"""Router de chat: interacción del cliente con el grafo de agentes.

Dos modos de consumo:
- POST /api/chat         → respuesta JSON síncrona (simple, para pruebas).
- POST /api/chat/stream  → Server-Sent Events con progreso en tiempo real.
"""

import json
import logging
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


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
    try:
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=request.message)], "thread_id": request.thread_id},
            config={"configurable": {"thread_id": request.thread_id}},
        )
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


async def _stream_chat_events(
    graph, message: str, thread_id: str
) -> AsyncIterator[ChatStreamEvent]:
    """Genera eventos SSE conforme cada nodo del grafo termina."""
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # Guard: si el thread ya está pausado por HITL, no re-invocar el grafo
        existing_state = await graph.aget_state(config)
        if existing_state and existing_state.next:
            yield ChatStreamEvent(
                type="awaiting_admin",
                content=(
                    "Tu solicitud sigue pendiente de revisión por nuestro equipo. "
                    "Te avisaremos en cuanto se resuelva."
                ),
            )
            return

        input_state = {"messages": [HumanMessage(content=message)], "thread_id": thread_id}

        # stream_mode="updates": emite un chunk por cada nodo que termina
        async for chunk in graph.astream(input_state, config=config, stream_mode="updates"):
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
    events = _stream_chat_events(graph, request.message, request.thread_id)
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
    return {
        "thread_id": thread_id,
        "current_agent": values.get("current_agent"),
        "order_id": values.get("order_id"),
        "customer_name": values.get("customer_name"),
        "is_eligible": values.get("is_eligible"),
        "resolution": values.get("resolution"),
        "refund_amount": values.get("refund_amount"),
    }
