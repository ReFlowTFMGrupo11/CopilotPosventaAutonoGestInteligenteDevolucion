"""Tests unitarios de backend/services/tool_call_service.py.

Mockea el cliente Supabase (cadena .table().select()...().execute()), no
tool_call_service en sí -- mismo patrón que test_usage_service.py: aquí se
ejercita la lógica de agregación real (error_rate, latencia media por
tool), no solo que se llame al servicio correcto.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services import tool_call_service


def _make_mock_supabase(table_data=None):
    if table_data is None:
        table_data = []
    client = MagicMock()
    query = MagicMock()
    query.select.return_value = query
    query.insert.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.execute = AsyncMock(return_value=MagicMock(data=table_data))
    client.table.return_value = query
    return client


def _patched_client(table_data=None):
    client = _make_mock_supabase(table_data)

    async def fake_get_client():
        return client

    return client, patch(
        "backend.services.tool_call_service.get_supabase_client", new=fake_get_client
    )


class TestLogToolCall:
    @pytest.mark.asyncio
    async def test_inserta_una_fila_con_los_campos_correctos(self):
        client, patcher = _patched_client()
        with patcher:
            await tool_call_service.log_tool_call(
                tool_name="create_return_record",
                success=True,
                latency_ms=250,
                thread_id="thread-1",
                error_message=None,
            )

        client.table.return_value.insert.assert_called_once_with(
            {
                "thread_id": "thread-1",
                "tool_name": "create_return_record",
                "success": True,
                "error_message": None,
                "latency_ms": 250,
            }
        )

    @pytest.mark.asyncio
    async def test_thread_id_y_error_message_son_opcionales(self):
        client, patcher = _patched_client()
        with patcher:
            await tool_call_service.log_tool_call(
                tool_name="get_order_details", success=False, latency_ms=50
            )

        inserted = client.table.return_value.insert.call_args[0][0]
        assert inserted["thread_id"] is None
        assert inserted["error_message"] is None
        assert inserted["success"] is False


class TestGetToolCallErrorRates:
    @pytest.mark.asyncio
    async def test_sin_filas_devuelve_lista_vacia(self):
        _, patcher = _patched_client(table_data=[])
        with patcher:
            result = await tool_call_service.get_tool_call_error_rates()
        assert result == []

    @pytest.mark.asyncio
    async def test_agrega_total_y_errores_por_tool(self):
        rows = [
            {
                "tool_name": "generate_shipping_label",
                "success": True,
                "latency_ms": 100,
                "created_at": "2026-09-13T20:00:02+00:00",
            },
            {
                "tool_name": "generate_shipping_label",
                "success": False,
                "latency_ms": 300,
                "created_at": "2026-09-13T20:00:01+00:00",
            },
            {
                "tool_name": "generate_shipping_label",
                "success": True,
                "latency_ms": 200,
                "created_at": "2026-09-13T20:00:00+00:00",
            },
        ]
        _, patcher = _patched_client(table_data=rows)
        with patcher:
            result = await tool_call_service.get_tool_call_error_rates()

        assert len(result) == 1
        entry = result[0]
        assert entry["tool_name"] == "generate_shipping_label"
        assert entry["total"] == 3
        assert entry["errors"] == 1
        assert entry["error_rate"] == pytest.approx(1 / 3, abs=1e-4)
        assert entry["avg_latency_ms"] == round((100 + 300 + 200) / 3)

    @pytest.mark.asyncio
    async def test_ordena_por_error_rate_descendente(self):
        rows = [
            {
                "tool_name": "tool_sin_errores",
                "success": True,
                "latency_ms": 100,
                "created_at": "2026-09-13T20:00:01+00:00",
            },
            {
                "tool_name": "tool_con_errores",
                "success": False,
                "latency_ms": 100,
                "created_at": "2026-09-13T20:00:00+00:00",
            },
        ]
        _, patcher = _patched_client(table_data=rows)
        with patcher:
            result = await tool_call_service.get_tool_call_error_rates()

        assert [entry["tool_name"] for entry in result] == [
            "tool_con_errores",
            "tool_sin_errores",
        ]

    @pytest.mark.asyncio
    async def test_pasa_el_limite_a_la_query(self):
        client, patcher = _patched_client(table_data=[])
        with patcher:
            await tool_call_service.get_tool_call_error_rates(limit=50)

        client.table.return_value.limit.assert_called_once_with(50)
