"""
Agente Evaluador de Políticas.

Actúa como auditor. Consulta:
1. El historial del pedido (datos ya cargados en el estado).
2. La base vectorial de normas (RAG via ``search_return_policy``).

Verifica de forma estricta si la devolución es elegible basándose en:
- Plazos de devolución según categoría.
- Estado del producto.

No decide aquí si el caso necesita revisión humana (HITL) más allá de la
elegibilidad — eso (zona frontera del plazo, motivo sensible, historial de
abuso, importe > 100€) lo evalúa resolution.py de forma determinista, no
este LLM (ver dataset/policies/00_marco_general_devoluciones.md, sección 5).
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

# A diferencia del triaje (structured output nativo), aquí se le pide al
# LLM que devuelva el JSON dentro de un bloque ```json ... ``` en texto
# libre; más abajo (policy_evaluator_agent) ese bloque se extrae con regex.
POLICY_SYSTEM_PROMPT = """\
Eres un **Agente Evaluador de Políticas** de devoluciones de ReFlow.
Tu trabajo es determinar de forma objetiva y estricta si una devolución es elegible.

## Datos que recibirás
- Detalles del pedido (productos, fecha, estado).
- Historial de devoluciones del cliente.
- Políticas de devolución relevantes (resultados RAG).
- Motivo y artículos que el cliente quiere devolver.

## Criterios de evaluación (elegibilidad)
1. **Plazo**: ¿Han pasado más días de los permitidos por la política de la categoría?
2. **Estado del producto**: ¿La condición del artículo está dentro de las condiciones permitidas?
3. **Embalaje original**: ¿Se requiere y el cliente lo tiene?

NO evalúes aquí el historial de devoluciones del cliente, si el motivo es
sensible (reacción alérgica, sospecha de falsificación) ni si la fecha está
en zona frontera del plazo: esas señales NO cambian si la devolución es
elegible o no, solo si además debe pasar por revisión humana — eso lo
decide un paso Python posterior (ver resolution.py), no tú.

## Formato de respuesta
Responde SIEMPRE con un bloque JSON ```json ... ``` con las siguientes claves:
- **is_eligible** (bool): si la devolución es elegible.
- **eligibility_reason** (str): explicación detallada de la decisión.
- **refund_amount** (float): monto del reembolso (0 si no elegible).
  Si aplica restocking_fee, descuéntalo del precio.
- **policy_applied** (dict): resumen de la política aplicada.

Sé objetivo e imparcial. Basa tu decisión EXCLUSIVAMENTE en las políticas y datos.
"""


def _build_llm() -> ChatOpenAI:
    """Construye el LLM para el evaluador de políticas."""
    return ChatOpenAI(
        model="gpt-5-nano",
        # temperature=0.0: máxima consistencia, deseable en un agente cuyas
        # decisiones deben poder auditarse (mismo caso → misma decisión).
        temperature=0.0,  # Determinista para auditoría
        max_tokens=4096,
    )


def _calculate_refund_amount(order_details: dict, items_to_return: list[dict]) -> float:
    """Suma el importe a reembolsar en Python puro, a partir de las líneas
    reales del pedido — nunca del número que el LLM haya podido escribir en
    su bloque JSON.

    Mismo motivo que ``_sum_refund_amount`` en
    ``archived/agente2ConMCP/agente_evaluacion.py``: este importe alimenta
    directamente el corte HITL (``resolution.py::HITL_REFUND_THRESHOLD``),
    así que no puede depender de que el LLM copie o sume bien los precios.
    """
    order_items_by_id = {
        oi.id: oi
        for oi in (OrderItem.model_validate(raw) for raw in order_details.get("items", []))
        if oi.id
    }

    total = 0.0
    for item in items_to_return:
        oi = order_items_by_id.get(item.get("order_item_id"))
        if oi is None:
            # Artículo que el cliente quiere devolver pero que no aparece en
            # el pedido consultado: no se puede saber su precio, se ignora
            # en vez de asumir un importe arbitrario.
            continue
        quantity = item.get("quantity") or 1
        if oi.unit_price is not None:
            total += float(oi.unit_price) * float(quantity)
        elif oi.total_price is not None:
            # Sin unit_price no se puede prorratear por cantidad devuelta;
            # se usa el total de la línea completa como aproximación.
            total += float(oi.total_price)

    return round(total, 2)


async def policy_evaluator_agent(state: ReturnState) -> dict[str, Any]:
    """Nodo del agente Evaluador de Políticas.

    Consulta las políticas via RAG y evalúa la elegibilidad.
    """
    llm = _build_llm()

    # Se leen del estado compartido los datos ya recopilados por los nodos
    # anteriores (triage_agent y fetch_order_data).
    order_details = state.get("order_details", {})
    return_history = state.get("return_history", {})
    reason = state.get("reason", "")
    reason_category = state.get("reason_category", "")
    items_to_return = state.get("items_to_return", [])

    # ── Obtener la categoría del primer artículo para buscar la política ──
    product_category = ""
    order_items = order_details.get("items", [])
    if order_items and items_to_return:
        # Recorre las líneas del pedido y se queda con la categoría del
        # primer producto que tenga una: se asume (simplificación) que basta
        # con la categoría de un artículo para buscar la política aplicable.
        for raw_item in order_items:
            # model_validate: valida/parsea el dict crudo de Supabase contra
            # el modelo Pydantic OrderItem (lanza error si falta algo esencial).
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
    # Mismo patrón de desenvolver la respuesta MCP que en triage.py.
    if isinstance(raw_policy, list) and raw_policy and "text" in raw_policy[0]:
        text = raw_policy[0]["text"]
        try:
            policy_results = json.loads(text)
        except json.JSONDecodeError:
            # Si el texto no es JSON válido, no se aborta: se guarda el
            # texto crudo bajo "error" para poder depurarlo después.
            logger.warning("RAG policy no devolvió JSON válido: %s", text[:200])
            policy_results = {"error": text}
    else:
        policy_results = raw_policy

    # Calcula cuántos días han pasado desde la entrega, dato clave para
    # comprobar si se ha superado el plazo de devolución de la categoría.
    days_since_order = calculate_days_since_delivery(order_details)

    # ── Construir contexto para el LLM ─────────────────────────────────
    # Se arma un bloque de texto en Markdown con TODOS los datos relevantes
    # (pedido, artículos, motivo, historial, políticas) para que el LLM
    # razone sobre ellos como si fuera un expediente completo.
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
"""

    # El contexto se envía como un SystemMessage adicional AL FINAL de la
    # lista, después del historial de conversación, para que el LLM lo
    # tenga fresco justo antes de decidir.
    messages = [
        SystemMessage(content=POLICY_SYSTEM_PROMPT),
        *state.get("messages", []),
        SystemMessage(content=f"CONTEXTO DE EVALUACIÓN:\n{context}"),
    ]

    response = await llm.ainvoke(messages)

    # ── Extraer resultado estructurado ─────────────────────────────────
    # Se guarda ya la respuesta completa del LLM en el historial y policy_info
    # en el estado; is_eligible/eligibility_reason/refund_amount se rellenan
    # más abajo tras parsear el bloque JSON.
    # policy_max_return_days: viene de la política estructurada del RAG, no
    # de los "semantic_results" de texto libre. days_since_delivery y este
    # campo se reexponen en el estado porque resolution.py los necesita
    # para detectar la "zona frontera" del plazo (ver más abajo, HITL).
    policy_max_return_days = None
    if isinstance(policy_results, dict):
        policy_max_return_days = (policy_results.get("policy_info") or {}).get("max_return_days")

    updates: dict[str, Any] = {
        "messages": [response],
        "current_agent": "evaluator",
        "policy_info": policy_results,
        "days_since_delivery": days_since_order,
        "policy_max_return_days": policy_max_return_days,
    }

    # re.DOTALL: hace que "." también capture saltos de línea, necesario
    # porque el bloque JSON del LLM ocupa varias líneas.
    match = re.search(r"```json\s*(.*?)\s*```", response.content, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            updates["is_eligible"] = result.get("is_eligible", False)
            updates["eligibility_reason"] = result.get("eligibility_reason", "")
        except json.JSONDecodeError as exc:
            # El LLM incluyó un bloque ```json``` pero con contenido
            # inválido (JSON roto): se falla "seguro" tratando el caso
            # como no elegible.
            logger.warning("Error parseando resultado del evaluador: %s", exc)
            updates["is_eligible"] = False
            updates["eligibility_reason"] = "Error interno al evaluar la política."
    else:
        # El LLM no incluyó ningún bloque ```json``` en absoluto: mismo
        # fallback "seguro" (rechazar) que en el caso anterior.
        updates["is_eligible"] = False
        updates["eligibility_reason"] = "No se pudo evaluar la política correctamente."

    # refund_amount NUNCA se toma del número que escriba el LLM: se recalcula
    # siempre en Python a partir de los importes reales del pedido
    # (order_details), igual que archived/agente2ConMCP/agente_evaluacion.py
    # ::_sum_refund_amount. Alimenta directamente el corte HITL de
    # resolution.py (HITL_REFUND_THRESHOLD), así que no puede depender de
    # que el LLM copie o sume bien los precios.
    updates["refund_amount"] = (
        _calculate_refund_amount(order_details, items_to_return) if updates["is_eligible"] else 0.0
    )

    return updates
