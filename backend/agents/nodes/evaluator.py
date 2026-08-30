"""
Agente Evaluador de Políticas.

Actúa como auditor. Consulta:
1. El historial del pedido (datos ya cargados en el estado).
2. La base vectorial de normas (RAG via ``search_return_policy``), una vez
   por cada categoría distinta presente en ``items_to_return``.

Evalúa CADA artículo de la solicitud de forma independiente, con una única
llamada al LLM de salida estructurada (``PolicyEvaluationOutput``): un mismo
pedido puede terminar con unos artículos elegibles y otros no.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from backend.agents.state import ReturnState
from backend.agents.llm_factory import build_chat_llm, trim_history
from backend.agents.usage_tracking import invoke_structured_tracked
from backend.agents.infra.mcp_client import search_return_policy
from backend.agents.nodes.policy_rules import compute_refund, deterministic_check
from backend.models import ItemEligibility, OrderItem, PolicyEvaluationOutput
from backend.services.supabase_service import calculate_days_since_delivery

logger = logging.getLogger(__name__)

# ── Prompt del sistema ─────────────────────────────────────────────────────

POLICY_SYSTEM_PROMPT = """\
Eres un **Agente Evaluador de Políticas** de devoluciones de ReFlow.
Tu trabajo es determinar de forma objetiva y estricta si cada artículo que el
cliente quiere devolver es elegible, EVALUANDO CADA ARTÍCULO POR SEPARADO.

## Datos que recibirás
- Detalles del pedido (productos, fecha, estado).
- Historial de devoluciones del cliente.
- Para cada artículo a devolver: su categoría y las políticas de devolución
  relevantes de ESA categoría (resultados RAG).
- Motivo general de la devolución.

## Criterios de evaluación (por artículo)
1. **Plazo**: ¿Han pasado más días de los permitidos por la política de SU categoría?
2. **Estado del producto**: ¿La condición del artículo está dentro de las condiciones permitidas?
3. **Embalaje original / precinto de higiene**: ¿Se requiere y el cliente lo tiene intacto?
4. **Historial de abuso**: Si el cliente tiene más de 5 devoluciones aprobadas en los últimos
   6 meses, sé más estricto con artículos límite.

## Reglas importantes
- Un pedido puede tener artículos elegibles y NO elegibles a la vez. Evalúa
  cada `order_item_id` de forma independiente, usando SOLO la política de su
  propia categoría.
- Si aplica un `restocking_fee`, descuéntalo del `refund_amount` de ESE artículo.
- `refund_amount` debe ser 0 para cualquier artículo no elegible.
- Sé objetivo e imparcial. Basa cada decisión EXCLUSIVAMENTE en la política de
  la categoría de ese artículo y en los datos del pedido, no en los de otros artículos.

Debes devolver una evaluación (`items`) con exactamente una entrada por cada
artículo recibido en "Artículos a evaluar", identificada por su `order_item_id`.
"""


def _build_llm() -> ChatOpenAI:
    """Construye el LLM para el evaluador de políticas.

    Modelo configurable vía ``EVALUATOR_MODEL``; por defecto ``gpt-5-mini``.
    """
    return build_chat_llm(
        "EVALUATOR_MODEL", temperature=0.0
    )  # determinista para auditoría


def _product_name_by_item_id(order_details: dict[str, Any]) -> dict[str, str]:
    """Mapea order_item_id -> nombre de producto, a partir del pedido."""
    names: dict[str, str] = {}
    for raw_item in order_details.get("items", []):
        oi = OrderItem.model_validate(raw_item)
        if oi.id:
            names[oi.id] = (
                oi.product.name if oi.product and oi.product.name else "Artículo"
            )
    return names


def _category_by_item_id(order_details: dict[str, Any]) -> dict[str, str]:
    """Mapea order_item_id -> categoría de producto, a partir del pedido."""
    categories: dict[str, str] = {}
    for raw_item in order_details.get("items", []):
        oi = OrderItem.model_validate(raw_item)
        if oi.id and oi.product and oi.product.category:
            categories[oi.id] = oi.product.category
    return categories


async def evaluator_agent(state: ReturnState) -> dict[str, Any]:
    """Nodo del agente Evaluador de Políticas.

    Evalúa CADA artículo de ``items_to_return`` de forma independiente:
    busca la política de SU categoría vía RAG (una consulta por cada
    categoría distinta presente en la solicitud) y pide al LLM una decisión
    por artículo en una única llamada con salida estructurada
    (``PolicyEvaluationOutput``). Así un mismo pedido puede terminar con
    unos artículos marcados como elegibles y otros como no elegibles.
    """
    llm = _build_llm()

    order_details = state.get("order_details", {})
    return_history = state.get("return_history", {})
    reason = state.get("reason", "")
    reason_category = state.get("reason_category", "")
    items_to_return = state.get("items_to_return", [])

    product_names = _product_name_by_item_id(order_details)
    product_categories = _category_by_item_id(order_details)

    # ── Búsqueda RAG: una consulta por cada categoría DISTINTA presente
    #    entre los artículos que el cliente quiere devolver (no solo la
    #    del primer artículo del pedido) ─────────────────────────────────
    policy_by_category: dict[str, Any] = {}
    for item in items_to_return:
        category = product_categories.get(item.get("order_item_id"), "")
        if category and category not in policy_by_category:
            raw_policy = await search_return_policy(
                query=f"devolución {reason_category} {item.get('condition', '')} {reason}",
                category=category,
                thread_id=state.get("thread_id"),
            )
            # MCP devuelve content blocks: [{"type": "text", "text": "{...}"}]
            if isinstance(raw_policy, list) and raw_policy and "text" in raw_policy[0]:
                text = raw_policy[0]["text"]
                try:
                    policy_by_category[category] = json.loads(text)
                except json.JSONDecodeError:
                    logger.warning(
                        "RAG policy no devolvió JSON válido para '%s': %s",
                        category,
                        text[:200],
                    )
                    policy_by_category[category] = {"error": text}
            else:
                policy_by_category[category] = raw_policy

    days_since_order = calculate_days_since_delivery(order_details)

    # ── Construir contexto por artículo para el LLM ─────────────────────
    items_context = [
        {
            "order_item_id": item.get("order_item_id"),
            "name": product_names.get(item.get("order_item_id"), "Artículo"),
            "category": product_categories.get(item.get("order_item_id"), ""),
            "quantity": item.get("quantity", 1),
            "condition": item.get("condition", "unknown"),
            "applicable_policy": policy_by_category.get(
                product_categories.get(item.get("order_item_id"), ""),
                {"error": "No se encontró política para esta categoría."},
            ),
        }
        for item in items_to_return
    ]

    context = f"""
## Datos del pedido
- Días desde entrega: {days_since_order}
- Detalles del pedido: {json.dumps(order_details, default=str, ensure_ascii=False)}

## Motivo general indicado por el cliente
- Categoría de motivo: {reason_category}
- Descripción: {reason}

## Historial de devoluciones del cliente
- Total de devoluciones: {return_history.get('total_returns', 0)}
- Aprobadas: {return_history.get('approved', 0)}
- Rechazadas: {return_history.get('rejected', 0)}

## Artículos a evaluar (uno por uno, cada uno con SU política de categoría)
{json.dumps(items_context, default=str, ensure_ascii=False, indent=2)}
"""

    messages = [
        SystemMessage(content=POLICY_SYSTEM_PROMPT),
        *trim_history(state.get("messages", [])),
        SystemMessage(content=f"CONTEXTO DE EVALUACIÓN:\n{context}"),
    ]

    result: PolicyEvaluationOutput | None = await invoke_structured_tracked(
        llm,
        PolicyEvaluationOutput,
        messages,
        node="evaluator",
        thread_id=state.get("thread_id", ""),
        customer_id=state.get("customer_id"),
        order_id=state.get("order_id"),
    )

    updates: dict[str, Any] = {
        "current_agent": "evaluator",
        "policy_info": policy_by_category,
    }

    if result is None or not result.items:
        logger.warning(
            "Evaluador: structured output vacío o None; se marca todo como no elegible."
        )
        fallback_reason = "No se pudo evaluar la política correctamente."
        updates["items_eligibility"] = [
            {
                "order_item_id": item.get("order_item_id"),
                "is_eligible": False,
                "eligibility_reason": fallback_reason,
                "refund_amount": 0.0,
                "policy_category": product_categories.get(
                    item.get("order_item_id"), ""
                ),
            }
            for item in items_to_return
        ]
        updates["any_eligible"] = False
        updates["refund_amount"] = 0.0
        updates["eligibility_reason"] = fallback_reason
        return updates

    items_eligibility = [item.model_dump() for item in result.items]

    # ── Reglas deterministas (policy_rules.py): vetan legalmente y fijan
    #    el importe exacto del reembolso. El LLM aporta el razonamiento en
    #    lenguaje natural (eligibility_reason) y decide los casos donde las
    #    reglas no objetan nada, pero NUNCA puede:
    #      1. Levantar un veto legal/de negocio (p. ej. exclusión de
    #         higiene, plazo muy superado) — un veredicto "invalid" fuerza
    #         is_eligible=False sin importar lo que dijera el LLM.
    #      2. Decidir la aritmética del reembolso — refund_amount siempre
    #         sale de compute_refund(), nunca del LLM.
    #    Un veredicto "human_review" no cambia is_eligible (lo decide el
    #    LLM/HITL), solo marca needs_admin_approval a nivel de solicitud.
    order_items_raw = order_details.get("items", [])
    approved_returns = return_history.get("approved", 0)
    any_needs_review = False

    for item_eligibility in items_eligibility:
        oid = item_eligibility.get("order_item_id")
        matching_item = next(
            (i for i in items_to_return if i.get("order_item_id") == oid), None
        )
        if matching_item is None:
            continue

        category = product_categories.get(oid, "")
        policy_info = (policy_by_category.get(category) or {}).get("policy_info") or {}
        restocking_fee = policy_info.get("restocking_fee_percent") or 0.0
        deterministic_refund = compute_refund(
            order_items_raw, [matching_item], restocking_fee
        )

        verdict, reasons = deterministic_check(
            days_since_order=days_since_order,
            max_return_days=policy_info.get("max_return_days"),
            allowed_conditions=policy_info.get("allowed_conditions"),
            condition=matching_item.get("condition", "unknown"),
            category=category,
            reason_category=reason_category,
            refund_amount=deterministic_refund,
            approved_returns=approved_returns,
        )

        if verdict == "invalid":
            item_eligibility["is_eligible"] = False
            item_eligibility["refund_amount"] = 0.0
            item_eligibility["eligibility_reason"] = " | ".join(reasons)
        else:
            item_eligibility["refund_amount"] = (
                deterministic_refund if item_eligibility.get("is_eligible") else 0.0
            )
            if verdict == "human_review":
                any_needs_review = True
                logger.info(
                    "Evaluador: artículo %s marcado para revisión humana: %s",
                    oid,
                    "; ".join(reasons),
                )

    updates["items_eligibility"] = items_eligibility
    updates["any_eligible"] = any(item["is_eligible"] for item in items_eligibility)
    updates["refund_amount"] = sum(
        item["refund_amount"] for item in items_eligibility if item["is_eligible"]
    )
    updates["needs_admin_approval"] = any_needs_review
    # Resumen legible: usado por rejection_agent cuando NINGÚN artículo es
    # elegible, y útil para depuración/logs en el caso mixto.
    updates["eligibility_reason"] = " | ".join(
        f"{product_names.get(item['order_item_id'], item['order_item_id'])}: "
        f"{'elegible' if item['is_eligible'] else 'no elegible'} — {item['eligibility_reason']}"
        for item in items_eligibility
    )

    return updates
