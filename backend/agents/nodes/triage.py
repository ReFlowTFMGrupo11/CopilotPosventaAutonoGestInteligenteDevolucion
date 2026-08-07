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
from typing import Any

# AIMessage: mensaje "del asistente" que se añade al historial de la conversación.
# SystemMessage: instrucción de sistema (prompt) que no forma parte del diálogo visible.
from langchain_core.messages import AIMessage, SystemMessage
# ChatOpenAI: wrapper de LangChain sobre la API de chat de OpenAI.
from langchain_openai import ChatOpenAI

from backend.agents.state import ReturnState
# Funciones que llaman, vía MCP, al servidor de Supabase para traer el
# pedido y el historial de devoluciones del cliente.
from backend.agents.infra.mcp_client import get_order_details, get_customer_return_history

logger = logging.getLogger(__name__)

# ── Prompt del sistema ─────────────────────────────────────────────────────

# Prompt fijo que define el "rol" y las reglas de comportamiento del LLM en
# este nodo; se envía en cada invocación junto con el historial de mensajes.
TRIAGE_SYSTEM_PROMPT = """\
Eres ReFlow, un asistente de atención al cliente especializado en devoluciones.
Tu rol es el de **Agente de Triaje y Empatía**: el primer punto de contacto.

## Objetivos
1. Saludar amablemente y mostrar empatía por la situación del cliente.
2. Entender el motivo de la devolución.
3. Extraer la siguiente información de forma conversacional (NO interrogatorio):
   - **order_id**: UUID del pedido (el cliente lo tiene en su email de confirmación).
   - **reason**: motivo de la devolución en texto libre.
   - **reason_category**: una de las categorías cerradas de
     dataset/policies/00_marco_general_devoluciones.md (sección 3):
     defective, wrong_item_shipped, wrong_size, not_as_described,
     damaged_in_transit, missing_parts, changed_mind, duplicate_order,
     arrived_late, better_price_found, allergic_reaction, quality_issue,
     assembly_issue, incompatible, counterfeit_suspicion.
     IMPORTANTE: allergic_reaction (reacción alérgica) y
     counterfeit_suspicion (sospecha de falsificación) disparan SIEMPRE
     revisión humana obligatoria (ver resolution.py) — extráelas con la
     misma naturalidad que el resto, no las evites ni las suavices a otra
     categoría.
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


# ── Modelos ────────────────────────────────────────────────────────────────

# Modelos Pydantic que definen la forma exacta que debe tener la respuesta
# del LLM (ver backend/models/returns.py).
from backend.models import ReturnItem, TriageOutput


def _build_llm() -> ChatOpenAI:
    """Construye el LLM para el agente de triaje con salida estructurada."""
    # temperature=0: respuestas deterministas (poca variación creativa),
    # apropiado para un agente que debe extraer datos con precisión.
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
    # with_structured_output(TriageOutput): en vez de devolver texto libre,
    # el LLM está obligado a devolver un objeto que cumpla el schema de
    # TriageOutput (campos y tipos fijos) — evita tener que parsear texto.
    llm_structured = llm.with_structured_output(TriageOutput)

    # Construir la lista de mensajes para el LLM
    # Se antepone el prompt de sistema al historial de conversación real
    # acumulado en el estado (mensajes previos del cliente y del asistente).
    system = SystemMessage(content=TRIAGE_SYSTEM_PROMPT)
    llm_messages = [system, *state.get("messages", [])]

    # ainvoke(): llamada asíncrona al LLM; devuelve directamente una
    # instancia de TriageOutput (o None si no pudo generar salida válida).
    result: TriageOutput | None = await llm_structured.ainvoke(llm_messages)

    if result is None:
        # Fallback: el LLM no generó structured output válido
        # Caso raro pero posible (fallo de red, respuesta cortada...): se
        # responde algo genérico en vez de dejar el turno sin respuesta.
        logger.warning("Triaje: structured output devolvió None, usando fallback.")
        return {
            "messages": [AIMessage(content="Lo siento, no he podido procesar tu mensaje. ¿Podrías repetirlo?")],
            "current_agent": "triage",
        }

    # Diccionario de actualizaciones que este nodo devuelve a LangGraph; solo
    # estas claves del estado se sobrescriben (el resto queda intacto).
    updates: dict[str, Any] = {
        "messages": [AIMessage(content=result.response_to_customer)],
        "current_agent": "triage",
    }

    # Cada campo solo se añade a "updates" si el LLM lo rellenó (no es None):
    # así, si en este turno el cliente no dio el order_id, no se sobrescribe
    # con None el order_id que ya se hubiera capturado en un turno anterior.
    if result.order_id:
        updates["order_id"] = result.order_id
    if result.reason:
        updates["reason"] = result.reason
    if result.reason_category:
        updates["reason_category"] = result.reason_category
    if result.items_to_return:
        # .model_dump(): convierte cada ReturnItem (objeto Pydantic) a dict
        # plano, porque ReturnState.items_to_return se define como list[dict].
        updates["items_to_return"] = [item.model_dump() for item in result.items_to_return]

    return updates


async def fetch_order_data(state: ReturnState) -> dict[str, Any]:
    """Nodo auxiliar que consulta los detalles del pedido en Supabase.

    Se ejecuta después del triaje, cuando ya tenemos el ``order_id``.
    Utiliza las herramientas MCP de ``mcp_supabase`` directamente.
    """
    order_id = state.get("order_id")
    if not order_id:
        # Salvaguarda: en la práctica el grafo solo llega a este nodo cuando
        # route_after_triage ya comprobó que hay order_id, pero se protege
        # igualmente por si se invoca este nodo desde otro lugar (tests...).
        return {"error": "No se proporcionó order_id."}

    try:
        raw_order = await get_order_details(order_id)
        # MCP devuelve lista de content blocks: [{"type": "text", "text": "{...}"}]
        # El protocolo MCP envuelve las respuestas de las tools en una lista
        # de "bloques de contenido"; aquí se desenvuelve para quedarse con
        # el JSON real (parseándolo desde el campo "text").
        if isinstance(raw_order, list):
            order_details = json.loads(raw_order[0]["text"])
        else:
            order_details = raw_order

        # Se extraen del pedido los datos del cliente para no tener que
        # volver a consultarlos más adelante en el grafo.
        customer_id = order_details["order"]["customer"]["id"]
        customer_name = order_details["order"]["customer"]["full_name"]
        customer_email = order_details["order"]["customer"]["email"]

        raw_history = await get_customer_return_history(customer_id)
        if isinstance(raw_history, list):
            return_history = json.loads(raw_history[0]["text"])
        else:
            return_history = raw_history

        return {
            "order_details": order_details,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "return_history": return_history,
        }
    except Exception as exc:
        # Captura amplia deliberada: cualquier fallo (pedido inexistente,
        # error de red con el servidor MCP, JSON corrupto...) se traduce en
        # un mensaje entendible para el cliente, en vez de romper el grafo.
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
