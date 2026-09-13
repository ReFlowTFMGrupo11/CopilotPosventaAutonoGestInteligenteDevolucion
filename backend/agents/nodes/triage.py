"""
Agente de Triaje y Empatía.

Primer punto de contacto con el cliente. Se encarga de:
1. Saludar y empatizar con el usuario.
2. Comprender el motivo de insatisfacción.
3. Extraer parámetros clave (order_number, razón, artículos) de forma conversacional.
4. Consultar los detalles del pedido en Supabase.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 FRONTERA  DETERMINISTA  vs  LLM  en este módulo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 LLM  (triage_agent)
  - Extrae order_number del texto libre del cliente.
  - Clasifica reason_category (enum blando; puede equivocarse sin consecuencias graves).
  - Redacta response_to_customer empático.
  - Infiere items_to_return por nombre de producto → order_item_id  ← RIESGO,
    por eso existe el override determinista.

 DETERMINISTA  (fetch_order_data + helpers)
  - Consulta BD para validar que el pedido existe.
  - Verifica si ya hay una devolución activa para el pedido (_check_existing_return).
  - Construye el mensaje de artículos disponibles (_build_items_prompt).
  - Sobreescribe items_to_return con la selección explícita del usuario
    proveniente de checkboxes UI (_apply_deterministic_selection).
    El LLM NUNCA puede alterar esta selección si el usuario ya la marcó.
  - Normaliza respuestas MCP (_parse_mcp_response).

 REGLA GENERAL:
  - Si un campo cambia el camino del grafo o crea/modifica registros → determinista.
  - Si un campo solo mejora comprensión o UX → LLM.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from backend.agents.state import ReturnState
from backend.agents.llm_factory import build_chat_llm, trim_history
from backend.agents.usage_tracking import invoke_structured_tracked
from backend.agents.infra.mcp_client import (
    get_order_details,
    get_customer_return_history,
)

logger = logging.getLogger(__name__)

# ── Prompt del sistema ─────────────────────────────────────────────────────

TRIAGE_SYSTEM_PROMPT = """\
Eres ReFlow, un asistente de atención al cliente especializado en devoluciones.
Tu rol es el de **Agente de Triaje y Empatía**: el primer punto de contacto.

## Objetivos
1. Saludar amablemente y mostrar empatía por la situación del cliente.
2. Entender el motivo de la devolución.
3. Extraer la siguiente información de forma conversacional (NO interrogatorio):
   - **order_number**: número de pedido, EXACTAMENTE tal cual lo escribe el
     cliente (carácter por carácter, sin corregir ni "normalizar" el formato).
     Lo tiene en su email de confirmación; puede tener distintos prefijos
     (p. ej. "ORD-2026-00177", "ORD-QA-0004", "ORD-QAM-0018"...). NUNCA
     sustituyas lo que el cliente escribió por ningún ejemplo de este prompt,
     aunque el formato no te resulte familiar — un ejemplo de formato no es
     nunca un número de pedido real. NUNCA le pidas un UUID.
   - **reason**: motivo de la devolución en texto libre.
   - **reason_category**: una de [defective, wrong_item, not_as_described, no_longer_needed, arrived_late, other].
   - **items_to_return**: lista de artículos con formato [{"order_item_id": "...", "quantity": 1, "condition": "..."}].
     Las condiciones posibles son: unopened, defective, damaged, used, wrong_item.

## Interpretación semántica de motivo → condition
El cliente casi nunca usa las palabras exactas del enum, y puede describir el
problema de mil formas distintas según la categoría del producto (electrónica,
calzado, alimentación, mascotas, cosmética, etc.). NO busques coincidencias
literales de palabras clave: interpreta el SIGNIFICADO real de lo que dice y
mapéalo tú mismo a unopened / defective / damaged / used / wrong_item. Algunos
ejemplos orientativos (no es una lista cerrada, hay infinitas variantes):
   - "estropeado", "no funciona", "no enciende" → defective
   - "llegó dañado", "abollado", "roto por fuera" → damaged
   - "sin abrir", "precintado", "no lo he usado" → unopened
   - "ya lo he usado/probado" → used
   - "no es el que pedí", "me enviaron otra cosa" → wrong_item
   - "he cambiado de opinión", "ya no lo quiero/necesito", "no me convence",
     "no era lo que esperaba" (sin mención de uso o daño) → unopened, asumiendo
     que un cliente que se arrepiente de la compra no ha llegado a usar el
     artículo, salvo que el propio mensaje indique lo contrario
Si el motivo de un artículo ya deja claro su estado (por significado, aunque no
use ninguna de estas palabras), infiere `condition` en el mismo turno en el que
se menciona; pregunta el estado explícitamente solo para los artículos cuya
condición siga siendo realmente ambigua tras leer todo el historial.

## Confirmación obligatoria antes de dar por buena la condición inferida
Como la condición se infiere por significado (no por coincidencia exacta), puede
fallar. Por eso, en el turno en el que completas por primera vez la condición de
TODOS los artículos, NO la des por confirmada todavía: en `response_to_customer`
resume lo que has entendido artículo a artículo (p. ej. "Entiendo que quieres
devolver el Microondas porque está estropeado —lo marco como defectuoso— y el
Champú porque no te gusta el color —lo marco como sin abrir—. ¿Es correcto?") y
espera la respuesta del cliente.
- `items_confirmed` = true SOLO si el mensaje MÁS RECIENTE del cliente confirma
  explícitamente ese resumen (ej. "sí", "correcto", "exacto", "así es").
- `items_confirmed` = false/None en cualquier otro caso, incluida la primera vez
  que infieres el estado (la confirmación nunca puede darse en el mismo turno en
  que se infiere; necesita un turno de ida y vuelta).
- Si el cliente corrige algo del resumen ("no, el champú está sin abrir, no
  estropeado"), actualiza `condition` con el valor correcto y vuelve a resumir
  y pedir confirmación: no asumas confirmación de lo que no corrigió.

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
- NUNCA confirmes que una devolución ha sido registrada, procesada o aprobada.
  Tu rol es SOLO recopilar información. La confirmación final la hace otro agente.
- NUNCA digas frases como "ya registré", "hemos procesado", "tu devolución está lista"
  o similares. Si el cliente da toda la información, responde únicamente con un
  resumen de lo recogido y que el sistema lo validará.
"""


# ── Modelos ────────────────────────────────────────────────────────────────

from backend.models import TriageOutput


def _build_llm() -> ChatOpenAI:
    """Construye el LLM para el agente de triaje con salida estructurada.

    Modelo configurable vía ``TRIAGE_MODEL``; por defecto ``gpt-5-mini``.
    """
    return build_chat_llm("TRIAGE_MODEL", temperature=0)


_EMPTY_MESSAGE_RESPONSE = (
    "No he recibido ningún mensaje. ¿Puedes contarme qué problema tienes con tu pedido?"
)


def _last_ai_message_content(messages: list[Any]) -> str | None:
    """Contenido del último ``AIMessage`` en el historial, o ``None`` si no hay."""
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message.content
    return None


def _is_noop_turn(messages: list[Any]) -> bool:
    """True si el turno actual no puede aportar NADA nuevo que extraer.

    Casos deterministas y seguros — deliberadamente NO se intenta detectar
    "el cliente no dijo nada relevante" por semántica/keywords (el propio
    prompt de este módulo prohíbe ese enfoque para campos como
    ``items_confirmed``: "NO busques coincidencias literales de palabras
    clave"). Solo se cubren dos casos sin ambigüedad posible:

    1. Mensaje vacío/solo espacios — no hay texto del que extraer nada.
    2. El último mensaje humano es un duplicado EXACTO e INMEDIATO del
       anterior (mismo contenido, sin ningún turno de por medio) — el
       patrón de un doble-submit del frontend o un reintento del cliente
       tras un 504 de ``GRAPH_TURN_TIMEOUT_SECONDS`` (chat.py cancela la
       llamada al LLM en curso, pero el cliente puede reenviar el mismo
       mensaje creyendo que no llegó).

    Solo se compara el ÚLTIMO PAR consecutivo, nunca cualquier repetición
    en el historial completo: un cliente que repite la misma frase varios
    turnos después (p.ej. para insistir) sí puede significar algo distinto
    en ese punto de la conversación, así que ese caso SÍ se reprocesa con
    el LLM como siempre.
    """
    if not messages:
        return False
    last = messages[-1]
    if not isinstance(last, HumanMessage):
        return False
    if not (last.content or "").strip():
        return True
    human_messages = [m for m in messages if isinstance(m, HumanMessage)]
    return len(human_messages) >= 2 and human_messages[-2].content == last.content


async def triage_agent(state: ReturnState) -> dict[str, Any]:
    """Nodo del agente de Triaje y Empatía.

    Lee los ``messages`` del estado, invoca al LLM con structured output
    (Pydantic) para garantizar un schema válido en cada respuesta.
    """
    messages = state.get("messages", [])

    # Corte determinista ANTES de pagar una llamada al LLM: sin esto, un
    # mensaje vacío o un doble-submit/reintento idéntico consecutivo
    # disparaba una llamada completa al LLM para no extraer nada nuevo — el
    # propio LLM habría vuelto a pedir lo mismo que ya se sabe. Ver
    # `_is_noop_turn` para qué casos cubre (y cuáles NO, a propósito).
    if _is_noop_turn(messages):
        logger.info(
            "Triaje: turno sin información nueva (mensaje vacío o duplicado "
            "inmediato); se omite la llamada al LLM."
        )
        previous_response = _last_ai_message_content(messages[:-1])
        return {
            "messages": [
                AIMessage(content=previous_response or _EMPTY_MESSAGE_RESPONSE)
            ],
            "current_agent": "triage",
        }

    llm = _build_llm()

    # Construir la lista de mensajes para el LLM
    context = [SystemMessage(content=TRIAGE_SYSTEM_PROMPT)]
    if state.get("order_number"):
        context.append(
            SystemMessage(content=f"order_number ya conocido: {state['order_number']}")
        )
    if state.get("order_details"):
        items = state["order_details"].get("items", [])
        context.append(
            SystemMessage(
                content=f"ARTÍCULOS DEL PEDIDO: {json.dumps(items, default=str, ensure_ascii=False)}"
            )
        )
    llm_messages = [*context, *trim_history(state.get("messages", []))]

    result: TriageOutput | None = await invoke_structured_tracked(
        llm,
        TriageOutput,
        llm_messages,
        node="triage",
        thread_id=state.get("thread_id", ""),
        customer_id=state.get("customer_id"),
        order_id=state.get("order_id"),
    )

    if result is None:
        # Fallback: el LLM no generó structured output válido
        logger.warning("Triaje: structured output devolvió None, usando fallback.")
        return {
            "messages": [
                AIMessage(
                    content="Lo siento, no he podido procesar tu mensaje. ¿Podrías repetirlo?"
                )
            ],
            "current_agent": "triage",
        }

    # ── Pedido bloqueado (p. ej. ya tiene una devolución activa) ────────
    # fetch_order_data deja `error` marcado en el estado, pero ese campo
    # nunca se limpia solo: sin este corte, la conversación seguía
    # recogiendo motivo/estado/confirmación turno tras turno como si todo
    # avanzara con normalidad, mientras route_after_fetch (graph.py) la
    # descartaba en silencio cada vez por el `error` ya persistido —
    # un bucle de confirmaciones que nunca llega a ningún sitio. Si el
    # cliente da un order_number DISTINTO, se le deja intentar con ese
    # otro pedido en vez de quedar bloqueado para siempre.
    blocking_error = state.get("error")
    switching_order = bool(result.order_number) and result.order_number != state.get(
        "order_number"
    )
    if blocking_error and not switching_order:
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"{blocking_error} Si quieres devolver un artículo de OTRO pedido, "
                        "dime su número."
                    )
                )
            ],
            "current_agent": "triage",
        }

    updates: dict[str, Any] = {
        "messages": [AIMessage(content=result.response_to_customer)],
        "current_agent": "triage",
    }

    if switching_order:
        # Nuevo pedido: cualquier bloqueo/artículos/motivo del pedido
        # anterior ya no aplican, para no arrastrar datos de un pedido
        # a otro.
        updates["error"] = None
        updates["order_details"] = None
        updates["items_to_return"] = None
        updates["items_confirmed"] = None
        updates["reason"] = None
        updates["reason_category"] = None

    if result.order_number:
        updates["order_number"] = result.order_number
    if result.reason:
        updates["reason"] = result.reason
    if result.reason_category:
        updates["reason_category"] = result.reason_category

    # ── Red de seguridad determinista para items_confirmed ─────────────
    # El LLM decide items_confirmed por semántica y puede equivocarse; no nos
    # fiamos de un "true" si el contenido de items_to_return acaba de cambiar
    # en este mismo turno (la confirmación real solo puede darse en un turno
    # posterior, sobre un resumen ya mostrado).
    old_items = state.get("items_to_return") or []
    new_items = (
        [item.model_dump() for item in result.items_to_return]
        if result.items_to_return
        else old_items
    )
    if result.items_to_return:
        updates["items_to_return"] = new_items

    if _items_key(old_items) != _items_key(new_items):
        updates["items_confirmed"] = False
    elif result.items_confirmed:
        updates["items_confirmed"] = True

    _apply_deterministic_selection(state, result, updates)

    # Limpiar selección transitoria para no arrastrarla a turnos posteriores.
    if state.get("selected_item_ids") is not None:
        updates["selected_item_ids"] = None

    return updates


# ── Helpers ────────────────────────────────────────────────────────────────


def _items_key(items: list[dict[str, Any]]) -> frozenset[tuple[str, str]]:
    """Firma de (order_item_id, condition) para detectar si items_to_return cambió."""
    return frozenset(
        (item.get("order_item_id", ""), item.get("condition", "")) for item in items
    )


# Mapeo determinista motivo → condición más probable. Fuente única usada
# tanto por el atajo de pedido con un solo artículo (_auto_select_single_item)
# como por la selección explícita vía checkboxes (_apply_deterministic_selection)
# — antes solo la usaba el primero, así que un pedido con varios artículos
# nunca se beneficiaba de ella y siempre acababa preguntando la condición
# explícitamente aunque el motivo ya la insinuara.
_CONDITION_MAP: dict[str, str] = {
    "defective": "defective",
    "wrong_item": "wrong_item",
    "not_as_described": "defective",
    "no_longer_needed": "unopened",
    "arrived_late": "unopened",
}
_CONDITION_LABELS: dict[str, str] = {
    "defective": "defectuoso",
    "wrong_item": "artículo incorrecto",
    "unopened": "sin abrir",
}


def _infer_condition_from_reason(reason_category: str) -> str:
    """Condición más probable dado el motivo, o "" si no se puede derivar."""
    return _CONDITION_MAP.get(reason_category, "")


def _apply_deterministic_selection(
    state: ReturnState,
    result: Any,
    updates: dict[str, Any],
) -> None:
    """Sobreescribe `items_to_return` con la selección explícita del usuario.

    Si el cliente marcó checkboxes (`selected_item_ids`), se usa esa lista en
    vez de la inferencia del LLM sobre QUÉ artículo devolver. La condición se
    resuelve en este orden:
      1. Lo que el cliente ya dijo en este mismo mensaje (inferido por el LLM,
         y distinto de "unknown") → se toma como confirmado sin más.
      2. El mapeo determinista motivo→condición (``_infer_condition_from_reason``)
         → se propone al cliente, pendiente de confirmar (igual que hace
         ``_auto_select_single_item`` para pedidos de un solo artículo).
      3. Si ninguna de las dos resuelve la condición, se pide explícitamente.

    Args:
        result: Salida estructurada del LLM de triaje (``TriageOutput``),
            de donde se toma la condición ya inferida (si la hay).
        updates: Dict de actualizaciones del nodo; se modifica in-place
            para añadir `items_to_return`/`items_confirmed`/`messages`.
    """
    selected_item_ids = state.get("selected_item_ids") or []
    order_items = (state.get("order_details") or {}).get("items", [])
    if not selected_item_ids or not order_items:
        return

    valid_items_by_id = {item.get("id"): item for item in order_items if item.get("id")}
    llm_condition = (
        result.items_to_return[0].condition if result.items_to_return else ""
    )
    stated_by_customer = bool(llm_condition) and llm_condition != "unknown"
    condition = (
        llm_condition
        if stated_by_customer
        else (
            _infer_condition_from_reason(state.get("reason_category") or "")
            or "unknown"
        )
    )

    normalized = [
        {"order_item_id": item_id, "quantity": 1, "condition": condition}
        for item_id in selected_item_ids
        if valid_items_by_id.get(item_id)
    ]
    if not normalized:
        return

    updates["items_to_return"] = normalized

    if stated_by_customer:
        # El cliente ya dijo el estado en este mismo mensaje: la selección
        # por checkbox + su propia frase son confirmación suficiente.
        updates["items_confirmed"] = True
        return

    updates["items_confirmed"] = False
    names = [
        ((valid_items_by_id.get(i) or {}).get("product") or {}).get("name", "Artículo")
        for i in selected_item_ids
    ]
    if condition == "unknown":
        updates["messages"] = [
            AIMessage(
                content=(
                    f"Perfecto, he marcado {', '.join(names)} para la devolución. "
                    "Para continuar, necesito el estado del producto: "
                    "`unopened` (sin abrir), `defective` (defectuoso) o "
                    "`wrong_item` (artículo incorrecto)."
                )
            )
        ]
    else:
        label = _CONDITION_LABELS.get(condition, condition)
        updates["messages"] = [
            AIMessage(
                content=(
                    f"Perfecto, he marcado {', '.join(names)} para la devolución. "
                    f"Por el motivo indicado, entiendo que el estado es "
                    f"**{label}**. ¿Es correcto?"
                )
            )
        ]


def _parse_mcp_response(raw: Any) -> dict:
    """Normaliza la respuesta MCP (lista de content blocks o dict directo)."""
    if isinstance(raw, list):
        return json.loads(raw[0]["text"])
    return raw


def _check_existing_return(
    return_history: dict, order_id: str, order_number: str
) -> dict[str, Any] | None:
    """Si ya existe una devolución activa para el pedido, devuelve error+mensaje.

    Args:
        return_history: Salida de ``get_customer_return_history`` (contiene
            la lista `returns` con `order_id`/`status` de cada devolución
            previa del cliente).

    Returns:
        Dict con `error` y `messages` si hay una devolución activa para
        `order_id`, o ``None`` si no hay ninguna.
    """
    active_statuses = {"pending", "pending_approval", "processing"}
    existing = [
        r
        for r in (return_history.get("returns") or [])
        if r.get("order_id") == order_id and r.get("status") in active_statuses
    ]
    if not existing:
        return None
    status_display = existing[0].get("status", "en curso")
    return {
        "error": f"Ya existe una devolución para este pedido (estado: {status_display}).",
        "messages": [
            AIMessage(
                content=(
                    f"El pedido **{order_number}** ya tiene una solicitud de devolución "
                    f"registrada (estado: **{status_display}**). No es posible crear otra "
                    f"devolución para el mismo pedido.\n\n"
                    f"Si necesitas más información sobre el estado de tu devolución o "
                    f"tienes alguna otra consulta, estoy aquí para ayudarte."
                )
            )
        ],
    }


def _build_items_prompt(order_number: str, items: list[dict]) -> AIMessage:
    """Construye el mensaje para preguntar al cliente qué artículo quiere devolver."""
    if len(items) == 1:
        single = items[0]
        product_name = (single.get("product") or {}).get("name", "Artículo")
        return AIMessage(
            content=(
                f"He encontrado tu pedido {order_number} con el artículo "
                f"**{product_name}** ({single.get('unit_price')}€). "
                f"¿Cuál es el motivo de la devolución y en qué estado "
                f"se encuentra el artículo (sin abrir, defectuoso, artículo incorrecto, etc.)?"
            )
        )
    items_text = (
        "\n".join(
            f"- {(item.get('product') or {}).get('name', 'Artículo')} "
            f"(cantidad: {item.get('quantity', 1)}, precio: {item.get('unit_price')}€)"
            for item in items
        )
        or "(no se encontraron artículos en este pedido)"
    )
    return AIMessage(
        content=(
            f"He encontrado tu pedido {order_number}. Estos son los artículos:\n"
            f"{items_text}\n\n¿Cuál quieres devolver, por qué motivo y en qué estado "
            f"se encuentra cada uno (sin abrir, defectuoso, dañado, usado, artículo "
            f"incorrecto)?"
        )
    )


def _auto_select_single_item(
    order_number: str,
    items: list[dict],
    reason_category: str,
) -> dict[str, Any] | None:
    """Si hay 1 artículo y el reason_category es conocido, auto-selecciona con condición.

    Returns:
        Dict con `items_to_return` y `messages` listo para mezclar en
        updates, o ``None`` si no se puede auto-seleccionar (varios
        artículos o categoría desconocida).
    """
    if len(items) != 1:
        return None
    condition = _infer_condition_from_reason(reason_category)
    if not condition:
        return None

    single = items[0]
    product_name = (single.get("product") or {}).get("name", "Artículo")
    label = _CONDITION_LABELS.get(condition, condition)
    return {
        "items_to_return": [
            {"order_item_id": single["id"], "quantity": 1, "condition": condition}
        ],
        "messages": [
            AIMessage(
                content=(
                    f"Entendido. Voy a gestionar la devolución de **{product_name}** "
                    f"(estado: {label}) del pedido {order_number}. "
                    f"¿Confirmas que esto es correcto?"
                )
            )
        ],
    }


async def fetch_order_data(state: ReturnState) -> dict[str, Any]:
    """Nodo auxiliar que consulta los detalles del pedido en Supabase.

    Se ejecuta después del triaje, cuando ya tenemos el ``order_number``. Si
    todavía no sabemos qué artículo quiere devolver el cliente, muestra los
    artículos del pedido y pregunta, en vez de exigirle un ID técnico.
    """
    order_number = state.get("order_number")
    if not order_number:
        return {"error": "No se proporcionó order_number."}

    # Si ya tenemos los datos del pedido en el estado, no volver a consultarlos.
    if state.get("order_details") and state.get("items_to_return"):
        return {}

    try:
        order_details = _parse_mcp_response(await get_order_details(order_number))

        order_id = order_details["order"]["id"]
        customer_id = order_details["order"]["customer"]["id"]
        customer_name = order_details["order"]["customer"]["full_name"]
        customer_email = order_details["order"]["customer"]["email"]

        return_history = _parse_mcp_response(
            await get_customer_return_history(customer_id)
        )

        updates: dict[str, Any] = {
            "order_id": order_id,
            "order_details": order_details,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "return_history": return_history,
        }

        # ── Verificar si ya existe una devolución para este pedido ─────────
        duplicate_msg = _check_existing_return(return_history, order_id, order_number)
        if duplicate_msg:
            updates["error"] = duplicate_msg["error"]
            updates["messages"] = duplicate_msg["messages"]
            return updates

        # Primera vez que vemos este pedido: preguntar artículo y motivo.
        if not state.get("items_to_return"):
            items = order_details.get("items", [])
            auto = _auto_select_single_item(
                order_number, items, state.get("reason_category") or ""
            )
            if auto:
                updates.update(auto)
            else:
                updates["messages"] = [_build_items_prompt(order_number, items)]

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
