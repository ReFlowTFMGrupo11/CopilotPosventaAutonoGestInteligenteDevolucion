"""Router de chat: interacción del cliente con el grafo de agentes.

Dos modos de consumo:
- POST /api/chat         → respuesta JSON síncrona (simple, para pruebas).
- POST /api/chat/stream  → Server-Sent Events con progreso en tiempo real.
"""

import asyncio
import logging
import time
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from backend.api.dependencies import get_graph
from backend.api.schemas import (
    ChatRequest,
    ChatResponse,
    ChatStreamEvent,
    NewChatResponse,
)
from backend.config import get_settings
from backend.services.observability import with_langfuse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# ── Controles de ciclos/timeout/gasto ──────────────────────────────────────
#
# Ninguno de los tres existía antes: el grafo en sí es acíclico dentro de un
# mismo turno, pero nada impedía (a) una conversación de cientos de turnos en
# el mismo thread_id, (b) un `ainvoke`/`astream` colgado para siempre si el
# LLM o un MCP server dejaban de responder sin lanzar excepción, ni (c) que
# LangGraph corriera con el `recursion_limit` implícito del SDK (25) en vez
# de uno explícito y documentado.

# Fuente única: backend/config.py (Settings). Antes, estas tres constantes
# se definían por duplicado aquí Y en admin.py con el mismo default cada
# una — cambiar una sin la otra las desincronizaba sin ningún aviso.
_settings = get_settings()

# Explícito en vez de depender del default implícito de LangGraph (25).
GRAPH_RECURSION_LIMIT = _settings.graph_recursion_limit

# Tiempo máximo para que el grafo complete un turno completo (todas las
# llamadas a LLM/MCP/BD que ese turno dispare). Si se agota, se cancela la
# tarea y se informa al cliente en vez de dejar la petición colgada.
GRAPH_TURN_TIMEOUT_SECONDS = _settings.graph_turn_timeout_seconds

# Tope de turnos de usuario por conversación (thread_id). Protege frente a
# conversaciones sin fin (bug de frontend, o un cliente reenviando el mismo
# hilo indefinidamente) que harían crecer coste y contexto sin límite.
MAX_CONVERSATION_TURNS = _settings.max_conversation_turns

_TURN_LIMIT_MSG = (
    "Esta conversación ha alcanzado el número máximo de turnos permitido. "
    "Por favor, inicia una nueva conversación para continuar."
)
_TURN_TIMEOUT_MSG = (
    "El agente ha tardado demasiado en responder. Por favor, inténtalo de nuevo."
)


def _with_graph_limits(config: dict) -> dict:
    """Añade el `recursion_limit` explícito a un config de LangGraph."""
    merged = dict(config)
    merged["recursion_limit"] = GRAPH_RECURSION_LIMIT
    return merged


async def _conversation_turn_limit_reached(graph, config: dict) -> bool:
    """True si ``thread_id`` ya acumuló ``MAX_CONVERSATION_TURNS`` mensajes de usuario."""
    if MAX_CONVERSATION_TURNS <= 0:
        return False
    state = await graph.aget_state(config)
    messages = (state.values or {}).get("messages", []) if state else []
    human_turns = sum(1 for m in messages if isinstance(m, HumanMessage))
    return human_turns >= MAX_CONVERSATION_TURNS


async def _known_customer_id(graph, thread_id: str) -> str | None:
    """``customer_id`` ya resuelto para este thread_id en un turno anterior.

    Se usa para taggear las trazas de LangFuse por cliente desde el primer
    nodo del turno; antes de que el cliente dé su order_number todavía no
    hay customer_id (ver fetch_order_data en triage.py) y se omite el tag.
    """
    state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    return (state.values or {}).get("customer_id") if state else None

# Un lock por thread_id: si dos peticiones para el MISMO hilo llegan
# solapadas (doble clic, doble envío del frontend, reintento de red...),
# la segunda espera a que la primera termine en vez de invocar el grafo
# dos veces en paralelo sobre el mismo checkpoint. Sin esto, la segunda
# podía toparse con un estado a medias y devolver el mensaje generico de
# "sigue pendiente de revisión" sin haber creado ningún registro en BD.
#
# _ThreadLockRegistry en vez de un defaultdict(asyncio.Lock) plano: un
# dict así crece con cada thread_id nuevo y nunca se libera solo (una
# fuga de memoria lenta en un proceso de larga duración). El registro
# expulsa entradas inactivas (no locked() y sin uso reciente) cada vez
# que se pide un lock nuevo.
_THREAD_LOCK_TTL_SECONDS = 3600.0  # 1 hora sin actividad


class _ThreadLockRegistry:
    """Registro de ``asyncio.Lock`` por ``thread_id`` con expulsión de
    entradas inactivas, para no crecer sin límite en un proceso de larga
    duración."""

    def __init__(self, ttl_seconds: float = _THREAD_LOCK_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_used: dict[str, float] = {}

    def get(self, thread_id: str) -> asyncio.Lock:
        self._evict_stale()
        self._last_used[thread_id] = time.monotonic()
        if thread_id not in self._locks:
            self._locks[thread_id] = asyncio.Lock()
        return self._locks[thread_id]

    def _evict_stale(self) -> None:
        now = time.monotonic()
        stale = [
            tid for tid, last_used in self._last_used.items()
            if now - last_used > self._ttl and not self._locks[tid].locked()
        ]
        for tid in stale:
            del self._locks[tid]
            del self._last_used[tid]


_thread_locks = _ThreadLockRegistry()


@router.post("/new", response_model=NewChatResponse)
async def create_chat():
    """Crea una nueva sesión de chat y devuelve el thread_id."""
    thread_id = str(uuid.uuid4())
    return NewChatResponse(thread_id=thread_id)


# ── Endpoint síncrono (JSON) ──────────────────────────────────────────────


@router.post("", response_model=ChatResponse)
async def send_message(request: ChatRequest, graph=Depends(get_graph)):
    """Envía un mensaje y espera la respuesta completa (sin streaming).

    Útil para pruebas con curl o clientes que no soportan SSE.
    """
    config = _with_graph_limits(
        with_langfuse(
            {
                "configurable": {"thread_id": request.thread_id},
            },
            thread_id=request.thread_id,
            customer_id=await _known_customer_id(graph, request.thread_id),
        )
    )

    if await _conversation_turn_limit_reached(graph, config):
        return ChatResponse(thread_id=request.thread_id, response=_TURN_LIMIT_MSG)

    try:
        result = await asyncio.wait_for(
            graph.ainvoke(
                {
                    "messages": [HumanMessage(content=request.message)],
                    "thread_id": request.thread_id,
                    "selected_item_ids": request.selected_item_ids,
                },
                config=config,
            ),
            timeout=GRAPH_TURN_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=_TURN_TIMEOUT_MSG)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error ejecutando el grafo: {exc}")

    last_message = result["messages"][-1]

    return ChatResponse(
        thread_id=request.thread_id,
        response=last_message.content,
        current_agent=result.get("current_agent"),
        order_id=result.get("order_id"),
        is_eligible=result.get("is_eligible"),
        resolution=result.get("resolution"),
    )


# ── Endpoint streaming (SSE) ─────────────────────────────────────────────

_HITL_CUSTOMER_MSG = (
    "Tu solicitud de devolución está siendo revisada por nuestro equipo. "
    "Dado el importe del reembolso, necesitamos una validación manual antes de procesarla. "
    "Te notificaremos en un plazo de 24-48 horas con la resolución. "
    "¡Gracias por tu paciencia!"
)


async def _astream_with_timeout(
    aiter: AsyncIterator, timeout: float
) -> AsyncIterator:
    """Envuelve un async generator aplicando ``timeout`` a cada paso.

    ``graph.astream`` emite un chunk por cada nodo que termina. Si un nodo
    concreto se queda colgado (LLM/MCP/BD sin responder), el `async for`
    original nunca produciría el siguiente chunk ni lanzaría excepción — la
    petición SSE quedaría abierta para siempre. Al medir el timeout por
    paso (``__anext__``) en vez de sobre el generator completo, una
    conversación con muchos nodos legítimos no se corta por acumulación,
    solo cuando UN paso concreto excede el plazo.
    """
    iterator = aiter.__aiter__()
    while True:
        try:
            item = await asyncio.wait_for(iterator.__anext__(), timeout=timeout)
        except StopAsyncIteration:
            return
        yield item


async def _stream_chat_events(
    graph, message: str, thread_id: str, selected_item_ids: list[str] | None = None
) -> AsyncIterator[ChatStreamEvent]:
    """Genera eventos SSE conforme cada nodo del grafo termina."""
    config = _with_graph_limits(
        with_langfuse(
            {
                "configurable": {"thread_id": thread_id},
            },
            thread_id=thread_id,
            customer_id=await _known_customer_id(graph, thread_id),
        )
    )
    lock = _thread_locks.get(thread_id)

    if lock.locked():
        logger.warning(
            "Peticion para thread_id=%s solapada con otra en curso; se rechaza "
            "en vez de invocar el grafo dos veces en paralelo.",
            thread_id,
        )
        yield ChatStreamEvent(
            type="awaiting_admin",
            content=(
                "Ya estamos procesando tu mensaje anterior. Espera a que termine "
                "antes de enviar otro."
            ),
        )
        return

    async with lock:
        try:
            # Guard: si el thread ya está pausado por HITL, no re-invocar el grafo
            existing_state = await graph.aget_state(config)
            if existing_state and existing_state.next:
                yield ChatStreamEvent(
                    type="awaiting_admin",
                    content=_HITL_CUSTOMER_MSG,
                )
                return

            if await _conversation_turn_limit_reached(graph, config):
                yield ChatStreamEvent(type="final", content=_TURN_LIMIT_MSG)
                return

            input_state = {
                "messages": [HumanMessage(content=message)],
                "thread_id": thread_id,
                "selected_item_ids": selected_item_ids,
            }

            # stream_mode="updates": emite un chunk por cada nodo que termina.
            # Envuelto con timeout por paso (ver _astream_with_timeout) para no
            # quedar colgados si un nodo concreto no responde nunca.
            stream = graph.astream(input_state, config=config, stream_mode="updates")
            async for chunk in _astream_with_timeout(stream, GRAPH_TURN_TIMEOUT_SECONDS):
                for node_name in chunk:
                    if node_name == "__interrupt__":
                        continue
                    yield ChatStreamEvent(
                        type="agent_step",
                        agent=node_name,
                        content=f"Agente «{node_name}» ha completado su turno.",
                    )

            # Tras el streaming, leer estado final para saber si quedó pausado
            state = await graph.aget_state(config)
            values = state.values or {}

            if state.next:
                # El grafo se pausó en un interrupt() → HITL
                interrupt_payload: dict = {}
                for task in state.tasks:
                    if task.interrupts:
                        interrupt_payload = task.interrupts[0].value
                        break
                yield ChatStreamEvent(
                    type="awaiting_admin",
                    content=interrupt_payload.get(
                        "message",
                        "Tu solicitud requiere aprobación de un administrador. "
                        "Te avisaremos en cuanto se resuelva.",
                    ),
                    order_id=interrupt_payload.get("order_id"),
                )
                return

            # Respuesta final
            last_message = (values.get("messages") or [None])[-1]
            content = last_message.content if last_message else "No he podido generar una respuesta."

            yield ChatStreamEvent(
                type="final",
                content=content,
                agent=values.get("current_agent"),
                order_id=values.get("order_id"),
                is_eligible=values.get("is_eligible"),
                tracking_number=values.get("tracking_number"),
                label_path=values.get("label_path"),
                resolution=values.get("resolution"),
            )
        except asyncio.TimeoutError:
            logger.warning("Timeout de turno en streaming (thread_id=%s)", thread_id)
            yield ChatStreamEvent(type="error", content=_TURN_TIMEOUT_MSG)
        except Exception as exc:
            logger.exception("Error en streaming (thread_id=%s)", thread_id)
            yield ChatStreamEvent(type="error", content=f"Error procesando tu solicitud: {exc}")


async def _to_sse(events: AsyncIterator[ChatStreamEvent]) -> AsyncIterator[bytes]:
    """Serializa ChatStreamEvent al formato Server-Sent Events."""
    async for event in events:
        yield f"data: {event.model_dump_json()}\n\n".encode("utf-8")


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    graph=Depends(get_graph),
) -> StreamingResponse:
    """Envía un mensaje y recibe eventos SSE en tiempo real.

    El frontend ve el progreso de cada agente conforme termina
    (cada 2-5s), en vez de esperar 10-20s por la respuesta completa.
    """
    events = _stream_chat_events(
        graph,
        request.message,
        request.thread_id,
        request.selected_item_ids,
    )
    return StreamingResponse(_to_sse(events), media_type="text/event-stream")


# ── Estado del grafo ──────────────────────────────────────────────────────


@router.get("/{thread_id}/state")
async def get_chat_state(thread_id: str, graph=Depends(get_graph)):
    """Devuelve el estado actual del grafo para un thread_id."""
    try:
        state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Sesión no encontrada: {exc}")

    values = state.values if state else {}
    raw_items = (values.get("order_details") or {}).get("items", [])
    items_to_return = values.get("items_to_return") or []
    order_items = [
        {
            "id": item.get("id"),
            "name": (item.get("product") or {}).get("name", "Artículo"),
            "quantity": item.get("quantity", 1),
            "unit_price": item.get("unit_price"),
        }
        for item in raw_items
    ]
    return {
        "thread_id": thread_id,
        "current_agent": values.get("current_agent"),
        "order_id": values.get("order_id"),
        "customer_name": values.get("customer_name"),
        "is_eligible": values.get("is_eligible"),
        "resolution": values.get("resolution"),
        "refund_amount": values.get("refund_amount"),
        "order_items": order_items,
        "selection_required": len(order_items) > 1 and not bool(items_to_return),
    }
