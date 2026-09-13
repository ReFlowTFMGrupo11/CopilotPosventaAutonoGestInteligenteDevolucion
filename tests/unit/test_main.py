"""Tests unitarios de backend/api/main.py (app-level, fuera de cualquier router).

Usan dependency_overrides para inyectar mocks del grafo y de Supabase,
de modo que NO se necesita OpenAI, Supabase ni servidores MCP.
"""

import pytest


@pytest.mark.asyncio
async def test_health_check(async_client):
    """Verifica que /health responde 200 con el estado del servicio."""
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
