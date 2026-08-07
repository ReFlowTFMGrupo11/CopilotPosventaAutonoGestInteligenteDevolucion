"""Tests unitarios para backend.services.supabase_service."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.services.supabase_service import (
    calculate_days_since_delivery,
    get_order_details,
    get_customer_return_history,
    create_return_record,
    update_return_status,
)


# ---------------------------------------------------------------------------
# calculate_days_since_delivery
# ---------------------------------------------------------------------------


class TestCalculateDaysSinceDelivery:
    """Tests para la función de cálculo de días desde entrega."""

    def test_delivered_today_returns_zero(self):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        result = calculate_days_since_delivery({"order": {"delivered_at": now}})
        assert result == 0

    def test_delivered_five_days_ago(self):
        from datetime import datetime, timezone, timedelta

        five_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        result = calculate_days_since_delivery({"order": {"delivered_at": five_days_ago}})
        assert result == 5

    def test_no_delivered_at_uses_created_at(self):
        from datetime import datetime, timezone, timedelta

        three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        result = calculate_days_since_delivery({"order": {"created_at": three_days_ago}})
        assert result == 3

    def test_no_dates_returns_9999(self):
        result = calculate_days_since_delivery({"order": {}})
        assert result == 9999

    def test_empty_order_returns_9999(self):
        result = calculate_days_since_delivery({})
        assert result == 9999

    def test_handles_z_suffix(self):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = calculate_days_since_delivery({"order": {"delivered_at": now}})
        assert result == 0


# ---------------------------------------------------------------------------
# get_order_details
# ---------------------------------------------------------------------------


class TestGetOrderDetails:
    """Tests para consulta de detalles del pedido."""

    @pytest.mark.asyncio
    async def test_returns_order_and_items(self):
        # MagicMock, no AsyncMock: el builder de Supabase (.table/.select/
        # .eq/.update/.insert/.order/.single...) es síncrono, solo
        # .execute() es async. Un AsyncMock() sin spec propaga "asyncness"
        # a TODOS sus hijos por defecto, así que client.table(...) devolvería
        # una coroutine en vez de encadenar — por eso se fuerza MagicMock
        # aquí y solo .execute se declara AsyncMock explícitamente abajo.
        mock_client = MagicMock()

        # Mock para order query
        order_chain = AsyncMock()
        order_chain.data = {"id": "ord-1", "customer": {"id": "c1"}}

        items_chain = AsyncMock()
        items_chain.data = [{"id": "oi-1", "product": {"name": "Item"}}]

        # Configurar la cadena de llamadas
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute = AsyncMock(return_value=order_chain)
        mock_client.table.return_value.select.return_value.eq.return_value.execute = AsyncMock(return_value=items_chain)

        with patch("backend.services.supabase_service.get_supabase_client", return_value=mock_client):
            result = await get_order_details("ord-1")

        assert "order" in result
        assert "items" in result


# ---------------------------------------------------------------------------
# get_customer_return_history
# ---------------------------------------------------------------------------


class TestGetCustomerReturnHistory:
    """Tests para historial de devoluciones."""

    @pytest.mark.asyncio
    async def test_counts_approved_and_rejected(self):
        # MagicMock, no AsyncMock: el builder de Supabase (.table/.select/
        # .eq/.update/.insert/.order/.single...) es síncrono, solo
        # .execute() es async. Un AsyncMock() sin spec propaga "asyncness"
        # a TODOS sus hijos por defecto, así que client.table(...) devolvería
        # una coroutine en vez de encadenar — por eso se fuerza MagicMock
        # aquí y solo .execute se declara AsyncMock explícitamente abajo.
        mock_client = MagicMock()

        resp_mock = AsyncMock()
        resp_mock.data = [
            {"status": "approved"},
            {"status": "approved"},
            {"status": "rejected"},
        ]

        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute = AsyncMock(return_value=resp_mock)

        with patch("backend.services.supabase_service.get_supabase_client", return_value=mock_client):
            result = await get_customer_return_history("cust-1")

        assert result["total_returns"] == 3
        assert result["approved"] == 2
        assert result["rejected"] == 1

    @pytest.mark.asyncio
    async def test_empty_history(self):
        # MagicMock, no AsyncMock: el builder de Supabase (.table/.select/
        # .eq/.update/.insert/.order/.single...) es síncrono, solo
        # .execute() es async. Un AsyncMock() sin spec propaga "asyncness"
        # a TODOS sus hijos por defecto, así que client.table(...) devolvería
        # una coroutine en vez de encadenar — por eso se fuerza MagicMock
        # aquí y solo .execute se declara AsyncMock explícitamente abajo.
        mock_client = MagicMock()

        resp_mock = AsyncMock()
        resp_mock.data = []

        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute = AsyncMock(return_value=resp_mock)

        with patch("backend.services.supabase_service.get_supabase_client", return_value=mock_client):
            result = await get_customer_return_history("cust-1")

        assert result["total_returns"] == 0
        assert result["approved"] == 0
        assert result["rejected"] == 0


# ---------------------------------------------------------------------------
# create_return_record
# ---------------------------------------------------------------------------


class TestCreateReturnRecord:
    """Tests para creación de devoluciones."""

    @pytest.mark.asyncio
    async def test_creates_return_and_items(self):
        # MagicMock, no AsyncMock: el builder de Supabase (.table/.select/
        # .eq/.update/.insert/.order/.single...) es síncrono, solo
        # .execute() es async. Un AsyncMock() sin spec propaga "asyncness"
        # a TODOS sus hijos por defecto, así que client.table(...) devolvería
        # una coroutine en vez de encadenar — por eso se fuerza MagicMock
        # aquí y solo .execute se declara AsyncMock explícitamente abajo.
        mock_client = MagicMock()

        return_resp = AsyncMock()
        return_resp.data = [{"id": "ret-1", "status": "pending"}]

        items_resp = AsyncMock()
        items_resp.data = []

        mock_client.table.return_value.insert.return_value.execute = AsyncMock(
            side_effect=[return_resp, items_resp]
        )

        with patch("backend.services.supabase_service.get_supabase_client", return_value=mock_client):
            result = await create_return_record(
                order_id="ord-1",
                customer_id="cust-1",
                reason="Producto defectuoso",
                reason_category="defective",
                refund_amount=79.99,
                items=[{"order_item_id": "oi-1", "quantity": 1, "condition": "defective"}],
            )

        assert result["return_request"]["id"] == "ret-1"
        assert result["items_created"] == 1


# ---------------------------------------------------------------------------
# update_return_status
# ---------------------------------------------------------------------------


class TestUpdateReturnStatus:
    """Tests para actualización de estado."""

    @pytest.mark.asyncio
    async def test_updates_status(self):
        # MagicMock, no AsyncMock: el builder de Supabase (.table/.select/
        # .eq/.update/.insert/.order/.single...) es síncrono, solo
        # .execute() es async. Un AsyncMock() sin spec propaga "asyncness"
        # a TODOS sus hijos por defecto, así que client.table(...) devolvería
        # una coroutine en vez de encadenar — por eso se fuerza MagicMock
        # aquí y solo .execute se declara AsyncMock explícitamente abajo.
        mock_client = MagicMock()

        resp_mock = AsyncMock()
        resp_mock.data = [{"id": "ret-1", "status": "approved"}]

        mock_client.table.return_value.update.return_value.eq.return_value.execute = AsyncMock(return_value=resp_mock)

        with patch("backend.services.supabase_service.get_supabase_client", return_value=mock_client):
            result = await update_return_status("ret-1", "approved", resolution="full_refund")

        assert result["updated_return"]["status"] == "approved"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        # MagicMock, no AsyncMock: el builder de Supabase (.table/.select/
        # .eq/.update/.insert/.order/.single...) es síncrono, solo
        # .execute() es async. Un AsyncMock() sin spec propaga "asyncness"
        # a TODOS sus hijos por defecto, así que client.table(...) devolvería
        # una coroutine en vez de encadenar — por eso se fuerza MagicMock
        # aquí y solo .execute se declara AsyncMock explícitamente abajo.
        mock_client = MagicMock()

        resp_mock = AsyncMock()
        resp_mock.data = []

        mock_client.table.return_value.update.return_value.eq.return_value.execute = AsyncMock(return_value=resp_mock)

        with patch("backend.services.supabase_service.get_supabase_client", return_value=mock_client):
            result = await update_return_status("ret-nonexistent", "approved")

        assert result["updated_return"] is None
