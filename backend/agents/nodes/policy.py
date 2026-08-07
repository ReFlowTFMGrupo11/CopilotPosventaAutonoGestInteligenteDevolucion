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
    updates: dict[str, Any] = {
        "messages": [response],
        "current_agent": "evaluator",
        "policy_info": policy_results,
    }

    # re.DOTALL: hace que "." también capture saltos de línea, necesario
    # porque el bloque JSON del LLM ocupa varias líneas.
    match = re.search(r"```json\s*(.*?)\s*```", response.content, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            updates["is_eligible"] = result.get("is_eligible", False)
            updates["eligibility_reason"] = result.get("eligibility_reason", "")
            updates["refund_amount"] = float(result.get("refund_amount", 0.0))
        except (json.JSONDecodeError, ValueError) as exc:
            # El LLM incluyó un bloque ```json``` pero con contenido
            # inválido (JSON roto o refund_amount no numérico): se falla
            # "seguro" tratando el caso como no elegible.
            logger.warning("Error parseando resultado del evaluador: %s", exc)
            updates["is_eligible"] = False
            updates["eligibility_reason"] = "Error interno al evaluar la política."
    else:
        # El LLM no incluyó ningún bloque ```json``` en absoluto: mismo
        # fallback "seguro" (rechazar) que en el caso anterior.
        updates["is_eligible"] = False
        updates["eligibility_reason"] = "No se pudo evaluar la política correctamente."

    return updates
