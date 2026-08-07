"""
Agente de Resolución.

Si la devolución es elegible:
1. Genera la etiqueta de transporte (MCP logística).
2. Registra la devolución en Supabase (MCP datos).
3. Envía la notificación al cliente.
4. Aplica HITL si el importe supera los 100 €.

Si no es elegible:
- Redacta un mensaje empático de rechazo.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
# Command: instrucción de LangGraph que, además de actualizar el estado,
# indica explícitamente a qué nodo saltar a continuación ("goto").
# interrupt(): pausa la ejecución del grafo en este punto exacto y la
# reanuda más tarde con el valor que se le pase a Command(resume=...).
from langgraph.types import Command, interrupt

from backend.agents.state import ReturnState
from backend.agents.infra.mcp_client import (
    create_return_record,
    generate_shipping_label,
    send_customer_notification,
)
from backend.models import OrderItem

logger = logging.getLogger(__name__)

# ── Umbral HITL ────────────────────────────────────────────────────────────
# A partir de este importe (en euros) se exige aprobación humana antes de
# tramitar el reembolso; coincide con lo documentado en dataset/policies/00_....
HITL_REFUND_THRESHOLD = 100.0  # euros

# ── Prompts ────────────────────────────────────────────────────────────────

RESOLUTION_SYSTEM_PROMPT = """\
Eres el **Agente de Resolución** de ReFlow.
Tu trabajo es comunicar al cliente el resultado de su solicitud de devolución.

## Si la devolución es ELEGIBLE:
- Confirma al cliente que su devolución ha sido aprobada.
- Proporciona el número de seguimiento de la etiqueta de devolución.
- Indica los próximos pasos (imprimir etiqueta, enviar paquete).
- Menciona el monto del reembolso y el plazo estimado (5-10 días hábiles).

## Si la devolución NO es elegible:
- Comunica el rechazo de forma empática y comprensiva.
- Explica claramente el motivo del rechazo.
- Ofrece alternativas si es posible (contacto con soporte, garantía del fabricante, etc.).

## Si requiere aprobación de un administrador (HITL):
- Informa al cliente que, dado el importe del reembolso, se requiere una revisión adicional.
- Asegura que un responsable revisará su caso en un plazo de 24-48 horas.

Responde siempre en español, de forma cálida y profesional.
"""

# Este prompt tiene un placeholder {reason} que se rellena con .format()
# más abajo, según el motivo concreto del rechazo en cada caso.
REJECTION_SYSTEM_PROMPT = """\
Eres el **Agente de Resolución** de ReFlow. Redacta un mensaje empático
de rechazo de devolución en español.

Motivo del rechazo: {reason}

Sé comprensivo, ofrece alternativas cuando sea posible y cierra de forma positiva.
"""


def _build_llm() -> ChatOpenAI:
    """Construye el LLM para el agente de resolución."""
    # temperature=0.4: algo más de variación que en triage/policy, porque
    # aquí el objetivo es un mensaje cálido y natural, no extracción exacta.
    return ChatOpenAI(
        model="gpt-5-nano",
        temperature=0.4,
        max_tokens=4096,
    )


async def resolution_agent(
    state: ReturnState,
) -> Command[Literal["hitl_admin", "__end__"]]:
    """Nodo del agente de Resolución.

    Si la devolución es elegible, genera la etiqueta, registra la devolución
    y notifica al cliente. Aplica HITL si el reembolso supera el umbral.
    """
    llm = _build_llm()

    # Se recopilan del estado todos los datos necesarios para completar la
    # devolución (importe, identificadores, motivo, artículos...).
    refund_amount = state.get("refund_amount", 0.0)
    order_id = state.get("order_id", "")
    customer_id = state.get("customer_id", "")
    customer_name = state.get("customer_name", "")
    customer_email = state.get("customer_email", "")
    reason = state.get("reason", "")
    reason_category = state.get("reason_category", "")
    items_to_return = state.get("items_to_return", [])

    # ── HITL: pausar si el reembolso supera el umbral ──────────────────
    if refund_amount > HITL_REFUND_THRESHOLD:
        # interrupt(): detiene aquí la ejecución del grafo y persiste el
        # estado (gracias al checkpointer); el payload pasado es la
        # información que verá el proceso/panel de administración para
        # decidir. La ejecución no continúa hasta que alguien invoque el
        # grafo de nuevo con Command(resume={"approved": True/False}).
        admin_response = interrupt({
            "type": "admin_approval_required",
            "refund_amount": refund_amount,
            "order_id": order_id,
            "customer_id": customer_id,
            "reason": reason,
            "message": (
                f"Se requiere aprobación manual: reembolso de {refund_amount:.2f}€ "
                f"(umbral: {HITL_REFUND_THRESHOLD:.2f}€)."
            ),
        })

        # Al reanudarse, admin_response contiene lo que el admin decidió.
        if not admin_response.get("approved", False):
            # El administrador rechazó el reembolso tras revisión manual:
            # se genera un mensaje de rechazo y el grafo termina aquí, sin
            # llegar a generar etiqueta ni registrar la devolución.
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
                    "current_agent": "resolver",
                },
                goto="__end__",
            )
        # Si sí se aprobó (admin_response["approved"] es True), el flujo
        # continúa normalmente hacia abajo, como si nunca hubiera habido
        # que pausar (se genera etiqueta, se registra, se notifica).

    # ── Generar etiqueta de transporte ─────────────────────────────────
    # Antes de pedir la etiqueta hay que resolver el NOMBRE de cada
    # artículo a devolver, ya que items_to_return solo trae order_item_id.
    label_items = []
    order_items = state.get("order_details", {}).get("items", [])
    for item in items_to_return:
        item_name = "Artículo"
        # Busca, entre las líneas del pedido original, la que coincide con
        # el order_item_id que el cliente quiere devolver, para sacar el
        # nombre real del producto (si no se encuentra, queda "Artículo").
        for raw_oi in order_items:
            oi = OrderItem.model_validate(raw_oi)
            if oi.id == item.get("order_item_id"):
                item_name = oi.product.name if oi.product and oi.product.name else "Artículo"
                break
        label_items.append({
            "name": item_name,
            "quantity": item.get("quantity", 1),
        })

    # Llamada MCP al servidor de logística: genera el PDF y devuelve el
    # número de seguimiento y la ruta del archivo generado.
    label_result = await generate_shipping_label(
        order_id=order_id,
        items=label_items,
        customer_name=customer_name,
    )

    # ── Registrar devolución en Supabase ───────────────────────────────
    # Llamada MCP al servidor de datos: inserta la fila en return_requests
    # (y sus return_items) con estado inicial "pending".
    return_record = await create_return_record(
        order_id=order_id,
        customer_id=customer_id,
        reason=reason,
        reason_category=reason_category,
        refund_amount=refund_amount,
        items=items_to_return,
        notes=f"Procesado automáticamente. Tracking: {label_result['tracking_number']}",
    )

    # ── Notificar al cliente ───────────────────────────────────────────
    # "Envía" (simulado, ver logistics_service.py) el email de confirmación
    # con el resumen de la devolución y la etiqueta adjunta.
    await send_customer_notification(
        email=customer_email,
        subject="ReFlow - Tu devolución ha sido aprobada",
        message=(
            f"Hola {customer_name},\n\n"
            f"Tu devolución para el pedido {order_id[:8]}... ha sido aprobada.\n"
            f"Número de seguimiento: {label_result['tracking_number']}\n"
            f"Reembolso estimado: {refund_amount:.2f}€\n\n"
            "Adjuntamos la etiqueta de envío. Imprímela y pégala en el paquete.\n\n"
            "¡Gracias por tu paciencia!"
        ),
        attachment_path=label_result.get("label_path", ""),
    )

    # ── Generar mensaje final para el usuario ──────────────────────────
    # Este resumen se le pasa al LLM como contexto para que redacte el
    # mensaje final al cliente siguiendo RESOLUTION_SYSTEM_PROMPT.
    resolution_context = (
        f"Devolución aprobada. Tracking: {label_result['tracking_number']}. "
        f"Reembolso: {refund_amount:.2f}€. "
        f"Etiqueta generada en: {label_result.get('label_path', 'N/A')}."
    )

    final_response = await llm.ainvoke([
        SystemMessage(content=RESOLUTION_SYSTEM_PROMPT),
        SystemMessage(content=f"CONTEXTO: {resolution_context}"),
    ])

    # goto="__end__": termina el turno aquí (no hay más nodos que ejecutar
    # tras una devolución aprobada, con o sin HITL de por medio).
    return Command(
        update={
            "messages": [final_response],
            "tracking_number": label_result["tracking_number"],
            "label_path": label_result.get("label_path"),
            "return_request_id": return_record["return_request"]["id"],
            # Distingue si se aprobó automáticamente (importe bajo el
            # umbral) o tras pasar por HITL, para trazabilidad.
            "admin_decision": "auto_approved" if refund_amount <= HITL_REFUND_THRESHOLD else "approved",
            "resolution": "approved",
            "current_agent": "resolver",
        },
        goto="__end__",
    )


async def rejection_agent(state: ReturnState) -> dict[str, Any]:
    """Nodo que comunica un rechazo empático cuando la devolución no es elegible."""
    llm = _build_llm()

    # Usa el motivo que dejó el Agente Evaluador (policy.py); si por algún
    # motivo no está presente, cae en un mensaje genérico.
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
    # Nota: en el flujo actual, resolution_agent ya gestiona directamente el
    # caso de rechazo del admin (goto="__end__") y el de aprobación sigue
    # en el propio resolution_agent; este nodo queda como punto de entrada
    # explícito del grafo para el camino "hitl_admin" (ver graph.py).
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
