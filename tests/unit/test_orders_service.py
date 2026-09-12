"""Tests unitarios para backend.services.orders_service.

Extraído de test_supabase_service.py al dividir supabase_service.py por
dominio (ver docs/REMAINING_TASKS.md #3): calculate_days_since_delivery y
get_order_details son las dos únicas funciones del dominio "pedidos".
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.services.orders_service import (
    calculate_days_since_delivery,
    get_order_details,
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
            "backend.services.orders_service.get_supabase_client",
            return_value=mock_client,
        ):
            result = await get_order_details("ord-1")

        assert "order" in result
        assert "items" in result
