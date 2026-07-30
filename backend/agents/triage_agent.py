"""
Agente de Triaje y Empatía.

Primer punto de contacto con el cliente. Se encarga de:
1. Saludar y empatizar con el usuario.
2. Comprender el motivo de insatisfacción.
3. Extraer parámetros clave (order_id, razón, artículos) de forma conversacional.
4. Consultar los detalles del pedido en Supabase.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from backend.agents.state import ReturnState
from backend.agents.mcp_client import get_order_details, get_customer_return_history

logger = logging.getLogger(__name__)

# ── Prompt del sistema ─────────────────────────────────────────────────────

TRIAGE_SYSTEM_PROMPT = """\
Eres ReFlow, un asistente de atención al cliente especializado en devoluciones.
Tu rol es el de **Agente de Triaje y Empatía**: el primer punto de contacto.

## Objetivos
1. Saludar amablemente y mostrar empatía por la situación del cliente.
2. Entender el motivo de la devolución.
3. Extraer la siguiente información de forma conversacional (NO interrogatorio):
   - **order_id**: UUID del pedido (el cliente lo tiene en su email de confirmación).
   - **reason**: motivo de la devolución en texto libre.
   - **reason_category**: una de [defective, wrong_item, not_as_described, no_longer_needed, arrived_late, other].
   - **items_to_return**: lista de artículos con formato [{"order_item_id": "...", "quantity": 1, "condition": "..."}].
     Las condiciones posibles son: unopened, defective, damaged, used, wrong_item.

## Reglas
- Sé empático, cálido y profesional. Usa español.
- Si el cliente no proporciona el order_id, pídelo amablemente.
- Si falta información, pregunta de forma natural (una cosa a la vez).
- Cuando tengas TODA la información necesaria, responde con un JSON al final de tu mensaje
  dentro de un bloque ```json ... ``` con las claves: order_id, reason, reason_category, items_to_return.
- NO inventes datos. Si no tienes algo, pregunta.
- Si el cliente tiene un problema que NO es una devolución, indícale amablemente
  que solo puedes ayudar con devoluciones.
"""


def _build_llm() -> ChatOpenAI:
    """Construye el LLM para el agente de triaje."""
    return ChatOpenAI(
        model="gpt-5-nano",
        temperature=0.3,
        max_tokens=1024,
    )


def _extract_json_from_response(content: str) -> dict[str, Any] | None:
    """Intenta extraer un bloque JSON del contenido de la respuesta del LLM."""
    pattern = r"```json\s*(.*?)\s*```"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.warning("No se pudo parsear el JSON extraído del triaje.")
    return None


async def triage_agent(state: ReturnState) -> dict[str, Any]:
    """Nodo del agente de Triaje y Empatía.

    Lee los ``messages`` del estado, invoca al LLM y decide si ya tiene
    suficiente información para avanzar al Evaluador de Políticas.
    """
    llm = _build_llm()

    # Construir la lista de mensajes para el LLM
    system = SystemMessage(content=TRIAGE_SYSTEM_PROMPT)
    llm_messages = [system, *state.get("messages", [])]

    response = await llm.ainvoke(llm_messages)

    # Intentar extraer datos estructurados de la respuesta
    extracted = _extract_json_from_response(response.content)

    updates: dict[str, Any] = {
        "messages": [response],
        "current_agent": "triage",
    }

    if extracted:
        updates["order_id"] = extracted.get("order_id")
        updates["reason"] = extracted.get("reason")
        updates["reason_category"] = extracted.get("reason_category")
        updates["items_to_return"] = extracted.get("items_to_return", [])

    return updates


async def fetch_order_data(state: ReturnState) -> dict[str, Any]:
    """Nodo auxiliar que consulta los detalles del pedido en Supabase.

    Se ejecuta después del triaje, cuando ya tenemos el ``order_id``.
    Utiliza las herramientas MCP de ``mcp_supabase`` directamente.
    """
    order_id = state.get("order_id")
    if not order_id:
        return {"error": "No se proporcionó order_id."}

    try:
        order_details = await get_order_details(order_id)
        customer_id = order_details["order"]["customer"]["id"]
        customer_name = order_details["order"]["customer"]["full_name"]
        customer_email = order_details["order"]["customer"]["email"]

        return_history = await get_customer_return_history(customer_id)

        return {
            "order_details": order_details,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "return_history": return_history,
        }
    except Exception as exc:
        logger.error("Error al consultar datos del pedido: %s", exc)
        return {
            "error": f"No se pudo recuperar el pedido {order_id}. Verifica que el ID sea correcto.",
            "messages": [
                AIMessage(
                    content=(
                        f"Lo siento, no he podido encontrar el pedido con ID `{order_id}`. "
                        "¿Podrías verificar que el identificador sea correcto?"
                    )
                )
            ],
        }
