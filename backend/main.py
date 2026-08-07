"""
backend/main.py
==================
Backend REST + streaming: expone el grafo de LangGraph
(backend/agents/graph.py) como servicio web para el frontend Streamlit
(frontend/), siguiendo la arquitectura documentada en
docs/FLUJO_LLAMADAS.md:

    Streamlit --(HTTP POST, SSE)--> FastAPI --> LangGraph (3 agentes)
        --> tools MCP (Supabase / Logística, por HTTP)
        --> HITL (interrupt() si el reembolso > 100 €)
        --> respuesta a Streamlit vía SSE.

Dos grupos de endpoints:
  - POST /api/chat/stream: un turno de chat, streaming SSE con el paso de
    cada agente y la respuesta final (o el aviso de que quedó pendiente de
    un administrador).
  - GET /api/admin/pending y POST /api/admin/approve/{thread_id}: panel de
    administración para el corte Human-in-the-Loop.

El grafo y el registro de pendientes de HITL se construyen de forma
perezosa (backend/dependencies.py) para que `uvicorn backend.main:app` no
falle si aún no has configurado el .env, y para poder sustituirlos en tests.
"""

import logging
from typing import AsyncIterator

# Debe cargarse ANTES de importar backend.dependencies/backend.agents.graph:
# los nodos del grafo (triage.py, policy.py, resolution.py) construyen
# ChatOpenAI() leyendo OPENAI_API_KEY de las variables de entorno del
# proceso en el momento de cada petición, no del fichero .env directamente
# (mismo motivo que en backend/agents/cli/demo_chat.py y backend/mcp/mcp_supabase.py).
from dotenv import load_dotenv

load_dotenv(override=True)

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from backend.dependencies import get_graph, get_pending_store
from backend.schemas import (
    ApproveRequest,
    ApproveResponse,
    ChatRequest,
    ChatStreamEvent,
    PendingApprovalOut,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ReFlow API",
    description="Copiloto de Posventa Autónomo y Gestión Inteligente de Devoluciones (TFM ReFlow).",
    version="1.0.0",
)

# allow_origins=["*"]: demo local de un TFM, el frontend Streamlit corre en
# otro puerto (8501) del mismo host. En un despliegue real se restringiría
# a los orígenes conocidos.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    """Endpoint trivial para comprobar que el proceso está vivo (lo usa el frontend)."""
    return {"status": "ok"}


async def stream_chat_events(
    graph, message: str, thread_id: str, pending: dict
) -> AsyncIterator[ChatStreamEvent]:
    """
    Genera los eventos de un turno de chat para un `thread_id` dado.
    Separada de la ruta HTTP para poder testearla directamente iterándola,
    sin pasar por StreamingResponse/HTTP real.
    """
    config = {"configurable": {"thread_id": thread_id}}

    try:
        if thread_id in pending:
            # Esta conversación ya está pausada esperando a un admin: no
            # volvemos a invocar el grafo (evitaría re-ejecutar el nodo de
            # resolución mientras sigue interrumpido). Se informa al
            # cliente y se corta aquí.
            yield ChatStreamEvent(
                type="awaiting_admin",
                content=(
                    "Tu solicitud sigue pendiente de revisión por nuestro equipo. "
                    "Te avisaremos en cuanto se resuelva."
                ),
            )
            return

        input_state = {"messages": [HumanMessage(content=message)]}
        # stream_mode="updates": cada chunk trae solo lo que devolvió el
        # último nodo ejecutado ({"nombre_nodo": {...cambios...}}), no el
        # estado completo acumulado — así se puede notificar paso a paso.
        async for chunk in graph.astream(input_state, config=config, stream_mode="updates"):
            for node_name in chunk:
                if node_name == "__interrupt__":
                    # Algunas versiones de LangGraph emiten un chunk propio
                    # para el interrupt(); el estado real de la pausa se
                    # comprueba de forma fiable más abajo con aget_state(),
                    # así que aquí no hace falta más que ignorarlo.
                    continue
                yield ChatStreamEvent(
                    type="agent_step",
                    agent=node_name,
                    content=f"Agente «{node_name}» ha completado su turno.",
                )

        # Tras agotar el streaming, se lee el estado persistido (vía el
        # checkpointer) para saber cómo terminó el turno: si el grafo se
        # pausó en un interrupt(), `state.next` no está vacío.
        state = await graph.aget_state(config)
        values = state.values or {}

        if state.next:
            interrupt_payload: dict = {}
            for task in state.tasks:
                if task.interrupts:
                    interrupt_payload = task.interrupts[0].value
                    break
            # Se guarda el payload del interrupt() para que el panel de
            # administración pueda listarlo sin tener que re-consultar el
            # grafo de cada thread_id conocido uno a uno.
            pending[thread_id] = interrupt_payload
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
    except Exception as exc:  # noqa: BLE001 - se traduce a un evento SSE "error", no se deja crashear el stream
        logger.exception("Error procesando el turno de chat (thread_id=%s)", thread_id)
        yield ChatStreamEvent(type="error", content=f"Ha ocurrido un error procesando tu solicitud: {exc}")


async def _to_sse(events: AsyncIterator[ChatStreamEvent]) -> AsyncIterator[bytes]:
    """Serializa cada `ChatStreamEvent` al formato Server-Sent Events (`data: <json>\\n\\n`)."""
    async for event in events:
        yield f"data: {event.model_dump_json()}\n\n".encode("utf-8")


@app.post("/api/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    graph=Depends(get_graph),
    pending: dict = Depends(get_pending_store),
) -> StreamingResponse:
    """Recibe un turno de chat y devuelve, vía Server-Sent Events, el razonamiento de los agentes en tiempo real."""
    events = stream_chat_events(graph, payload.message, payload.thread_id, pending)
    return StreamingResponse(_to_sse(events), media_type="text/event-stream")


@app.get("/api/admin/pending", response_model=list[PendingApprovalOut])
async def list_pending(pending: dict = Depends(get_pending_store)) -> list[PendingApprovalOut]:
    """Devoluciones pausadas por HITL (reembolso > 100€) a la espera de revisión humana."""
    return [
        PendingApprovalOut(
            thread_id=thread_id,
            order_id=payload.get("order_id"),
            customer_id=payload.get("customer_id"),
            refund_amount=payload.get("refund_amount"),
            reason=payload.get("reason"),
            message=payload.get("message"),
        )
        for thread_id, payload in pending.items()
    ]


@app.post("/api/admin/approve/{thread_id}", response_model=ApproveResponse)
async def approve_return(
    thread_id: str,
    payload: ApproveRequest,
    graph=Depends(get_graph),
    pending: dict = Depends(get_pending_store),
) -> ApproveResponse:
    """
    Un administrador aprueba/rechaza una devolución pausada por HITL.
    Reanuda EXACTAMENTE el grafo pausado de ese `thread_id` con
    `Command(resume=...)`: `resolution_agent` retoma la ejecución justo
    después de su llamada a `interrupt()` (ver backend/agents/nodes/resolution.py),
    sin repetir ninguna tool ya invocada antes de la pausa.
    """
    if thread_id not in pending:
        raise HTTPException(
            status_code=404,
            detail=f"No hay ninguna solicitud pendiente para el hilo {thread_id}.",
        )

    config = {"configurable": {"thread_id": thread_id}}
    # Command(resume=...) es el valor que recibe `interrupt(...)` como
    # retorno en el punto exacto donde el grafo se pausó.
    result = await graph.ainvoke(Command(resume={"approved": payload.approved}), config=config)
    pending.pop(thread_id, None)

    last_message = (result.get("messages") or [None])[-1]
    content = last_message.content if last_message else ""

    return ApproveResponse(
        thread_id=thread_id,
        status=result.get("resolution", "unknown"),
        content=content,
    )
