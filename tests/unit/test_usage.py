"""Tests unitarios de backend/api/routers/usage.py.

Corresponde 1:1 con frontend/pages/2_Costes.py (ver
docs/defensaTFM/defenderFastAPI.md). Antes no existía ningún test para
estos dos endpoints (list_usage_sessions/get_usage_session_detail) --
hueco real detectado al dividir test_api_endpoints.py, cerrado aquí.

Mockea usage_service directamente (no el cliente Supabase): la lógica de
agregación por sesión y el cálculo de coste (pricing.py) son
responsabilidad de backend/services/usage_service.py, no de este router
-- aquí solo se comprueba que el router llama al servicio correcto y da
forma a la respuesta HTTP esperada.
"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_list_usage_sessions(async_client):
    """Verifica que se listan las sesiones con coste/latencia agregados."""
    mock_sessions = [
        {
            "thread_id": "thread-1",
            "customer_id": "cust-1",
            "customer_name": "Ana García",
            "order_id": "ord-1",
            "order_number": "ORD-2026-00081",
            "requests": 3,
            "total_tokens": 1500,
            "input_tokens": 1000,
            "output_tokens": 500,
            "cost_eur": 0.0123,
            "cost_complete": True,
            "avg_latency_ms": 850,
            "max_latency_ms": 1200,
            "last_seen": "2026-09-11T20:00:00+00:00",
        },
    ]
    with patch(
        "backend.api.routers.usage.usage_service.list_usage_sessions",
        new=AsyncMock(return_value=mock_sessions),
    ):
        async with async_client as client:
            resp = await client.get("/api/admin/usage/sessions")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["sessions"][0]["thread_id"] == "thread-1"
    assert data["sessions"][0]["cost_eur"] == 0.0123


@pytest.mark.asyncio
async def test_list_usage_sessions_respects_limit_param(async_client):
    """Verifica que el query param `limit` se pasa tal cual al servicio."""
    mock_get = AsyncMock(return_value=[])
    with patch(
        "backend.api.routers.usage.usage_service.list_usage_sessions", new=mock_get
    ):
        async with async_client as client:
            resp = await client.get("/api/admin/usage/sessions?limit=5")

    assert resp.status_code == 200
    mock_get.assert_awaited_once_with(limit=5)


@pytest.mark.asyncio
async def test_get_usage_session_detail(async_client):
    """Verifica el detalle petición a petición (tokens/latencia/coste) de una sesión."""
    mock_requests = [
        {
            "id": "req-1",
            "node": "triage",
            "model": "gpt-5-mini",
            "input_tokens": 200,
            "output_tokens": 50,
            "total_tokens": 250,
            "latency_ms": 900,
            "created_at": "2026-09-11T20:00:00+00:00",
            "cost_eur": 0.0021,
        },
        {
            "id": "req-2",
            "node": "evaluator",
            "model": "gpt-5-mini",
            "input_tokens": 800,
            "output_tokens": 150,
            "total_tokens": 950,
            "latency_ms": 1400,
            "created_at": "2026-09-11T20:00:05+00:00",
            "cost_eur": 0.0079,
        },
    ]
    with patch(
        "backend.api.routers.usage.usage_service.get_usage_detail",
        new=AsyncMock(return_value=mock_requests),
    ):
        async with async_client as client:
            resp = await client.get("/api/admin/usage/sessions/thread-1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["thread_id"] == "thread-1"
    assert data["count"] == 2
    assert data["requests"][0]["node"] == "triage"
    assert data["requests"][1]["node"] == "evaluator"


@pytest.mark.asyncio
async def test_get_usage_session_detail_empty(async_client):
    """Verifica que una sesión sin peticiones registradas devuelve una lista vacía, no un error."""
    with patch(
        "backend.api.routers.usage.usage_service.get_usage_detail",
        new=AsyncMock(return_value=[]),
    ):
        async with async_client as client:
            resp = await client.get("/api/admin/usage/sessions/thread-sin-uso")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["requests"] == []


@pytest.mark.asyncio
async def test_get_usage_trends(async_client):
    """Verifica la serie temporal por (fecha, nodo) para las gráficas de
    tendencia de 2_Costes.py."""
    mock_points = [
        {
            "date": "2026-09-11",
            "node": "triage_agent",
            "requests": 5,
            "total_tokens": 1200,
            "cost_eur": 0.005,
            "cost_complete": True,
            "avg_latency_ms": 800,
        },
    ]
    with patch(
        "backend.api.routers.usage.usage_service.get_usage_timeseries",
        new=AsyncMock(return_value=mock_points),
    ):
        async with async_client as client:
            resp = await client.get("/api/admin/usage/trends")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["points"][0]["node"] == "triage_agent"


@pytest.mark.asyncio
async def test_get_usage_trends_pasa_since_y_until_al_servicio(async_client):
    """Verifica que los query params since/until (YYYY-MM-DD) se parsean y
    se pasan tal cual al servicio."""
    mock_get = AsyncMock(return_value=[])
    with patch(
        "backend.api.routers.usage.usage_service.get_usage_timeseries", new=mock_get
    ):
        async with async_client as client:
            resp = await client.get(
                "/api/admin/usage/trends?since=2026-08-01&until=2026-08-31"
            )

    assert resp.status_code == 200
    kwargs = mock_get.call_args.kwargs
    assert str(kwargs["since"]) == "2026-08-01"
    assert str(kwargs["until"]) == "2026-08-31"


@pytest.mark.asyncio
async def test_get_usage_trends_sin_parametros_no_filtra(async_client):
    mock_get = AsyncMock(return_value=[])
    with patch(
        "backend.api.routers.usage.usage_service.get_usage_timeseries", new=mock_get
    ):
        async with async_client as client:
            resp = await client.get("/api/admin/usage/trends")

    assert resp.status_code == 200
    mock_get.assert_awaited_once_with(since=None, until=None)
