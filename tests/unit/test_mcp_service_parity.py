"""Tests de contrato MCP ↔ services/.

Por qué existe este test (ver docs/defensaTFM/defenderAgentes.md §4 y
AGENTS.md): los agentes llaman a `services/` a través de la capa MCP
(`backend/mcp/mcp_supabase.py`, `backend/mcp/mcp_logistics.py`), pero
`backend/api/routers/orders.py` y `admin.py` importan `services/`
DIRECTAMENTE, sin pasar por MCP — decisión intencional (MCP está pensado
para clientes LLM, no para una UI, ver el mismo documento), pero significa
que hay DOS caminos de código independientes hacia la misma lógica de
negocio. Nada impedía hasta ahora que una tool MCP empezara a transformar
o filtrar el resultado de su función de `services/` equivalente sin que
ningún test lo detectara — divergencia silenciosa entre lo que ve un
agente y lo que ve el panel de admin para la "misma" operación.

Estos tests no verifican lógica de negocio (ya cubierta en
test_supabase_service.py / test_logistics_service.py): verifican que cada
tool MCP sigue siendo un wrapper fino que delega 1:1 en su función de
`services/` — mismos argumentos, mismo valor de retorno sin modificar.
Si alguien añade transformación/filtrado dentro de una tool MCP, este test
debe romperse y forzar a documentar por qué ese tool ya no es un wrapper
fino.
"""

from unittest.mock import AsyncMock, patch

import pytest

from backend.models import ReturnItem, ShippingLabelItem


class TestMcpSupabaseParity:
    """backend/mcp/mcp_supabase.py debe delegar 1:1 en supabase_service."""

    @pytest.mark.asyncio
    async def test_get_order_details_is_thin_wrapper(self):
        from backend.mcp import mcp_supabase

        sentinel = {"order_number": "ORD-2026-00177"}
        with patch(
            "backend.services.supabase_service.get_order_details",
            new=AsyncMock(return_value=sentinel),
        ) as mock_fn:
            result = await mcp_supabase.get_order_details("ORD-2026-00177")

        mock_fn.assert_awaited_once_with("ORD-2026-00177")
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_get_customer_return_history_is_thin_wrapper(self):
        from backend.mcp import mcp_supabase

        sentinel = {"total_returns": 0}
        with patch(
            "backend.services.supabase_service.get_customer_return_history",
            new=AsyncMock(return_value=sentinel),
        ) as mock_fn:
            result = await mcp_supabase.get_customer_return_history("cust-uuid")

        mock_fn.assert_awaited_once_with("cust-uuid")
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_search_return_policy_is_thin_wrapper(self):
        from backend.mcp import mcp_supabase

        sentinel = {"semantic_results": []}
        with patch(
            "backend.services.supabase_service.search_return_policy",
            new=AsyncMock(return_value=sentinel),
        ) as mock_fn:
            result = await mcp_supabase.search_return_policy(
                "producto roto", "electronics", "thread-1"
            )

        mock_fn.assert_awaited_once_with("producto roto", "electronics", "thread-1")
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_create_return_record_forwards_args_unchanged(self):
        """Única transformación permitida y documentada: `ReturnItem` →
        dict vía `model_dump()`, porque es la frontera MCP/LLM (schema
        estricto) — no una transformación de negocio. Todo lo demás debe
        llegar a `services/` exactamente igual."""
        from backend.mcp import mcp_supabase

        sentinel = {"id": "return-uuid"}
        item = ReturnItem(order_item_id="item-1", quantity=1, condition="defective")
        with patch(
            "backend.services.supabase_service.create_return_record",
            new=AsyncMock(return_value=sentinel),
        ) as mock_fn:
            result = await mcp_supabase.create_return_record(
                order_id="order-uuid",
                customer_id="cust-uuid",
                reason="roto",
                reason_category="defective",
                refund_amount=19.99,
                items=[item],
                notes="",
                thread_id="thread-1",
            )

        mock_fn.assert_awaited_once_with(
            order_id="order-uuid",
            customer_id="cust-uuid",
            reason="roto",
            reason_category="defective",
            refund_amount=19.99,
            items=[item.model_dump()],
            notes="",
            thread_id="thread-1",
        )
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_update_return_status_is_thin_wrapper(self):
        from backend.mcp import mcp_supabase

        sentinel = {"status": "approved"}
        with patch(
            "backend.services.supabase_service.update_return_status",
            new=AsyncMock(return_value=sentinel),
        ) as mock_fn:
            result = await mcp_supabase.update_return_status(
                return_id="return-uuid",
                status="approved",
                resolution="full_refund",
                notes="ok",
            )

        mock_fn.assert_awaited_once_with(
            return_id="return-uuid",
            status="approved",
            resolution="full_refund",
            notes="ok",
        )
        assert result is sentinel


class TestMcpLogisticsParity:
    """backend/mcp/mcp_logistics.py debe delegar 1:1 en logistics_service."""

    @pytest.mark.asyncio
    async def test_generate_shipping_label_forwards_args_unchanged(self):
        from backend.mcp import mcp_logistics

        sentinel = {"label_path": "/tmp/label.pdf"}
        item = ShippingLabelItem(name="Microondas", quantity=1)
        with patch(
            "backend.services.logistics_service.generate_shipping_label",
            new=AsyncMock(return_value=sentinel),
        ) as mock_fn:
            result = await mcp_logistics.generate_shipping_label(
                order_id="order-uuid",
                items=[item],
                customer_name="Ana",
                customer_address="Calle Falsa 123",
            )

        mock_fn.assert_awaited_once_with(
            order_id="order-uuid",
            items=[item.model_dump()],
            customer_name="Ana",
            customer_address="Calle Falsa 123",
        )
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_send_customer_notification_is_thin_wrapper(self):
        from backend.mcp import mcp_logistics

        sentinel = {"sent": True}
        with patch(
            "backend.services.logistics_service.send_customer_notification",
            new=AsyncMock(return_value=sentinel),
        ) as mock_fn:
            result = await mcp_logistics.send_customer_notification(
                email="cliente@example.com",
                message="Tu etiqueta está lista.",
                subject="ReFlow - Actualización",
                attachment_path="/tmp/label.pdf",
            )

        mock_fn.assert_awaited_once_with(
            email="cliente@example.com",
            message="Tu etiqueta está lista.",
            subject="ReFlow - Actualización",
            attachment_path="/tmp/label.pdf",
        )
        assert result is sentinel
