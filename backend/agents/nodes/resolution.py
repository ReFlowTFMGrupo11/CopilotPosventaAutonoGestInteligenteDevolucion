"""
Agente de Resolución.

Si la devolución es elegible:
1. Genera la etiqueta de transporte (MCP logística).
2. Registra la devolución en Supabase (MCP datos).
3. Envía la notificación al cliente.
4. Aplica HITL si el importe supera los 100 €.

Si no es elegible:
- Redacta un mensaje empático de rechazo.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 FRONTERA  DETERMINISTA  vs  LLM  en este módulo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 DETERMINISTA  (resolution_agent)
  - Umbral HITL: refund_amount > 100€ → pausa obligatoria (interrupt).
  - Creación del registro en BD (create_return_record).
  - Generación de la etiqueta de transporte (generate_shipping_label).
  - Actualización de estado en BD (update_return_status).
  - Envío de notificación al cliente (send_customer_notification).
  - Decisión de HITL: si admin aprueba/rechaza → actualiza BD y continúa.

 LLM  (resolution_agent + rejection_agent)
  - Redacción del mensaje final al cliente (aprobación, rechazo, HITL pendiente).
  - Tono empático y explicación clara de los pasos siguientes.

 REGLA GENERAL:
  - Todas las acciones sobre BD y servicios externos son deterministas.
  - El LLM solo redacta los mensajes que ve el cliente.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Command, interrupt

from backend.agents.state import ReturnState
from backend.agents.llm_factory import build_chat_llm
from backend.agents.infra.mcp_client import (
    create_return_record,
    generate_shipping_label,
    send_customer_notification,
    update_return_status,
)
from backend.services.supabase_service import (
    DUPLICATE_RETURN_MARKER,
    get_latest_return_request,
    get_pending_return_request_id,
)
from backend.models import OrderItem

logger = logging.getLogger(__name__)

# ── Umbral HITL ────────────────────────────────────────────────────────────
HITL_REFUND_THRESHOLD = 100.0  # euros

# ── Prompts ────────────────────────────────────────────────────────────────

RESOLUTION_SYSTEM_PROMPT = """\
Eres el **Agente de Resolución** de ReFlow.
Tu trabajo es comunicar al cliente el resultado de su solicitud de devolución,
que puede ser MIXTO: unos artículos aprobados y otros rechazados a la vez.

## Para los artículos APROBADOS:
- Confirma, nombrándolos, que esos artículos han sido aprobados para devolución.
- Proporciona el número de seguimiento de la etiqueta de devolución.
- Indica los próximos pasos (imprimir etiqueta, enviar paquete).
- Menciona el monto del reembolso y el plazo estimado (5-10 días hábiles).

## Para los artículos RECHAZADOS (si los hay):
- Comunica el rechazo de forma empática y comprensiva, nombrando el artículo.
- Explica claramente el motivo del rechazo de ESE artículo en concreto.
- Ofrece alternativas si es posible (contacto con soporte, garantía del fabricante, etc.).

## Si requiere aprobación de un administrador (HITL):
- Informa al cliente que, dado el importe del reembolso, se requiere una revisión adicional.
- Asegura que un responsable revisará su caso en un plazo de 24-48 horas.

Responde siempre en español, de forma cálida y profesional. Si el resultado es
mixto, deja MUY CLARO qué artículos se devuelven y cuáles no, y por qué.
"""

REJECTION_SYSTEM_PROMPT = """\
Eres el **Agente de Resolución** de ReFlow. Redacta un mensaje empático
de rechazo de devolución en español.

Motivo del rechazo: {reason}

## Reglas
- Sé comprensivo y profesional, y explica el motivo del rechazo con claridad.
- Esta decisión es definitiva para esta conversación: no la presentes como
  provisional ni sujeta a revisión posterior.
- NO prometas ni sugieras ninguna acción que ReFlow no puede ejecutar de
  verdad. En concreto, NUNCA:
    - pidas fotos, vídeos ni ningún archivo adjunto (este chat es solo
      texto, no hay forma de recibir ni procesar archivos);
    - ofrezcas reparación, sustitución, asistencia técnica remota, gestión
      con el fabricante ni "revisión del caso" — ninguno de esos flujos
      existe en este sistema;
    - prometas plazos de respuesta futuros (p. ej. "en 48 horas").
- Cierra de forma positiva pero realista: agradece su paciencia y, si
  procede, indícale que puede escribir de nuevo para otra consulta o pedido.
"""


def _build_llm() -> ChatOpenAI:
    """Construye el LLM para el agente de resolución.

    Modelo configurable vía ``RESOLVER_MODEL``; por defecto ``gpt-5-nano``.
    """
    return build_chat_llm("RESOLVER_MODEL", temperature=0.4)


async def resolution_agent(
    state: ReturnState,
) -> Command[Literal["hitl_admin", "__end__"]]:
    """Nodo del agente de Resolución.

    Procesa SOLO los artículos que el Evaluador marcó como elegibles
    (``items_eligibility``): genera etiqueta, registra la devolución y
    notifica al cliente. Si la solicitud era mixta, el mensaje final también
    explica qué artículos quedaron fuera y por qué. Aplica HITL si el
    reembolso de los artículos elegibles supera el umbral.
    """
    llm = _build_llm()

    refund_amount = state.get("refund_amount", 0.0)
    order_id = state.get("order_id", "")
    order_number = state.get("order_number", "")
    customer_id = state.get("customer_id", "")
    customer_name = state.get("customer_name", "")
    customer_email = state.get("customer_email", "")
    reason = state.get("reason", "")
    reason_category = state.get("reason_category", "")
    items_to_return = state.get("items_to_return", [])
    items_eligibility = state.get("items_eligibility", [])

    # ── Filtrar: solo se procesan los artículos elegibles ───────────────
    eligible_ids = {e["order_item_id"] for e in items_eligibility if e.get("is_eligible")}
    rejected_items = [e for e in items_eligibility if not e.get("is_eligible")]
    eligible_items_to_return = [
        item for item in items_to_return if item.get("order_item_id") in eligible_ids
    ]

    # ── HITL: pausar si el importe supera el umbral o si el Evaluador
    #    marcó el caso como "needs_admin_approval" (zona frontera de plazo,
    #    motivo sensible o cliente frecuente, aunque el importe sea bajo) ──
    needs_admin_approval = state.get("needs_admin_approval", False) or refund_amount > HITL_REFUND_THRESHOLD
    if needs_admin_approval:
        # Crear registro o reutilizar existente (re-ejecución tras resume).
        thread_id = state.get("thread_id", "")
        try:
            hitl_record = await create_return_record(
                order_id=order_id,
                customer_id=customer_id,
                reason=reason,
                reason_category=reason_category,
                refund_amount=refund_amount,
                items=items_to_return,
                notes="Pendiente de aprobación manual (HITL).",
                thread_id=thread_id,
            )
            existing_return_id = hitl_record["return_request"]["id"]
            await update_return_status(
                return_id=existing_return_id,
                status="pending_approval",
                resolution="",
                notes=f"Reembolso de {refund_amount:.2f}€ supera umbral o requiere revisión.",
            )
        except (RuntimeError, ValueError) as exc:
            # Solo interpretar como duplicado si lleva el marcador de
            # supabase_service.py; cualquier otro fallo (red, datos
            # malformados...) se propaga en vez de silenciarse como si
            # fuera un resume normal tras interrupt().
            if DUPLICATE_RETURN_MARKER not in str(exc):
                raise
            # Guard de duplicados: el registro ya existe (resume tras interrupt)
            logger.info("HITL record ya existe, reutilizando: %s", exc)
            # Buscar el ID del registro existente via BD
            existing_return_id = await get_pending_return_request_id(order_id)

        admin_response = interrupt({
            "type": "admin_approval_required",
            "refund_amount": refund_amount,
            "order_id": order_id,
            "order_number": order_number,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "reason": reason,
            "return_request_id": existing_return_id,
            "items": [
                {
                    "order_item_id": item.get("order_item_id"),
                    "quantity": item.get("quantity", 1),
                    "condition": item.get("condition"),
                }
                for item in items_to_return
            ],
            "message": (
                f"Pedido {order_number} · Cliente: {customer_name} · "
                f"Artículos: {len(items_to_return)} · "
                f"Reembolso: {refund_amount:.2f}€ (umbral: {HITL_REFUND_THRESHOLD:.2f}€) · "
                f"Motivo: {reason_category} — {reason}"
            ),
        })

        if not admin_response.get("approved", False):
            # Admin rechazó: actualizar BD y comunicar al cliente
            await update_return_status(
                return_id=existing_return_id,
                status="rejected",
                resolution="rejected_by_admin",
                notes=admin_response.get("reason", "Rechazado por administrador."),
            )
            rejection_msg = await llm.ainvoke([
                SystemMessage(
                    content=REJECTION_SYSTEM_PROMPT.format(
                        reason="El administrador ha rechazado la devolución tras revisión manual."
                    )
                ),
            ])
            return Command(
                update={
                    "messages": [rejection_msg],
                    "admin_decision": "rejected",
                    "resolution": "rejected_by_admin",
                    "return_request_id": existing_return_id,
                    "current_agent": "resolver",
                },
                goto="__end__",
            )

    # Admin aprobó (o no hacía falta HITL): continuar con etiqueta + notificación.
    # ── Mapeo order_item_id -> nombre, para etiquetas y mensajes ────────
    order_items = state.get("order_details", {}).get("items", [])
    item_names: dict[str, str] = {}
    for raw_oi in order_items:
        oi = OrderItem.model_validate(raw_oi)
        if oi.id:
            item_names[oi.id] = oi.product.name if oi.product and oi.product.name else "Artículo"

    # ── Generar etiqueta de transporte (solo artículos elegibles) ──────
    label_items = [
        {
            "name": item_names.get(item.get("order_item_id"), "Artículo"),
            "quantity": item.get("quantity", 1),
        }
        for item in eligible_items_to_return
    ]

    label_result = await generate_shipping_label(
        order_id=order_id,
        items=label_items,
        customer_name=customer_name,
    )

    # ── Registrar devolución en Supabase (solo artículos elegibles) ─────
    # Si viene de HITL aprobado, el registro ya existe (se creó antes del
    # interrupt, ver bloque HITL arriba); solo hay que marcarlo aprobado.
    if needs_admin_approval:
        await update_return_status(
            return_id=existing_return_id,
            status="approved",
            resolution="approved_by_admin",
            notes=f"Aprobado por administrador. Tracking: {label_result['tracking_number']}",
        )
        return_request_id = existing_return_id
    else:
        try:
            return_record = await create_return_record(
                order_id=order_id,
                customer_id=customer_id,
                reason=reason,
                reason_category=reason_category,
                refund_amount=refund_amount,
                items=eligible_items_to_return,
                notes=f"Procesado automáticamente. Tracking: {label_result['tracking_number']}",
                thread_id=state.get("thread_id", ""),
            )
        except (RuntimeError, ValueError) as exc:
            # Solo interpretar como duplicado si lleva el marcador de
            # supabase_service.py; ver comentario equivalente más arriba.
            if DUPLICATE_RETURN_MARKER not in str(exc):
                raise
            # Guard de duplicados: ya existe una devolución para este pedido/artículo
            # (p. ej. reintento del cliente o re-ejecución de un caso de QA).
            logger.info("Return record ya existe, informando al cliente: %s", exc)
            existing = await get_latest_return_request(order_id)
            duplicate_msg = await llm.ainvoke([
                SystemMessage(
                    content=(
                        "Eres el Agente de Resolución de ReFlow. Informa al cliente, de forma "
                        "clara y empática, de que ya existe una solicitud de devolución en curso "
                        f"para este pedido (estado actual: {existing.get('status', 'en proceso')}). "
                        "No hace falta crear una nueva; nuestro equipo ya la está gestionando."
                    )
                ),
            ])
            return Command(
                update={
                    "messages": [duplicate_msg],
                    "resolution": "duplicate",
                    "return_request_id": existing.get("id", ""),
                    "current_agent": "resolver",
                },
                goto="__end__",
            )
        # ── Marcar como aprobada (auto-aprobación ≤ umbral) ────────────────
        await update_return_status(
            return_id=return_record["return_request"]["id"],
            status="approved",
            resolution="auto_approved",
            notes=f"Aprobado automáticamente. Tracking: {label_result['tracking_number']}",
        )
        return_request_id = return_record["return_request"]["id"]

    # ── Notificar al cliente ───────────────────────────────────────────
    approved_names = [item_names.get(item.get("order_item_id"), "Artículo") for item in eligible_items_to_return]
    rejected_lines = "\n".join(
        f"- {item_names.get(r['order_item_id'], r['order_item_id'])}: {r['eligibility_reason']}"
        for r in rejected_items
    )

    email_body = (
        f"Hola {customer_name},\n\n"
        f"Tu devolución para el pedido {order_number or order_id} ha sido procesada.\n\n"
        f"Artículos aprobados: {', '.join(approved_names)}\n"
        f"Número de seguimiento: {label_result['tracking_number']}\n"
        f"Reembolso estimado: {refund_amount:.2f}€\n"
    )
    if rejected_items:
        email_body += f"\nArtículos que NO pudieron devolverse:\n{rejected_lines}\n"
    email_body += (
        "\nAdjuntamos la etiqueta de envío para los artículos aprobados. "
        "Imprímela y pégala en el paquete.\n\n¡Gracias por tu paciencia!"
    )

    await send_customer_notification(
        email=customer_email,
        subject="ReFlow - Resultado de tu solicitud de devolución",
        message=email_body,
        attachment_path=label_result.get("label_path", ""),
    )

    # ── Generar mensaje final para el usuario ──────────────────────────
    resolution_context = (
        f"Artículos APROBADOS: {', '.join(approved_names)}. "
        f"Tracking: {label_result['tracking_number']}. "
        f"Reembolso total: {refund_amount:.2f}€. "
        f"Etiqueta generada en: {label_result.get('label_path', 'N/A')}. "
    )
    if rejected_items:
        resolution_context += (
            "Artículos RECHAZADOS (no incluidos en la etiqueta ni en el reembolso): "
            + "; ".join(
                f"{item_names.get(r['order_item_id'], r['order_item_id'])} ({r['eligibility_reason']})"
                for r in rejected_items
            )
            + "."
        )
    else:
        resolution_context += "No hay artículos rechazados en esta solicitud."

    final_response = await llm.ainvoke([
        SystemMessage(content=RESOLUTION_SYSTEM_PROMPT),
        SystemMessage(content=f"CONTEXTO: {resolution_context}"),
    ])

    return Command(
        update={
            "messages": [final_response],
            "tracking_number": label_result["tracking_number"],
            "label_path": label_result.get("label_path"),
            "return_request_id": return_request_id,
            "admin_decision": "auto_approved" if refund_amount <= HITL_REFUND_THRESHOLD else "approved",
            "resolution": "partially_approved" if rejected_items else "approved",
            "current_agent": "resolver",
        },
        goto="__end__",
    )


async def rejection_agent(state: ReturnState) -> dict[str, Any]:
    """Nodo que comunica un rechazo empático cuando la devolución no es elegible."""
    llm = _build_llm()

    eligibility_reason = state.get("eligibility_reason", "No se cumple la política de devoluciones.")

    response = await llm.ainvoke([
        SystemMessage(
            content=REJECTION_SYSTEM_PROMPT.format(reason=eligibility_reason)
        ),
    ])

    return {
        "messages": [response],
        "resolution": "rejected",
        "current_agent": "resolver",
    }


async def hitl_admin_node(state: ReturnState) -> dict[str, Any]:
    """Nodo HITL: punto de espera para aprobación administrativa.

    Este nodo se ejecuta cuando el ``resolution_agent`` redirige aquí
    tras recibir la aprobación del admin via ``Command(resume=...)``.
    """
    admin_decision = state.get("admin_decision", "approved")

    if admin_decision == "approved":
        msg = AIMessage(
            content=(
                "Tu devolución ha sido revisada y **aprobada** por nuestro equipo. "
                "Recibirás un correo con la etiqueta de envío y los próximos pasos. "
                "¡Gracias por tu paciencia!"
            )
        )
    else:
        msg = AIMessage(
            content=(
                "Tras la revisión de tu caso, lamentablemente no ha sido posible "
                "aprobar la devolución. Si tienes alguna duda, puedes contactar con "
                "nuestro equipo de soporte."
            )
        )

    return {
        "messages": [msg],
        "resolution": admin_decision,
        "current_agent": "hitl_admin",
    }
