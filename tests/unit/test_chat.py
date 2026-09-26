"""Tests unitarios de backend/api/routers/chat.py.

Corresponde 1:1 con frontend/Chat.py (ver docs/defensaTFM/defenderFastAPI.md).
Usan dependency_overrides para inyectar un mock del grafo, de modo que NO
se necesita OpenAI, Supabase ni servidores MCP.
"""

import json

import pytest
from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_create_chat(async_client):
    """Verifica que crear un chat nuevo devuelve un thread_id con formato UUID."""
    async with async_client as client:
        resp = await client.post("/api/chat/new")

    assert resp.status_code == 200
    data = resp.json()
    assert "thread_id" in data
    assert len(data["thread_id"]) == 36  # UUID


@pytest.mark.asyncio
async def test_send_message(async_client, mock_graph):
    """Verifica que enviar un mensaje invoca al grafo y devuelve su respuesta."""
    async with async_client as client:
        resp = await client.post(
            "/api/chat",
            json={
                "thread_id": "test-thread-123",
                "message": "Quiero devolver mi pedido ORD-001",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["thread_id"] == "test-thread-123"
    assert data["response"] == "Devolución procesada correctamente."
    assert data["current_agent"] == "resolution"
    assert data["order_id"] == "ORD-001"
    assert data["is_eligible"] is True

    # Verificar que se llamó al grafo con los argumentos correctos
    mock_graph.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_message_graph_error(async_client, mock_graph):
    """Verifica que un error del grafo se propaga como 500 con el detalle del error."""
    mock_graph.ainvoke.side_effect = Exception("OpenAI timeout")

    async with async_client as client:
        resp = await client.post(
            "/api/chat",
            json={
                "thread_id": "test-thread-123",
                "message": "Hola",
            },
        )

    assert resp.status_code == 500
    assert "OpenAI timeout" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_send_message_missing_fields(async_client, mock_graph):
    """Verifica que falta el campo thread_id produce un 422 de validación."""
    async with async_client as client:
        resp = await client.post("/api/chat", json={"message": "Hola"})

    assert resp.status_code == 422  # Validation error (falta thread_id)


def _parse_sse(body: str) -> list[dict]:
    """Parsea un body SSE (``data: {...}\\n\\n`` repetido) a una lista de dicts."""
    return [
        json.loads(block[len("data: ") :])
        for block in body.strip().split("\n\n")
        if block.startswith("data: ")
    ]


@pytest.mark.asyncio
async def test_chat_stream_agent_steps_and_final(async_client, mock_graph):
    """Verifica que /api/chat/stream emite un evento SSE `agent_step` por cada
    nodo del grafo que termina, seguido de un evento `final` con la
    respuesta completa una vez el streaming acaba."""

    async def fake_astream(*args, **kwargs):
        yield {"triage": {}}
        yield {"evaluator": {}}

    mock_graph.astream = MagicMock(side_effect=fake_astream)
    mock_graph.aget_state.return_value.values = {
        "messages": [MagicMock(content="Devolución procesada correctamente.")],
        "current_agent": "resolution",
        "order_id": "ORD-001",
        "is_eligible": True,
        "resolution": "approved",
    }
    mock_graph.aget_state.return_value.next = None

    async with async_client as client:
        resp = await client.post(
            "/api/chat/stream",
            json={
                "thread_id": "test-thread-stream-1",
                "message": "Quiero devolver mi pedido ORD-001",
            },
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    assert [e["type"] for e in events] == ["agent_step", "agent_step", "final"]
    assert events[0]["agent"] == "triage"
    assert events[1]["agent"] == "evaluator"

    final_event = events[-1]
    assert final_event["content"] == "Devolución procesada correctamente."
    assert final_event["order_id"] == "ORD-001"
    assert final_event["is_eligible"] is True
    assert final_event["resolution"] == "approved"


@pytest.mark.asyncio
async def test_chat_stream_awaiting_admin_if_already_paused(async_client, mock_graph):
    """Si el thread ya está pausado por HITL antes de invocar el grafo, no
    se re-invoca `astream` -- se emite directamente un `awaiting_admin`."""
    mock_graph.aget_state.return_value.next = ("resolution",)  # cualquier tupla no vacía
    mock_graph.astream = MagicMock(side_effect=AssertionError("no debería llamarse"))

    async with async_client as client:
        resp = await client.post(
            "/api/chat/stream",
            json={
                "thread_id": "test-thread-stream-paused",
                "message": "¿Cómo va mi devolución?",
            },
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert len(events) == 1
    assert events[0]["type"] == "awaiting_admin"


@pytest.mark.asyncio
async def test_chat_stream_error_event_on_graph_exception(async_client, mock_graph):
    """Un fallo del grafo durante el streaming se traduce en un único evento
    `error`, no en una excepción sin capturar que rompa la conexión SSE."""
    mock_graph.astream = MagicMock(side_effect=Exception("OpenAI timeout"))

    async with async_client as client:
        resp = await client.post(
            "/api/chat/stream",
            json={
                "thread_id": "test-thread-stream-error",
                "message": "Hola",
            },
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "OpenAI timeout" in events[0]["content"]


@pytest.mark.asyncio
async def test_get_chat_state(async_client, mock_graph):
    """Verifica que se puede consultar el estado actual de un thread del grafo."""
    state = MagicMock()
    state.values = {
        "current_agent": "triage",
        "order_id": "ORD-001",
        "customer_name": "Ana García",
        "is_eligible": None,
        "resolution": None,
        "refund_amount": None,
    }
    mock_graph.aget_state.return_value = state

    async with async_client as client:
        resp = await client.get("/api/chat/test-thread-123/state")

    assert resp.status_code == 200
    data = resp.json()
    assert data["thread_id"] == "test-thread-123"
    assert data["current_agent"] == "triage"
    assert data["order_id"] == "ORD-001"
