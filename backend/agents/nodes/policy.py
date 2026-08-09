"""
Agente Evaluador de Políticas.

Actúa como auditor. Consulta:
1. El historial del pedido (datos ya cargados en el estado).
2. La base vectorial de normas (RAG via ``search_return_policy``).

Verifica de forma estricta si la devolución es elegible basándose en:
- Plazos de devolución según categoría.
- Estado del producto.
- Historial de devoluciones del cliente (detección de abuso).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI

from backend.agents.state import ReturnState
from backend.agents.infra.mcp_client import search_return_policy
from backend.models import OrderItem
from backend.services.supabase_service import calculate_days_since_delivery

logger = logging.getLogger(__name__)

# ── Prompt del sistema ─────────────────────────────────────────────────────

POLICY_SYSTEM_PROMPT = """\
Eres un **Agente Evaluador de Políticas** de devoluciones de ReFlow.
Tu trabajo es determinar de forma objetiva y estricta si una devolución es elegible.

## Datos que recibirás
- Detalles del pedido (productos, fecha, estado).
- Historial de devoluciones del cliente.
- Políticas de devolución relevantes (resultados RAG).
- Motivo y artículos que el cliente quiere devolver.

## Criterios de evaluación
1. **Plazo**: ¿Han pasado más días de los permitidos por la política de la categoría?
2. **Estado del producto**: ¿La condición del artículo está dentro de las condiciones permitidas?
3. **Embalaje original**: ¿Se requiere y el cliente lo tiene?
4. **Historial de abuso**: Si el cliente tiene más de 5 devoluciones aprobadas en los últimos
   6 meses, marca como sospechoso.

## Formato de respuesta
Responde SIEMPRE con un bloque JSON ```json ... ``` con las siguientes claves:
- **is_eligible** (bool): si la devolución es elegible.
- **eligibility_reason** (str): explicación detallada de la decisión.
- **policy_applied** (dict): resumen de la política aplicada.

Sé objetivo e imparcial. Basa tu decisión EXCLUSIVAMENTE en las políticas y datos.

## Comprobación determinista
El contexto incluye un veredicto calculado con las reglas objetivas de la
política (plazo, importe, motivo sensible, cliente frecuente). Si es
"invalid", tu is_eligible DEBE ser false. Si es "human_review", da igualmente
tu valoración de fondo: un administrador revisará la decisión antes de que
sea definitiva.
"""


# ── Reglas objetivas de la política general (dataset/policies/00_marco_general_devoluciones.md, sec. 5) ──
# Se calculan en código para no depender solo del criterio libre del LLM.

HITL_REFUND_THRESHOLD = 100.0  # debe coincidir con resolution.HITL_REFUND_THRESHOLD
SENSITIVE_REASONS = {"allergic_reaction", "counterfeit_suspicion"}
HYGIENE_CATEGORIES = {"cosmetica_perfumeria", "drogueria_salud", "alimentacion", "mascotas", "bebe_puericultura"}
MERCADIA_FAULT_REASONS = {"defective", "damaged_in_transit", "wrong_item_shipped", "missing_parts", "not_as_described"}
FREQUENT_RETURNER_THRESHOLD = 5


def _deterministic_check(
    days_since_order: int,
    max_return_days: int | None,
    allowed_conditions: list[str] | None,
    condition: str,
    category: str,
    reason_category: str,
    refund_amount: float,
    approved_returns: int,
) -> tuple[str, list[str]]:
    """Aplica las reglas objetivas de la política antes de consultar al LLM.

    Devuelve (veredicto, motivos), con veredicto en {"invalid", "human_review", "valid"}.
    """
    if max_return_days is None:
        return "valid", []  # sin política de categoría cargada: decide el LLM sin veto

    if days_since_order > max_return_days + 5:
        return "invalid", [f"Plazo superado: {days_since_order} días desde la entrega (máximo {max_return_days})."]

    if (
        category in HYGIENE_CATEGORIES
        and condition in {"opened_tested", "opened_unused", "used"}
        and reason_category not in MERCADIA_FAULT_REASONS
    ):
        return "invalid", [
            f"Precinto/uso roto ('{condition}') en categoría con exclusión legal de higiene "
            f"y motivo '{reason_category}' no imputable a Mercadia."
        ]

    if allowed_conditions and condition not in allowed_conditions and reason_category not in MERCADIA_FAULT_REASONS:
        return "invalid", [f"Estado '{condition}' no admitido para esta categoría ({allowed_conditions})."]

    reasons = []
    if refund_amount > HITL_REFUND_THRESHOLD:
        reasons.append(f"Importe {refund_amount:.2f}€ supera el umbral de {HITL_REFUND_THRESHOLD:.2f}€.")
    if max_return_days - 2 <= days_since_order <= max_return_days + 5:
        reasons.append(f"Solicitud en zona frontera del plazo ({days_since_order} de {max_return_days} días).")
    if reason_category in SENSITIVE_REASONS:
        reasons.append(f"Motivo sensible ('{reason_category}').")
    if approved_returns > FREQUENT_RETURNER_THRESHOLD:
        reasons.append(f"Cliente con {approved_returns} devoluciones aprobadas (posible abuso).")

    return ("human_review", reasons) if reasons else ("valid", [])


def _compute_refund(order_items: list[dict], items_to_return: list[dict], restocking_fee_percent: float) -> float:
    """Suma precio x cantidad de las líneas a devolver (no se confía en que
    el LLM haga aritmética de dinero), descontando el recargo de reposición."""
    by_id = {item["id"]: item for item in order_items if item.get("id")}
    total = sum(
        by_id[item["order_item_id"]]["unit_price"] * item.get("quantity", 1)
        for item in items_to_return
        if item.get("order_item_id") in by_id
    )
    return round(total * (1 - restocking_fee_percent / 100), 2)


def _build_llm() -> ChatOpenAI:
    """Construye el LLM para el evaluador de políticas."""
    return ChatOpenAI(
        model="gpt-5-nano",
        temperature=0.0,  # Determinista para auditoría
        max_tokens=4096,
    )





async def policy_evaluator_agent(state: ReturnState) -> dict[str, Any]:
    """Nodo del agente Evaluador de Políticas.

    Consulta las políticas via RAG y evalúa la elegibilidad.
    """
    llm = _build_llm()

    order_details = state.get("order_details", {})
    return_history = state.get("return_history", {})
    reason = state.get("reason", "")
    reason_category = state.get("reason_category", "")
    items_to_return = state.get("items_to_return", [])

    # ── Obtener la categoría del primer artículo para buscar la política ──
    product_category = ""
    order_items = order_details.get("items", [])
    if order_items and items_to_return:
        for raw_item in order_items:
            oi = OrderItem.model_validate(raw_item)
            if oi.product and oi.product.category:
                product_category = oi.product.category
                break

    # ── Búsqueda RAG de políticas ──────────────────────────────────────
    raw_policy = await search_return_policy(
        query=f"devolución {reason_category} {reason}",
        category=product_category,
    )
    # MCP devuelve content blocks: [{"type": "text", "text": "{...}"}]
    if isinstance(raw_policy, list) and raw_policy and "text" in raw_policy[0]:
        text = raw_policy[0]["text"]
        try:
            policy_results = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("RAG policy no devolvió JSON válido: %s", text[:200])
            policy_results = {"error": text}
    else:
        policy_results = raw_policy

    days_since_order = calculate_days_since_delivery(order_details)

    # ── Comprobación determinista + importe calculado a partir de las líneas ──
    policy_info = policy_results.get("policy_info") or {}
    condition = items_to_return[0].get("condition", "unknown") if items_to_return else "unknown"
    computed_refund = _compute_refund(order_items, items_to_return, policy_info.get("restocking_fee_percent") or 0)
    verdict, det_reasons = _deterministic_check(
        days_since_order=days_since_order,
        max_return_days=policy_info.get("max_return_days"),
        allowed_conditions=policy_info.get("allowed_conditions"),
        condition=condition,
        category=product_category,
        reason_category=reason_category,
        refund_amount=computed_refund,
        approved_returns=return_history.get("approved", 0),
    )

    # ── Construir contexto para el LLM ─────────────────────────────────
    context = f"""
## Datos del pedido
- Días desde entrega: {days_since_order}
- Detalles del pedido: {json.dumps(order_details, default=str, ensure_ascii=False)}

## Artículos a devolver
{json.dumps(items_to_return, default=str, ensure_ascii=False)}

## Motivo
- Categoría: {reason_category}
- Descripción: {reason}

## Historial de devoluciones del cliente
- Total de devoluciones: {return_history.get('total_returns', 0)}
- Aprobadas: {return_history.get('approved', 0)}
- Rechazadas: {return_history.get('rejected', 0)}

## Políticas encontradas (RAG)
{json.dumps(policy_results, default=str, ensure_ascii=False)}

## Comprobación determinista (obligatoria, no la contradigas)
- Veredicto: {verdict}
- Motivos: {'; '.join(det_reasons) or 'ninguno'}
- Importe calculado a partir de las líneas del pedido: {computed_refund:.2f}€
"""

    messages = [
        SystemMessage(content=POLICY_SYSTEM_PROMPT),
        *state.get("messages", []),
        SystemMessage(content=f"CONTEXTO DE EVALUACIÓN:\n{context}"),
    ]

    response = await llm.ainvoke(messages)

    # ── Extraer resultado estructurado ─────────────────────────────────
    updates: dict[str, Any] = {
        "messages": [response],
        "current_agent": "evaluator",
        "policy_info": policy_results,
    }

    match = re.search(r"```json\s*(.*?)\s*```", response.content, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            llm_eligible = result.get("is_eligible", False)
            llm_reason = result.get("eligibility_reason", "")
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Error parseando resultado del evaluador: %s", exc)
            llm_eligible, llm_reason = False, "Error interno al evaluar la política."
    else:
        llm_eligible, llm_reason = False, "No se pudo evaluar la política correctamente."

    # El veredicto determinista nunca se "ablanda": si es "invalid", se rechaza
    # sin más; si es "human_review", se respeta la valoración del LLM pero se
    # obliga a pasar por un administrador (needs_admin_approval).
    if verdict == "invalid":
        updates["is_eligible"] = False
        updates["needs_admin_approval"] = False
        updates["eligibility_reason"] = det_reasons[0]
    else:
        updates["is_eligible"] = llm_eligible
        updates["needs_admin_approval"] = verdict == "human_review"
        updates["eligibility_reason"] = llm_reason
    updates["refund_amount"] = computed_refund if (updates["is_eligible"] or updates["needs_admin_approval"]) else 0.0

    return updates
