"""
Agente Evaluador de Políticas.

Actúa como auditor. Consulta:
1. El historial del pedido (datos ya cargados en el estado).
2. La política estructurada de cada categoría (``get_policy_info``, sin RAG
   narrativo) para un PRE-CHECK determinista (ver defenderRAG.md §4.2).
3. Solo para los artículos que ese pre-check NO descarta ya: la base
   vectorial de normas (RAG via ``search_return_policy``), una vez por cada
   categoría distinta presente entre esos artículos pendientes.

Evalúa CADA artículo de la solicitud de forma independiente. Los artículos ya
vetados legalmente por el pre-check (plazo muy superado, exclusión de
higiene, condición no admitida) nunca llegan al LLM ni a la búsqueda RAG
narrativa — su resultado ya está decidido y no puede cambiar, así que
pagar esa llamada (embedding + RPC vectorial + LLM) no tendría ningún efecto
en la decisión final. Solo los artículos en zona gris (`valid`/
`human_review` tras el pre-check) pasan por una única llamada al LLM de
salida estructurada (``PolicyEvaluationOutput``): un mismo pedido puede
terminar con unos artículos elegibles y otros no.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from backend.agents.state import ReturnState
from backend.agents.llm_factory import build_chat_llm
from backend.agents.usage_tracking import invoke_structured_tracked
from backend.agents.infra.mcp_client import get_policy_info, search_return_policy
from backend.agents.nodes.policy_rules import compute_refund, deterministic_check
from backend.models import ItemEligibility, OrderItem, PolicyEvaluationOutput

logger = logging.getLogger(__name__)

# ── Traducción de enums para la query RAG (ver docs/defensaTFM/defenderRAG.md
#    §4.1) ─────────────────────────────────────────────────────────────────
#
# `reason_category`/`condition` viajan en inglés por todo el código (claves
# de _CONDITION_MAP en triage.py, comparaciones en policy_rules.py, etc.) y
# NO se tocan aquí -- este mapeo se usa SOLO al construir el texto de la
# query semántica hacia search_return_policy(), nunca para lógica de
# negocio. Medido contra la BD real (16 categorías × 2 motivos, ver
# defenderRAG.md): traducir estos dos términos sube la similitud media
# ~0.01 (positivo en 15/16 casos) al eliminar el último anglicismo de una
# query que ya es, por lo demás, 100% castellano -- el documento de
# políticas está en castellano, así que cualquier resto de inglés en la
# query es puro ruido de registro frente al corpus.
_REASON_CATEGORY_ES = {
    "defective": "defectuoso",
    "wrong_item": "artículo incorrecto",
    "not_as_described": "no coincide con lo descrito",
    "no_longer_needed": "ya no lo necesita",
    "arrived_late": "llegó tarde",
    "other": "otro motivo",
}
_CONDITION_ES = {
    "unopened": "sin abrir",
    "defective": "defectuoso",
    "damaged": "dañado",
    "used": "usado",
    "wrong_item": "artículo incorrecto",
}


def _build_rag_query(category: str, reason_category: str, condition: str) -> str:
    """Construye la query semántica para ``search_return_policy()``.

    Formulación en "registro documental" (pregunta sobre política de la
    categoría) en vez de "registro conversacional" (motivo+estado tal cual
    los da el cliente) -- medido contra la BD real (ver defenderRAG.md
    §4.1): la similitud coseno media con ``text-embedding-3-small`` sube de
    ~0.47 (query anterior: ``devolución {reason_category} {condition}
    {reason}``, con el texto libre del cliente) a ~0.68 (esta query), porque
    se acerca al registro normativo/formal de los documentos de política en
    vez del registro coloquial de la conversación. Se mantienen
    ``reason_category``/``condition`` (no el texto libre ``reason`` del
    cliente) para conservar la especificidad del caso dentro de los 5-6
    chunks de la categoría (p. ej. que el chunk de "reacciones alérgicas"
    de cosmética se siga recuperando), sin arrastrar la varianza léxica del
    texto libre que hacía caer la similitud en la query anterior.
    """
    reason_es = _REASON_CATEGORY_ES.get(reason_category, reason_category)
    condition_es = _CONDITION_ES.get(condition, condition)
    return (
        f"política de devolución en {category}: "
        f"motivo {reason_es}, estado del producto {condition_es}"
    )


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


def _eligibility_summary(
    items_eligibility: list[dict[str, Any]], product_names: dict[str, str]
) -> str:
    """Resumen legible: usado por rejection_agent cuando NINGÚN artículo es
    elegible, y útil para depuración/logs en el caso mixto."""
    return " | ".join(
        f"{product_names.get(item['order_item_id'], item['order_item_id'])}: "
        f"{'elegible' if item['is_eligible'] else 'no elegible'} — {item['eligibility_reason']}"
        for item in items_eligibility
    )


async def evaluator_agent(state: ReturnState) -> dict[str, Any]:
    """Nodo del agente Evaluador de Políticas.

    Evalúa CADA artículo de ``items_to_return`` de forma independiente, en
    dos fases (ver docs/defensaTFM/defenderRAG.md §4.2 para la evidencia
    completa de por qué se separó así):

    1. **Pre-check determinista** (barato: ``get_policy_info``, sin RAG
       narrativo ni LLM): aplica ``deterministic_check()`` con la política
       estructurada de la categoría. Los artículos con veredicto
       ``"invalid"`` quedan decididos aquí mismo — is_eligible=False,
       ``eligibility_reason`` = la plantilla determinista — porque NINGÚN
       contexto adicional (RAG narrativo o razonamiento del LLM) puede
       cambiar ese veto, así que pagarlo no tendría ningún efecto en el
       resultado (comprobado empíricamente: ver §4.2).
    2. **Evaluación LLM** (solo para los artículos que el pre-check deja en
       zona gris, veredicto ``"valid"``/``"human_review"``): búsqueda RAG
       narrativa (una consulta por categoría distinta entre esos artículos
       pendientes) + una única llamada al LLM de salida estructurada
       (``PolicyEvaluationOutput``) para decidir esos casos.

    Si el pre-check ya decide TODOS los artículos (caso común: solicitud de
    un solo artículo con veto claro), la función devuelve sin hacer ninguna
    búsqueda RAG ni llamar al LLM en absoluto.
    """
    order_details = state.get("order_details", {})
    return_history = state.get("return_history", {})
    reason = state.get("reason", "")
    reason_category = state.get("reason_category", "")
    items_to_return = state.get("items_to_return", [])

    product_names = _product_name_by_item_id(order_details)
    product_categories = _category_by_item_id(order_details)
    order_items_raw = order_details.get("items", [])
    approved_returns = return_history.get("approved", 0)
    # Ya viene calculado desde get_order_details() (MCP) -- ver
    # orders_service.get_order_details(); evita que este nodo tenga que
    # importar backend.services directamente (ver defenderMCP.md).
    days_since_order = order_details.get("order", {}).get("days_since_delivery", 9999)

    # ── FASE 1: pre-check determinista, barato (sin RAG narrativo) ──────
    # Una consulta a get_policy_info() por categoría DISTINTA — no hace
    # embedding ni búsqueda vectorial, solo lee la fila estructurada de
    # return_policies (plazo, condiciones admitidas, recargo).
    policy_info_by_category: dict[str, Any] = {}
    predetermined: dict[str, dict[str, Any]] = (
        {}
    )  # order_item_id -> ya decidido (invalid)
    pending_items: list[dict[str, Any]] = []  # necesitan RAG narrativo + LLM
    pending_verdicts: dict[str, tuple[str, list[str], float]] = {}

    for item in items_to_return:
        oid = item.get("order_item_id")
        category = product_categories.get(oid, "")

        if category and category not in policy_info_by_category:
            policy_info_by_category[category] = await get_policy_info(category)

        policy_info = policy_info_by_category.get(category) or {}
        restocking_fee = policy_info.get("restocking_fee_percent") or 0.0
        refund = compute_refund(order_items_raw, [item], restocking_fee)

        verdict, reasons = deterministic_check(
            days_since_order=days_since_order,
            max_return_days=policy_info.get("max_return_days"),
            allowed_conditions=policy_info.get("allowed_conditions"),
            condition=item.get("condition", "unknown"),
            category=category,
            reason_category=reason_category,
            refund_amount=refund,
            approved_returns=approved_returns,
        )

        if verdict == "invalid":
            predetermined[oid] = {
                "order_item_id": oid,
                "is_eligible": False,
                "eligibility_reason": " | ".join(reasons),
                "refund_amount": 0.0,
                "policy_category": category,
            }
        else:
            pending_items.append(item)
            pending_verdicts[oid] = (verdict, reasons, refund)

    updates: dict[str, Any] = {"current_agent": "evaluator"}

    # ── Corte temprano: si el pre-check ya decidió TODOS los artículos,
    #    ni la búsqueda RAG narrativa ni la llamada al LLM cambiarían nada
    #    (todos son vetos "invalid") — no se ejecutan en absoluto. ───────
    if not pending_items:
        items_eligibility = [
            predetermined[item.get("order_item_id")] for item in items_to_return
        ]
        updates["policy_info"] = policy_info_by_category
        updates["items_eligibility"] = items_eligibility
        updates["any_eligible"] = False
        updates["refund_amount"] = 0.0
        updates["needs_admin_approval"] = False
        updates["eligibility_reason"] = _eligibility_summary(
            items_eligibility, product_names
        )
        return updates

    llm = _build_llm()

    # ── FASE 2: búsqueda RAG narrativa — solo para las categorías DISTINTAS
    #    presentes entre los artículos pendientes (no todos los del pedido) ──
    policy_by_category: dict[str, Any] = {}
    for item in pending_items:
        category = product_categories.get(item.get("order_item_id"), "")
        if category and category not in policy_by_category:
            raw_policy = await search_return_policy(
                query=_build_rag_query(
                    category, reason_category, item.get("condition", "")
                ),
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

    # ── Construir contexto por artículo pendiente para el LLM ────────────
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
        for item in pending_items
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

    # NO se incluye el historial de chat (state["messages"]): el Evaluador
    # es un subagente de auditoría, no "quien habla con el usuario" (ese es
    # triage.py, que sí necesita el hilo — ver backend/agents/llm_factory.py
    # trim_history). El `context` de arriba ya es autosuficiente (pedido,
    # motivo, historial de devoluciones, artículos con su política); pasar
    # además el chat crudo sería contexto redundante que solo añade tokens
    # sin aportar nada a la decisión de política. Contexto aislado por
    # subtarea (ver session_4/README.md, "Por qué aislar el contexto").
    messages = [
        SystemMessage(content=POLICY_SYSTEM_PROMPT),
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

    updates["policy_info"] = policy_by_category

    if result is None or not result.items:
        logger.warning(
            "Evaluador: structured output vacío o None; se marca todo como no elegible."
        )
        fallback_reason = "No se pudo evaluar la política correctamente."
        llm_eligibility: dict[str, dict[str, Any]] = {
            item.get("order_item_id"): {
                "order_item_id": item.get("order_item_id"),
                "is_eligible": False,
                "eligibility_reason": fallback_reason,
                "refund_amount": 0.0,
                "policy_category": product_categories.get(
                    item.get("order_item_id"), ""
                ),
            }
            for item in pending_items
        }
    else:
        llm_eligibility = {
            item.order_item_id: item.model_dump() for item in result.items
        }

    # ── Reglas deterministas (policy_rules.py), ya calculadas en la FASE 1:
    #    fijan el importe exacto del reembolso y marcan revisión humana. El
    #    LLM aporta el razonamiento en lenguaje natural (eligibility_reason)
    #    y decide is_eligible para estos artículos en zona gris, pero NUNCA
    #    puede decidir la aritmética del reembolso — refund_amount siempre
    #    sale de compute_refund(), nunca del LLM. Un veredicto
    #    "human_review" no cambia is_eligible (lo decide el LLM/HITL), solo
    #    marca needs_admin_approval a nivel de solicitud. (El veredicto
    #    "invalid" ya se resolvió en la FASE 1 — nunca aparece aquí.)
    any_needs_review = False

    for oid, item_eligibility in llm_eligibility.items():
        verdict, reasons, refund = pending_verdicts.get(oid, ("valid", [], 0.0))

        item_eligibility["refund_amount"] = (
            refund if item_eligibility.get("is_eligible") else 0.0
        )
        if verdict == "human_review":
            any_needs_review = True
            logger.info(
                "Evaluador: artículo %s marcado para revisión humana: %s",
                oid,
                "; ".join(reasons),
            )

    # ── Combinar lo decidido en la FASE 1 (predetermined) con lo decidido
    #    en la FASE 2 (llm_eligibility), preservando el orden original de
    #    items_to_return. ──────────────────────────────────────────────
    items_eligibility = [
        predetermined.get(item.get("order_item_id"))
        or llm_eligibility.get(item.get("order_item_id"))
        for item in items_to_return
    ]

    updates["items_eligibility"] = items_eligibility
    updates["any_eligible"] = any(item["is_eligible"] for item in items_eligibility)
    updates["refund_amount"] = sum(
        item["refund_amount"] for item in items_eligibility if item["is_eligible"]
    )
    updates["needs_admin_approval"] = any_needs_review
    updates["eligibility_reason"] = _eligibility_summary(
        items_eligibility, product_names
    )

    return updates
