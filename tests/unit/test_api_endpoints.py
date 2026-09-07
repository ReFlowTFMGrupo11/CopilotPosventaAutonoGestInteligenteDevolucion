"""Tests unitarios de los endpoints FastAPI.

Usan dependency_overrides para inyectar mocks del grafo y de Supabase,
de modo que NO se necesita OpenAI, Supabase ni servidores MCP.
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from backend.api.main import app
from backend.api.dependencies import get_graph

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_mock_graph(ainvoke_return=None, aget_state_return=None):
    """Crea un mock del grafo con respuestas configurables."""
    graph = AsyncMock()

    if ainvoke_return is None:
        ainvoke_return = {
            "messages": [MagicMock(content="Devolución procesada correctamente.")],
            "current_agent": "resolution",
            "order_id": "ORD-001",
            "is_eligible": True,
            "resolution": "approved",
        }
    graph.ainvoke.return_value = ainvoke_return

    if aget_state_return is None:
        state = MagicMock()
        state.values = {}
        state.next = None
        aget_state_return = state
    graph.aget_state.return_value = aget_state_return

    return graph


def _make_mock_supabase(table_data=None):
    """Crea un mock del cliente Supabase.

    client.table() es síncrono, la cadena .select().eq()... también,
    solo .execute() es async.
    """
    if table_data is None:
        table_data = []

    client = MagicMock()
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.single.return_value = query
    query.execute = AsyncMock(return_value=MagicMock(data=table_data))
    client.table.return_value = query

    return client


@pytest.fixture
def mock_graph():
    """Fixture: grafo mock inyectado via dependency_overrides."""
    graph = _make_mock_graph()

    async def override():
        return graph

    app.dependency_overrides[get_graph] = override
    yield graph
    app.dependency_overrides.clear()


@pytest.fixture
def mock_supabase():
    """Fixture: mock de get_supabase_client (async)."""
    client = _make_mock_supabase()

    async def fake_get_client():
        return client

    with patch(
        "backend.services.supabase_service.get_supabase_client", new=fake_get_client
    ):
        yield client


@pytest.fixture
def async_client():
    """Fixture: cliente HTTP async para testear la app."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ── Tests: Health ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_check(async_client):
    async with async_client as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "reflow-api"
    # checkpointer: ver backend/agents/graph.py::get_checkpointer_status.
    # Sin build_return_graph() invocado en este proceso de test, viene a
    # None (no se ha construido ningún grafo todavía).
    assert "checkpointer" in body


# ── Tests: Chat ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_chat(async_client):
    async with async_client as client:
        resp = await client.post("/api/chat/new")

    assert resp.status_code == 200
    data = resp.json()
    assert "thread_id" in data
    assert len(data["thread_id"]) == 36  # UUID


@pytest.mark.asyncio
async def test_send_message(async_client, mock_graph):
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
    async with async_client as client:
        resp = await client.post("/api/chat", json={"message": "Hola"})

    assert resp.status_code == 422  # Validation error (falta thread_id)


@pytest.mark.asyncio
async def test_get_chat_state(async_client, mock_graph):
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


# ── Tests: Admin ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_pending_returns(async_client, mock_supabase):
    # Configurar datos de retorno
    mock_supabase.table.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "ret-1",
                "order_id": "ORD-001",
                "customer_id": "cust-1",
                "reason": "Defectuoso",
                "refund_amount": 150.0,
                "created_at": "2026-08-01",
            },
        ]
    )

    async with async_client as client:
        resp = await client.get("/api/admin/pending")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["pending"][0]["order_id"] == "ORD-001"


@pytest.mark.asyncio
async def test_approve_return(async_client, mock_graph):
    mock_graph.ainvoke.return_value = {
        "resolution": "approved",
        "tracking_number": "TRK-12345",
    }

    async with async_client as client:
        resp = await client.post(
            "/api/admin/test-thread-123/approve",
            json={
                "reason": "Cliente VIP",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["thread_id"] == "test-thread-123"
    assert data["resolution"] == "approved"
    assert data["tracking_number"] == "TRK-12345"


@pytest.mark.asyncio
async def test_reject_return(async_client, mock_graph):
    mock_graph.ainvoke.return_value = {
        "resolution": "rejected",
    }

    async with async_client as client:
        resp = await client.post(
            "/api/admin/test-thread-123/reject",
            json={
                "reason": "Fuera de plazo",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["resolution"] == "rejected"


@pytest.mark.asyncio
async def test_approve_return_graph_error(async_client, mock_graph):
    mock_graph.ainvoke.side_effect = Exception("No hay thread pausado")

    async with async_client as client:
        resp = await client.post("/api/admin/test-thread-123/approve")

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_returns(async_client, mock_supabase):
    mock_supabase.table.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "ret-1", "status": "approved", "order_id": "ORD-001"},
            {"id": "ret-2", "status": "rejected", "order_id": "ORD-002"},
        ]
    )

    async with async_client as client:
        resp = await client.get("/api/admin/returns")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2


@pytest.mark.asyncio
async def test_list_returns_with_status_filter(async_client, mock_supabase):
    mock_supabase.table.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "ret-1", "status": "approved", "order_id": "ORD-001"},
        ]
    )

    async with async_client as client:
        resp = await client.get("/api/admin/returns?status=approved")

    assert resp.status_code == 200


# ── Tests: Orders ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_order(async_client):
    mock_result = {
        "order": {"id": "ORD-001", "status": "delivered"},
        "items": [{"name": "Auriculares", "quantity": 1}],
    }
    with patch("backend.api.routers.orders.supabase_service") as mock_svc:
        mock_svc.get_order_details = AsyncMock(return_value=mock_result)

        async with async_client as client:
            resp = await client.get("/api/orders/ORD-001")

    assert resp.status_code == 200
    data = resp.json()
    assert data["order"]["id"] == "ORD-001"


@pytest.mark.asyncio
async def test_get_order_not_found(async_client):
    with patch("backend.api.routers.orders.supabase_service") as mock_svc:
        mock_svc.get_order_details = AsyncMock(side_effect=Exception("Not found"))

        async with async_client as client:
            resp = await client.get("/api/orders/FAKE-999")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_customer_history(async_client):
    mock_result = {
        "customer_id": "cust-001",
        "total_returns": 2,
        "approved": 1,
        "rejected": 1,
        "returns": [],
    }
    with patch("backend.api.routers.orders.supabase_service") as mock_svc:
        mock_svc.get_customer_return_history = AsyncMock(return_value=mock_result)

        async with async_client as client:
            resp = await client.get("/api/customers/cust-001/history")

    assert resp.status_code == 200
    data = resp.json()
    assert data["customer_id"] == "cust-001"
    assert data["total_returns"] == 2


@pytest.mark.asyncio
async def test_get_stats(async_client, mock_supabase):
    mock_supabase.table.return_value.execute.return_value = MagicMock(
        data=[
            {"status": "approved"},
            {"status": "approved"},
            {"status": "rejected"},
            {"status": "pending_approval"},
        ]
    )

    async with async_client as client:
        resp = await client.get("/api/stats")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_returns"] == 4
    assert data["approved"] == 2
    assert data["rejected"] == 1
    assert data["pending"] == 1
    assert data["approval_rate"] == 50.0
