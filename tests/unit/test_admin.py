"""Tests unitarios de backend/api/routers/admin.py.

Corresponde 1:1 con frontend/pages/1_Admin.py (ver
docs/defensaTFM/defenderFastAPI.md) -- incluye tanto las acciones propias
de administración (HITL, listar devoluciones) como get_order/
get_customer_history/get_stats, migrados desde el extinto
routers/orders.py porque su único consumidor real es esta misma página
(búsqueda de pedido + KPIs superiores del panel), nunca el chat de cliente.

Usan dependency_overrides/mocks para inyectar el grafo y Supabase, de modo
que NO se necesita OpenAI, Supabase ni servidores MCP.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_list_pending_returns(async_client, mock_supabase):
    """Verifica que se listan las devoluciones pendientes de aprobación."""
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
    """Verifica que aprobar una devolución vía HITL devuelve el número de seguimiento."""
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
async def test_approve_return_with_override_refund_amount(async_client, mock_graph):
    """Decisión 'Edit' del HITL: el admin puede corregir el importe antes
    de aprobar -- se propaga al resume del grafo para que resolution_agent
    lo use en vez del calculado por el Evaluador."""
    mock_graph.ainvoke.return_value = {
        "resolution": "approved",
        "tracking_number": "TRK-12345",
        "refund_amount": 80.0,
    }

    async with async_client as client:
        resp = await client.post(
            "/api/admin/test-thread-123/approve",
            json={
                "reason": "Importe corregido: el cliente solo pagó el envío",
                "override_refund_amount": 80.0,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["refund_amount"] == 80.0

    # El resume del grafo debe llevar el importe corregido.
    resume_command = mock_graph.ainvoke.call_args[0][0]
    assert resume_command.resume["override_refund_amount"] == 80.0
    assert resume_command.resume["approved"] is True


@pytest.mark.asyncio
async def test_approve_return_sin_override_no_edita_importe(async_client, mock_graph):
    """Aprobar sin `override_refund_amount` (caso normal) manda None -- no
    edita el importe calculado por el Evaluador."""
    mock_graph.ainvoke.return_value = {"resolution": "approved"}

    async with async_client as client:
        await client.post(
            "/api/admin/test-thread-123/approve",
            json={"reason": "Cliente VIP"},
        )

    resume_command = mock_graph.ainvoke.call_args[0][0]
    assert resume_command.resume["override_refund_amount"] is None


@pytest.mark.asyncio
async def test_reject_return(async_client, mock_graph):
    """Verifica que rechazar una devolución vía HITL devuelve resolution='rejected'."""
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
    """Verifica que aprobar un thread sin HITL pendiente devuelve un 400."""
    mock_graph.ainvoke.side_effect = Exception("No hay thread pausado")

    async with async_client as client:
        resp = await client.post("/api/admin/test-thread-123/approve")

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_returns(async_client, mock_supabase):
    """Verifica que se listan todas las devoluciones sin filtrar por estado."""
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
    """Verifica que el filtro por status en la query param se acepta y responde 200."""
    mock_supabase.table.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "ret-1", "status": "approved", "order_id": "ORD-001"},
        ]
    )

    async with async_client as client:
        resp = await client.get("/api/admin/returns?status=approved")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_return_detail(async_client, mock_supabase):
    """Verifica que se devuelve el detalle completo de una devolución
    existente, incluyendo sus return_items anidados."""
    mock_supabase.table.return_value.execute.return_value = MagicMock(
        data={
            "id": "ret-1",
            "order_id": "ORD-001",
            "status": "approved",
            "refund_amount": 150.0,
            "return_items": [
                {
                    "id": "ri-1",
                    "order_item_id": "oi-1",
                    "quantity": 1,
                    "condition": "defective",
                }
            ],
        }
    )

    async with async_client as client:
        resp = await client.get("/api/admin/returns/ret-1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "ret-1"
    assert data["order_id"] == "ORD-001"
    assert len(data["return_items"]) == 1


@pytest.mark.asyncio
async def test_get_return_detail_not_found(async_client, mock_supabase):
    """Verifica que una devolución inexistente devuelve un 404."""
    mock_supabase.table.return_value.execute.return_value = MagicMock(data=None)

    async with async_client as client:
        resp = await client.get("/api/admin/returns/ret-nonexistent")

    assert resp.status_code == 404


# ── Migrados desde el extinto routers/orders.py (mismas URLs, mismo
#    comportamiento -- solo cambia backend.api.routers.orders ->
#    backend.api.routers.admin en el target del patch) ─────────────────────


@pytest.mark.asyncio
async def test_get_order(async_client):
    """Verifica que se devuelven los detalles de un pedido existente."""
    mock_result = {
        "order": {"id": "ORD-001", "status": "delivered"},
        "items": [{"name": "Auriculares", "quantity": 1}],
    }
    with patch("backend.api.routers.admin.orders_service") as mock_svc:
        mock_svc.get_order_details = AsyncMock(return_value=mock_result)

        async with async_client as client:
            resp = await client.get("/api/orders/ORD-001")

    assert resp.status_code == 200
    data = resp.json()
    assert data["order"]["id"] == "ORD-001"


@pytest.mark.asyncio
async def test_get_order_not_found(async_client):
    """Verifica que un pedido inexistente devuelve un 404."""
    with patch("backend.api.routers.admin.orders_service") as mock_svc:
        mock_svc.get_order_details = AsyncMock(side_effect=Exception("Not found"))

        async with async_client as client:
            resp = await client.get("/api/orders/FAKE-999")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_customer_history(async_client):
    """Verifica que se devuelve el historial de devoluciones de un cliente."""
    mock_result = {
        "customer_id": "cust-001",
        "total_returns": 2,
        "approved": 1,
        "rejected": 1,
        "returns": [],
    }
    with patch("backend.api.routers.admin.returns_service") as mock_svc:
        mock_svc.get_customer_return_history = AsyncMock(return_value=mock_result)

        async with async_client as client:
            resp = await client.get("/api/customers/cust-001/history")

    assert resp.status_code == 200
    data = resp.json()
    assert data["customer_id"] == "cust-001"
    assert data["total_returns"] == 2


@pytest.mark.asyncio
async def test_get_stats(async_client, mock_supabase):
    """Verifica que las estadísticas agregadas se calculan correctamente por estado."""
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


@pytest.mark.asyncio
async def test_get_observability_links(async_client):
    """Verifica que incluye enlaces de LangFuse, estado del checkpointer y
    error rate por tool (ver tool_call_service.get_tool_call_error_rates,
    docs/defensaTFM/defenderLangfuse.md sobre por qué se agrega aquí en vez
    de solo enlazar a LangFuse)."""
    mock_error_rates = [
        {
            "tool_name": "generate_shipping_label",
            "total": 10,
            "errors": 2,
            "error_rate": 0.2,
            "avg_latency_ms": 350,
        }
    ]
    with patch(
        "backend.api.routers.admin.tool_call_service.get_tool_call_error_rates",
        new=AsyncMock(return_value=mock_error_rates),
    ):
        async with async_client as client:
            resp = await client.get("/api/admin/observability")

    assert resp.status_code == 200
    data = resp.json()
    assert data["tool_error_rates"] == mock_error_rates
    assert "checkpointer" in data
    assert "configured" in data  # de get_langfuse_links()
