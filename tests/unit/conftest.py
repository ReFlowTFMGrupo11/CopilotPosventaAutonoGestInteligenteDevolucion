"""Fixtures compartidos por los tests unitarios de endpoints FastAPI
(test_main.py, test_chat.py, test_admin.py, test_usage.py).

Antes vivían duplicados dentro de test_api_endpoints.py (un solo fichero
que cubría los 3 routers a la vez); al dividir ese fichero siguiendo la
misma frontera 1:1 router<->página del frontend (ver
docs/defensaTFM/defenderFastAPI.md), estos fixtures pasan a este
conftest.py de `tests/unit/` para que los 4 ficheros de test puedan
usarlos sin duplicar código ni depender entre sí.
"""

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
        """Sustituye a get_graph: devuelve el grafo mock en vez del real.

        Returns:
            El grafo mock (AsyncMock) creado por _make_mock_graph().
        """
        return graph

    app.dependency_overrides[get_graph] = override
    yield graph
    app.dependency_overrides.clear()


@pytest.fixture
def mock_supabase():
    """Fixture: mock de get_supabase_client (async)."""
    client = _make_mock_supabase()

    async def fake_get_client():
        """Sustituye a get_supabase_client: devuelve el cliente mock.

        Returns:
            El cliente Supabase mock creado por _make_mock_supabase().
        """
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
