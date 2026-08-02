"""
Agente de Triaje y Empatía.

Primer punto de contacto con el cliente. Se encarga de:
1. Saludar y empatizar con el usuario.
2. Comprender el motivo de insatisfacción.
3. Extraer parámetros clave (order_id, razón, artículos) de forma conversacional.
4. Consultar los detalles del pedido en Supabase.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

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
- Cuando tengas TODA la información necesaria, rellena todos los campos.
- NO inventes datos. Si no tienes algo, déjalo como null.
- Si el cliente tiene un problema que NO es una devolución, indícale amablemente
  que solo puedes ayudar con devoluciones.
- SIEMPRE rellena response_to_customer con tu respuesta empática al cliente.
"""


# ── Modelo de salida estructurada ──────────────────────────────────────────


class TriageOutput(BaseModel):
    """Salida estructurada del agente de triaje."""

    response_to_customer: str = Field(
        description="Respuesta empática a mostrar al cliente en este turno."
    )
    order_id: Optional[str] = Field(
        default=None,
        description="UUID del pedido. None si el cliente aún no lo ha proporcionado.",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Motivo de la devolución en palabras del cliente.",
    )
    reason_category: Optional[str] = Field(
        default=None,
        description="Categoría: defective, wrong_item, not_as_described, no_longer_needed, arrived_late, other.",
    )
    items_to_return: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Lista de artículos a devolver con order_item_id, quantity, condition.",
    )


def _build_llm() -> ChatOpenAI:
    """Construye el LLM para el agente de triaje con salida estructurada."""
    return ChatOpenAI(
        model="gpt-5-nano",
        temperature=0.3,
        max_tokens=1024,
    )


async def triage_agent(state: ReturnState) -> dict[str, Any]:
    """Nodo del agente de Triaje y Empatía.

    Lee los ``messages`` del estado, invoca al LLM con structured output
    (Pydantic) para garantizar un schema válido en cada respuesta.
    """
    llm = _build_llm()
    llm_structured = llm.with_structured_output(TriageOutput)

    # Construir la lista de mensajes para el LLM
    system = SystemMessage(content=TRIAGE_SYSTEM_PROMPT)
    llm_messages = [system, *state.get("messages", [])]

    result: TriageOutput = await llm_structured.ainvoke(llm_messages)

    updates: dict[str, Any] = {
        "messages": [AIMessage(content=result.response_to_customer)],
        "current_agent": "triage",
    }

    if result.order_id:
        updates["order_id"] = result.order_id
    if result.reason:
        updates["reason"] = result.reason
    if result.reason_category:
        updates["reason_category"] = result.reason_category
    if result.items_to_return:
        updates["items_to_return"] = result.items_to_return

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
