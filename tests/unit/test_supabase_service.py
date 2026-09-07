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


def _make_sync_supabase_client():
    """Cliente fake con builder sync y execute async, como supabase real."""
    client = MagicMock()
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.single.return_value = query
    query.in_.return_value = query
    query.insert.return_value = query
    query.update.return_value = query
    client.table.return_value = query
    return client, query


# ---------------------------------------------------------------------------
# calculate_days_since_delivery
# ---------------------------------------------------------------------------


class TestCalculateDaysSinceDelivery:
    """Tests para la función de cálculo de días desde entrega."""

    def test_delivered_today_returns_zero(self):
        """Verifica que una entrega con fecha de hoy da 0 días transcurridos."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        result = calculate_days_since_delivery({"order": {"delivered_at": now}})
        assert result == 0

    def test_delivered_five_days_ago(self):
        """Verifica que una entrega de hace 5 días da 5 días transcurridos."""
        from datetime import datetime, timezone, timedelta

        five_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        result = calculate_days_since_delivery(
            {"order": {"delivered_at": five_days_ago}}
        )
        assert result == 5

    def test_no_delivered_at_uses_created_at(self):
        """Verifica que sin delivered_at se usa created_at como fecha de referencia."""
        from datetime import datetime, timezone, timedelta

        three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        result = calculate_days_since_delivery(
            {"order": {"created_at": three_days_ago}}
        )
        assert result == 3

    def test_no_dates_returns_9999(self):
        """Verifica que sin ninguna fecha disponible se devuelve el centinela 9999."""
        result = calculate_days_since_delivery({"order": {}})
        assert result == 9999

    def test_empty_order_returns_9999(self):
        """Verifica que un order vacío también devuelve el centinela 9999."""
        result = calculate_days_since_delivery({})
        assert result == 9999

    def test_handles_z_suffix(self):
        """Verifica que se parsean correctamente fechas ISO con sufijo 'Z' (UTC)."""
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
        """Verifica que se devuelven tanto el pedido como sus artículos."""
        mock_client, query = _make_sync_supabase_client()

        # Mock para order query
        order_chain = MagicMock()
        order_chain.data = {"id": "ord-1", "customer": {"id": "c1"}}

        items_chain = MagicMock()
        items_chain.data = [{"id": "oi-1", "product": {"name": "Item"}}]

        # Configurar la cadena de llamadas
        query.execute = AsyncMock(side_effect=[order_chain, items_chain])

        with patch(
            "backend.services.supabase_service.get_supabase_client",
            return_value=mock_client,
        ):
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
        """Verifica que el historial cuenta correctamente devoluciones aprobadas y rechazadas."""
        mock_client, query = _make_sync_supabase_client()

        resp_mock = MagicMock()
        resp_mock.data = [
            {"status": "approved"},
            {"status": "approved"},
            {"status": "rejected"},
        ]

        query.execute = AsyncMock(return_value=resp_mock)

        with patch(
            "backend.services.supabase_service.get_supabase_client",
            return_value=mock_client,
        ):
            result = await get_customer_return_history("cust-1")

        assert result["total_returns"] == 3
        assert result["approved"] == 2
        assert result["rejected"] == 1

    @pytest.mark.asyncio
    async def test_empty_history(self):
        """Verifica que un cliente sin devoluciones previas devuelve contadores a cero."""
        mock_client, query = _make_sync_supabase_client()

        resp_mock = MagicMock()
        resp_mock.data = []

        query.execute = AsyncMock(return_value=resp_mock)

        with patch(
            "backend.services.supabase_service.get_supabase_client",
            return_value=mock_client,
        ):
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
        """Verifica que se crea el registro de devolución junto con sus artículos."""
        mock_client, query = _make_sync_supabase_client()

        existing_resp = MagicMock()
        existing_resp.data = []

        return_resp = MagicMock()
        return_resp.data = [{"id": "ret-1", "status": "pending"}]

        items_resp = MagicMock()
        items_resp.data = []

        query.execute = AsyncMock(side_effect=[existing_resp, return_resp, items_resp])

        with patch(
            "backend.services.supabase_service.get_supabase_client",
            return_value=mock_client,
        ):
            result = await create_return_record(
                order_id="ord-1",
                customer_id="cust-1",
                reason="Producto defectuoso",
                reason_category="defective",
                refund_amount=79.99,
                items=[
                    {"order_item_id": "oi-1", "quantity": 1, "condition": "defective"}
                ],
            )

        assert result["return_request"]["id"] == "ret-1"
        assert result["items_created"] == 1

    @pytest.mark.asyncio
    async def test_rejects_duplicate_order_item_already_returned(self):
        """Verifica que no se puede crear una devolución duplicada del mismo order_item."""
        mock_client, query = _make_sync_supabase_client()

        existing_resp = MagicMock()
        existing_resp.data = [
            {
                "id": "ret-prev-1",
                "status": "approved",
                "return_items": [{"order_item_id": "oi-1"}],
            }
        ]

        query.execute = AsyncMock(return_value=existing_resp)

        with patch(
            "backend.services.supabase_service.get_supabase_client",
            return_value=mock_client,
        ):
            with pytest.raises(ValueError, match="devolución previa"):
                await create_return_record(
                    order_id="ord-1",
                    customer_id="cust-1",
                    reason="Producto defectuoso",
                    reason_category="defective",
                    refund_amount=79.99,
                    items=[
                        {
                            "order_item_id": "oi-1",
                            "quantity": 1,
                            "condition": "defective",
                        }
                    ],
                )


# ---------------------------------------------------------------------------
# update_return_status
# ---------------------------------------------------------------------------


class TestUpdateReturnStatus:
    """Tests para actualización de estado."""

    @pytest.mark.asyncio
    async def test_updates_status(self):
        """Verifica que se actualiza el estado y la resolución de una devolución existente."""
        mock_client, query = _make_sync_supabase_client()

        resp_mock = MagicMock()
        resp_mock.data = [{"id": "ret-1", "status": "approved"}]

        query.execute = AsyncMock(return_value=resp_mock)

        with patch(
            "backend.services.supabase_service.get_supabase_client",
            return_value=mock_client,
        ):
            result = await update_return_status(
                "ret-1", "approved", resolution="full_refund"
            )

        assert result["updated_return"]["status"] == "approved"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """Verifica que actualizar una devolución inexistente devuelve updated_return=None."""
        mock_client, query = _make_sync_supabase_client()

        resp_mock = MagicMock()
        resp_mock.data = []

        query.execute = AsyncMock(return_value=resp_mock)

        with patch(
            "backend.services.supabase_service.get_supabase_client",
            return_value=mock_client,
        ):
            result = await update_return_status("ret-nonexistent", "approved")

        assert result["updated_return"] is None
