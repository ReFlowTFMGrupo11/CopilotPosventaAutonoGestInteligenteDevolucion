"""
Agente de Triaje y Empatía.

Primer punto de contacto con el cliente. Se encarga de:
1. Saludar y empatizar con el usuario.
2. Comprender el motivo de insatisfacción.
3. Extraer parámetros clave (order_number, razón, artículos) de forma conversacional.
4. Consultar los detalles del pedido en Supabase.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI

from backend.agents.state import ReturnState
from backend.agents.infra.mcp_client import get_order_details, get_customer_return_history

logger = logging.getLogger(__name__)

# ── Prompt del sistema ─────────────────────────────────────────────────────

TRIAGE_SYSTEM_PROMPT = """\
Eres ReFlow, un asistente de atención al cliente especializado en devoluciones.
Tu rol es el de **Agente de Triaje y Empatía**: el primer punto de contacto.

## Objetivos
1. Saludar amablemente y mostrar empatía por la situación del cliente.
2. Entender el motivo de la devolución.
3. Extraer la siguiente información de forma conversacional (NO interrogatorio):
   - **order_number**: número de pedido (el cliente lo tiene en su email de confirmación,
     formato "ORD-2026-00177"). NUNCA le pidas un UUID.
   - **reason**: motivo de la devolución en texto libre.
   - **reason_category**: una de [defective, wrong_item, not_as_described, no_longer_needed, arrived_late, other].
   - **items_to_return**: lista de artículos con formato [{"order_item_id": "...", "quantity": 1, "condition": "..."}].
     Las condiciones posibles son: unopened, defective, damaged, used, wrong_item.

## Artículos del pedido (order_item_id)
- El cliente identifica el artículo por su NOMBRE, nunca por un ID técnico.
- Si el contexto incluye un mensaje "ARTÍCULOS DEL PEDIDO", cruza lo que dice el
  cliente con esa lista y usa el "id" de la línea que corresponda como order_item_id.
- Si ese contexto todavía no existe, no puedes rellenar items_to_return: limítate a
  pedir el order_number primero.

## Reglas
- Sé empático, cálido y profesional. Usa español.
- Si el cliente no proporciona el order_number, pídelo amablemente.
- Si ya conoces el order_number (aparece en el contexto), no lo vuelvas a pedir.
- Si falta información, pregunta de forma natural (una cosa a la vez).
- Cuando tengas TODA la información necesaria, rellena todos los campos.
- NO inventes datos. Si no tienes algo, déjalo como null.
- Si el cliente tiene un problema que NO es una devolución, indícale amablemente
  que solo puedes ayudar con devoluciones.
- SIEMPRE rellena response_to_customer con tu respuesta empática al cliente.
"""


# ── Modelos ────────────────────────────────────────────────────────────────

from backend.models import TriageOutput


def _build_llm() -> ChatOpenAI:
    """Construye el LLM para el agente de triaje con salida estructurada."""
    return ChatOpenAI(
        model="gpt-5-nano",
        temperature=0,
        max_tokens=4096,
    )


async def triage_agent(state: ReturnState) -> dict[str, Any]:
    """Nodo del agente de Triaje y Empatía.

    Lee los ``messages`` del estado, invoca al LLM con structured output
    (Pydantic) para garantizar un schema válido en cada respuesta.
    """
    llm = _build_llm()
    llm_structured = llm.with_structured_output(TriageOutput)

    # Construir la lista de mensajes para el LLM
    context = [SystemMessage(content=TRIAGE_SYSTEM_PROMPT)]
    if state.get("order_number"):
        context.append(SystemMessage(content=f"order_number ya conocido: {state['order_number']}"))
    if state.get("order_details"):
        items = state["order_details"].get("items", [])
        context.append(SystemMessage(content=f"ARTÍCULOS DEL PEDIDO: {json.dumps(items, default=str, ensure_ascii=False)}"))
    llm_messages = [*context, *state.get("messages", [])]

    result: TriageOutput | None = await llm_structured.ainvoke(llm_messages)

    if result is None:
        # Fallback: el LLM no generó structured output válido
        logger.warning("Triaje: structured output devolvió None, usando fallback.")
        return {
            "messages": [AIMessage(content="Lo siento, no he podido procesar tu mensaje. ¿Podrías repetirlo?")],
            "current_agent": "triage",
        }

    updates: dict[str, Any] = {
        "messages": [AIMessage(content=result.response_to_customer)],
        "current_agent": "triage",
    }

    if result.order_number:
        updates["order_number"] = result.order_number
    if result.reason:
        updates["reason"] = result.reason
    if result.reason_category:
        updates["reason_category"] = result.reason_category
    if result.items_to_return:
        updates["items_to_return"] = [item.model_dump() for item in result.items_to_return]

    return updates


async def fetch_order_data(state: ReturnState) -> dict[str, Any]:
    """Nodo auxiliar que consulta los detalles del pedido en Supabase.

    Se ejecuta después del triaje, cuando ya tenemos el ``order_number``. Si
    todavía no sabemos qué artículo quiere devolver el cliente, muestra los
    artículos del pedido y pregunta, en vez de exigirle un ID técnico.
    """
    order_number = state.get("order_number")
    if not order_number:
        return {"error": "No se proporcionó order_number."}

    try:
        raw_order = await get_order_details(order_number)
        # MCP devuelve lista de content blocks: [{"type": "text", "text": "{...}"}]
        if isinstance(raw_order, list):
            order_details = json.loads(raw_order[0]["text"])
        else:
            order_details = raw_order

        order_id = order_details["order"]["id"]
        customer_id = order_details["order"]["customer"]["id"]
        customer_name = order_details["order"]["customer"]["full_name"]
        customer_email = order_details["order"]["customer"]["email"]

        raw_history = await get_customer_return_history(customer_id)
        if isinstance(raw_history, list):
            return_history = json.loads(raw_history[0]["text"])
        else:
            return_history = raw_history

        updates: dict[str, Any] = {
            "order_id": order_id,
            "order_details": order_details,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "return_history": return_history,
        }

        # Primera vez que vemos este pedido: aún no sabemos qué artículo
        # devolver.
        if not state.get("items_to_return"):
            items = order_details.get("items", [])
            if len(items) == 1:
                # Solo un artículo → seleccionarlo automáticamente
                single = items[0]
                product_name = (single.get("product") or {}).get("name", "Artículo")
                updates["items_to_return"] = [{
                    "order_item_id": single["id"],
                    "quantity": single.get("quantity", 1),
                    "condition": "unknown",
                }]
                updates["messages"] = [
                    AIMessage(
                        content=(
                            f"He encontrado tu pedido {order_number} con el artículo "
                            f"**{product_name}** ({single.get('unit_price')}€). "
                            f"¿Cuál es el motivo de la devolución?"
                        )
                    )
                ]
            else:
                items_text = "\n".join(
                    f"- {(item.get('product') or {}).get('name', 'Artículo')} "
                    f"(cantidad: {item.get('quantity', 1)}, precio: {item.get('unit_price')}€)"
                    for item in items
                ) or "(no se encontraron artículos en este pedido)"
                updates["messages"] = [
                    AIMessage(
                        content=(
                            f"He encontrado tu pedido {order_number}. Estos son los artículos:\n"
                            f"{items_text}\n\n¿Cuál quieres devolver y por qué motivo?"
                        )
                    )
                ]

        return updates
    except Exception as exc:
        logger.error("Error al consultar datos del pedido: %s", exc)
        return {
            "error": f"No se pudo recuperar el pedido {order_number}.",
            "messages": [
                AIMessage(
                    content=(
                        f"Lo siento, no he podido encontrar el pedido con número `{order_number}`. "
                        "¿Podrías verificar que sea correcto?"
                    )
                )
            ],
        }
