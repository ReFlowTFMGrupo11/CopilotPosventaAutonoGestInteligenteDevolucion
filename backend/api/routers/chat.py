"""Router de chat: interacción del cliente con el grafo de agentes."""

import uuid

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from backend.api.dependencies import get_graph
from backend.api.schemas import ChatRequest, ChatResponse, NewChatResponse

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/new", response_model=NewChatResponse)
async def create_chat():
    """Crea una nueva sesión de chat y devuelve el thread_id."""
    thread_id = str(uuid.uuid4())
    return NewChatResponse(thread_id=thread_id)


@router.post("", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """Envía un mensaje del usuario al grafo de agentes.

    El grafo se ejecuta desde el último checkpoint del thread_id,
    permitiendo conversaciones multi-turno.
    """
    graph = await get_graph()

    try:
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=request.message)]},
            config={"configurable": {"thread_id": request.thread_id}},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error ejecutando el grafo: {exc}")

    # Último mensaje del agente
    last_message = result["messages"][-1]

    return ChatResponse(
        thread_id=request.thread_id,
        response=last_message.content,
        current_agent=result.get("current_agent"),
        order_id=result.get("order_id"),
        is_eligible=result.get("is_eligible"),
        resolution=result.get("resolution"),
    )


@router.get("/{thread_id}/state")
async def get_chat_state(thread_id: str):
    """Devuelve el estado actual del grafo para un thread_id."""
    graph = await get_graph()

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
