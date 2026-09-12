"""Tests unitarios de backend/api/routers/chat.py.

Corresponde 1:1 con frontend/Chat.py (ver docs/defensaTFM/defenderFastAPI.md).
Usan dependency_overrides para inyectar un mock del grafo, de modo que NO
se necesita OpenAI, Supabase ni servidores MCP.
"""

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
