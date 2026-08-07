"""
Agente de Resolución.

Tres nodos del grafo viven en este archivo (comparten prompts y las señales
de HITL de ``_needs_admin_approval``):

- resolution_agent: primero comprueba si el caso necesita HITL
  (``_needs_admin_approval``, ver más abajo). Si no, resuelve directamente
  (genera etiqueta, registra la devolución en Supabase, notifica al
  cliente). Si sí, pausa con interrupt() ANTES de tocar ninguna tool y, al
  reanudar con la decisión del administrador, cede el turno a hitl_admin
  sin resolver nada él mismo.
- hitl_admin_node: retoma tras esa pausa. Si el administrador aprobó,
  completa el proceso (misma etiqueta+registro+notificación que arriba,
  vía el helper compartido _build_approved_return_updates); si rechazó,
  redacta un mensaje de rechazo.
- rejection_agent: redacta el rechazo cuando la devolución no es elegible
  desde el principio (rama que viene del Evaluador, no de HITL).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from langchain_core.messages import SystemMessage
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

# ── Señales de HITL ──────────────────────────────────────────────────────
# dataset/policies/00_marco_general_devoluciones.md, sección 5: con
# independencia de que la devolución sea elegible, estas señales obligan
# SIEMPRE a pasar por revisión humana. Se evalúan aquí en Python
# determinista (no como sugerencia dentro de un prompt), mismo motivo que
# refund_amount en policy.py: son reglas de negocio, no algo que dependa de
# que un LLM las recuerde bien.

# Importe a partir del cual se exige aprobación humana antes del reembolso.
HITL_REFUND_THRESHOLD = 100.0  # euros

# "la fecha de entrega está a menos de 3 días de distancia del límite del
# plazo" (ej.: día 28 o 29 de una política de 30 días) — zona en la que la
# elegibilidad es ambigua aunque el Evaluador haya dicho que sí procede.
BOUNDARY_ZONE_DAYS = 3

# Motivos que implican riesgo para la salud o responsabilidad de producto:
# van siempre a revisión humana, aunque el resto del caso sea intachable.
SENSITIVE_REASON_CATEGORIES = {"allergic_reaction", "counterfeit_suspicion"}

# "más de 3 devoluciones aprobadas en los últimos 90 días" (posible abuso /
# wardrobing). La otra mitad del criterio del doc — tasa de devolución
# >50% de sus pedidos — NO se evalúa: ninguna consulta actual trae el
# número total de pedidos del cliente, solo su historial de devoluciones.
FREQUENT_RETURNER_THRESHOLD = 3
FREQUENT_RETURNER_WINDOW_DAYS = 90

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


def _recent_approved_returns_count(return_history: dict, window_days: int) -> int:
    """Cuenta devoluciones aprobadas del cliente en los últimos ``window_days``
    días, a partir de la lista ``returns`` que ya trae ``return_history``
    (``get_customer_return_history`` incluye ``created_at`` por fila; no
    hace falta una consulta nueva ni filtrar en SQL).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    count = 0
    for entry in return_history.get("returns") or []:
        if entry.get("status") != "approved":
            continue
        created_at = entry.get("created_at")
        if not created_at:
            continue
        try:
            created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        except ValueError:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created >= cutoff:
            count += 1
    return count


def _needs_admin_approval(state: ReturnState) -> tuple[bool, list[str]]:
    """Decide si el caso debe pasar por HITL, con independencia de que ya se
    haya considerado elegible, y por qué (puede haber varias razones a la
    vez). Devuelve (necesita_hitl, razones) — ver
    dataset/policies/00_marco_general_devoluciones.md, sección 5.
    """
    reasons: list[str] = []

    refund_amount = state.get("refund_amount", 0.0)
    if refund_amount > HITL_REFUND_THRESHOLD:
        reasons.append(
            f"importe a reembolsar de {refund_amount:.2f}€ supera el umbral de "
            f"{HITL_REFUND_THRESHOLD:.0f}€"
        )

    reason_category = state.get("reason_category", "")
    if reason_category in SENSITIVE_REASON_CATEGORIES:
        reasons.append(f"motivo sensible ('{reason_category}') que requiere valoración humana")

    # Solo se evalúa si ambos datos están disponibles: si policy.py no pudo
    # determinarlos (política no encontrada, fecha inválida...), esta señal
    # se omite en vez de bloquear la resolución con un dato que no existe.
    days_since_delivery = state.get("days_since_delivery")
    max_return_days = state.get("policy_max_return_days")
    if days_since_delivery is not None and max_return_days is not None:
        diff = days_since_delivery - max_return_days
        if abs(diff) < BOUNDARY_ZONE_DAYS:
            reasons.append(
                f"solicitud en zona frontera del plazo ({days_since_delivery} de "
                f"{max_return_days} días, diferencia {diff:+d})"
            )

    recent_approved = _recent_approved_returns_count(
        state.get("return_history") or {}, FREQUENT_RETURNER_WINDOW_DAYS
    )
    if recent_approved > FREQUENT_RETURNER_THRESHOLD:
        reasons.append(
            f"cliente con {recent_approved} devoluciones aprobadas en los últimos "
            f"{FREQUENT_RETURNER_WINDOW_DAYS} días (posible abuso)"
        )

    return bool(reasons), reasons


async def _build_approved_return_updates(state: ReturnState) -> dict[str, Any]:
    """Completa una devolución ya aprobada: genera la etiqueta, la registra
    en Supabase, notifica al cliente y redacta el mensaje final.

    Compartida por dos caminos: la aprobación automática (resolution_agent,
    reembolso ≤ umbral HITL) y la aprobación de un administrador tras HITL
    (hitl_admin_node). Solo construye las actualizaciones de estado; no
    decide a qué nodo ir después (eso lo hace cada caller).
    """
    llm = _build_llm()

    refund_amount = state.get("refund_amount", 0.0)
    order_id = state.get("order_id", "")
    customer_id = state.get("customer_id", "")
    customer_name = state.get("customer_name", "")
    customer_email = state.get("customer_email", "")
    reason = state.get("reason", "")
    reason_category = state.get("reason_category", "")
    items_to_return = state.get("items_to_return", [])

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

    return {
        "messages": [final_response],
        "tracking_number": label_result["tracking_number"],
        "label_path": label_result.get("label_path"),
        "return_request_id": return_record["return_request"]["id"],
        "resolution": "approved",
    }


async def resolution_agent(
    state: ReturnState,
) -> Command[Literal["hitl_admin", "__end__"]]:
    """Nodo del agente de Resolución.

    Si el caso no necesita HITL (``_needs_admin_approval``), resuelve la
    devolución directamente (etiqueta, registro, notificación). Si sí lo
    necesita, se pausa con ``interrupt()`` y, al reanudar con la decisión
    del administrador, cede el control a ``hitl_admin`` — es ese nodo quien
    termina de resolver el caso (ver ``hitl_admin_node`` más abajo), no
    ``resolution_agent``.
    """
    order_id = state.get("order_id", "")
    customer_id = state.get("customer_id", "")

    needs_hitl, reasons = _needs_admin_approval(state)

    # ── HITL: pausar si alguna señal de dataset/policies/00_...md §5 aplica ──
    if needs_hitl:
        # interrupt(): detiene aquí la ejecución del grafo y persiste el
        # estado (gracias al checkpointer); el payload pasado es la
        # información que verá el proceso/panel de administración para
        # decidir. La ejecución no continúa hasta que alguien invoque el
        # grafo de nuevo con Command(resume={"approved": True/False}).
        admin_response = interrupt({
            "type": "admin_approval_required",
            "refund_amount": state.get("refund_amount", 0.0),
            "order_id": order_id,
            "customer_id": customer_id,
            "reason": state.get("reason", ""),
            "hitl_reasons": reasons,
            "message": "Se requiere aprobación manual: " + "; ".join(reasons) + ".",
        })

        # Al reanudarse, admin_response contiene lo que el admin decidió.
        # No se resuelve aquí: se deja constancia de la decisión en el
        # estado y se cede el turno a hitl_admin, que es quien completa el
        # proceso (aprobado) o redacta el rechazo (rechazado).
        return Command(
            update={
                "admin_decision": "approved" if admin_response.get("approved", False) else "rejected",
                "current_agent": "resolver",
            },
            goto="hitl_admin",
        )

    # ── Sin HITL: ninguna señal aplica, se resuelve directamente ────────
    updates = await _build_approved_return_updates(state)
    updates["admin_decision"] = "auto_approved"
    updates["current_agent"] = "resolver"
    return Command(update=updates, goto="__end__")


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
    """Nodo HITL: retoma el caso cuando ``resolution_agent`` reanuda tras
    ``interrupt()`` con la decisión de un administrador (ver
    ``Command(resume=...)`` en ``backend/main.py``).

    Si el administrador aprobó, completa el proceso igual que una
    devolución auto-aprobada (etiqueta, registro, notificación). Si
    rechazó, redacta un mensaje de rechazo empático.
    """
    admin_decision = state.get("admin_decision", "approved")

    if admin_decision == "approved":
        updates = await _build_approved_return_updates(state)
        updates["admin_decision"] = "approved"
        updates["current_agent"] = "hitl_admin"
        return updates

    llm = _build_llm()
    rejection_msg = await llm.ainvoke([
        SystemMessage(
            content=REJECTION_SYSTEM_PROMPT.format(
                reason="El administrador ha rechazado la devolución tras revisión manual."
            )
        ),
    ])
    return {
        "messages": [rejection_msg],
        "admin_decision": "rejected",
        "resolution": "rejected_by_admin",
        "current_agent": "hitl_admin",
    }
