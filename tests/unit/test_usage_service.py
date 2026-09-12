"""Tests unitarios de backend/services/usage_service.py.

Mockea el cliente Supabase (cadena .table().select()...().execute()), no
usage_service en sí: a diferencia de test_usage.py (que mockea
usage_service para probar solo el router), aquí se ejercita la lógica de
agregación real -- suma de tokens, latencia media/máxima, cost_complete,
y qué customer_id/order_id "gana" cuando hay varias filas por sesión.
Usa pricing.py real (ya cubierto en test_pricing.py), no lo mockea, para
verificar el cálculo de coste end-to-end dentro de la agregación.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services import usage_service


def _make_mock_supabase(table_data=None):
    """Mismo patrón que tests/unit/conftest.py::_make_mock_supabase, pero
    local a este fichero porque el target de patch es distinto
    (usage_service importa get_supabase_client directo de backend.db, no
    de supabase_service)."""
    if table_data is None:
        table_data = []
    client = MagicMock()
    query = MagicMock()
    query.select.return_value = query
    query.insert.return_value = query
    query.eq.return_value = query
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
        "backend.services.usage_service.get_supabase_client", new=fake_get_client
    )


class TestLogLlmUsage:
    @pytest.mark.asyncio
    async def test_inserta_una_fila_con_los_campos_correctos(self):
        client, patcher = _patched_client()
        with patcher:
            await usage_service.log_llm_usage(
                thread_id="thread-1",
                node="triage",
                model="gpt-5-mini",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                latency_ms=800,
                customer_id="cust-1",
                order_id="ord-1",
            )

        insert_call = client.table.return_value.insert
        insert_call.assert_called_once_with(
            {
                "thread_id": "thread-1",
                "customer_id": "cust-1",
                "order_id": "ord-1",
                "node": "triage",
                "model": "gpt-5-mini",
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "latency_ms": 800,
            }
        )

    @pytest.mark.asyncio
    async def test_customer_id_y_order_id_son_opcionales(self):
        client, patcher = _patched_client()
        with patcher:
            await usage_service.log_llm_usage(
                thread_id="thread-1",
                node="triage",
                model="gpt-5-mini",
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                latency_ms=100,
            )

        inserted = client.table.return_value.insert.call_args[0][0]
        assert inserted["customer_id"] is None
        assert inserted["order_id"] is None


class TestGetUsageBySession:
    @pytest.mark.asyncio
    async def test_sin_filas_devuelve_lista_vacia(self):
        _, patcher = _patched_client(table_data=[])
        with patcher:
            result = await usage_service.get_usage_by_session()
        assert result == []

    @pytest.mark.asyncio
    async def test_agrega_tokens_y_cuenta_peticiones_de_la_misma_sesion(self):
        rows = [
            {
                "thread_id": "thread-1",
                "customer_id": None,
                "order_id": None,
                "node": "evaluator",
                "model": "gpt-5-mini",
                "input_tokens": 800,
                "output_tokens": 150,
                "total_tokens": 950,
                "latency_ms": 1400,
                "created_at": "2026-09-11T20:00:05+00:00",
                "customers": None,
                "orders": None,
            },
            {
                "thread_id": "thread-1",
                "customer_id": "cust-1",
                "order_id": "ord-1",
                "node": "triage",
                "model": "gpt-5-mini",
                "input_tokens": 200,
                "output_tokens": 50,
                "total_tokens": 250,
                "latency_ms": 900,
                "created_at": "2026-09-11T20:00:00+00:00",
                "customers": {"full_name": "Ana García"},
                "orders": {"order_number": "ORD-2026-00081"},
            },
        ]
        _, patcher = _patched_client(table_data=rows)
        with patcher:
            result = await usage_service.get_usage_by_session()

        assert len(result) == 1
        session = result[0]
        assert session["thread_id"] == "thread-1"
        assert session["requests"] == 2
        assert session["total_tokens"] == 1200  # 950 + 250
        assert session["input_tokens"] == 1000
        assert session["output_tokens"] == 200
        assert session["avg_latency_ms"] == round((1400 + 900) / 2)
        assert session["max_latency_ms"] == 1400

    @pytest.mark.asyncio
    async def test_toma_el_primer_customer_id_no_nulo_como_el_mas_reciente(self):
        """Las filas llegan en orden `created_at desc` (más reciente primero,
        ver el .order() de la query real) -- la primera fila con
        customer_id/order_id no nulo debe "ganar", aunque venga después en
        la lista de filas de este test si simulase desorden."""
        rows = [
            {  # más reciente (primera en la lista, como llegaría de la query)
                "thread_id": "thread-1",
                "customer_id": "cust-nuevo",
                "order_id": "ord-nuevo",
                "node": "resolution",
                "model": "gpt-5-mini",
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "latency_ms": 500,
                "created_at": "2026-09-11T20:05:00+00:00",
                "customers": {"full_name": "Cliente Nuevo"},
                "orders": {"order_number": "ORD-NUEVO"},
            },
            {  # más antigua, con datos de un pedido ANTERIOR en el mismo hilo
                "thread_id": "thread-1",
                "customer_id": "cust-viejo",
                "order_id": "ord-viejo",
                "node": "triage",
                "model": "gpt-5-mini",
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "latency_ms": 500,
                "created_at": "2026-09-11T20:00:00+00:00",
                "customers": {"full_name": "Cliente Viejo"},
                "orders": {"order_number": "ORD-VIEJO"},
            },
        ]
        _, patcher = _patched_client(table_data=rows)
        with patcher:
            result = await usage_service.get_usage_by_session()

        session = result[0]
        assert session["customer_id"] == "cust-nuevo"
        assert session["order_number"] == "ORD-NUEVO"

    @pytest.mark.asyncio
    async def test_modelo_sin_precio_marca_cost_complete_false(self):
        rows = [
            {
                "thread_id": "thread-1",
                "customer_id": None,
                "order_id": None,
                "node": "triage",
                "model": "modelo-sin-precio-conocido",
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "latency_ms": 500,
                "created_at": "2026-09-11T20:00:00+00:00",
                "customers": None,
                "orders": None,
            },
        ]
        _, patcher = _patched_client(table_data=rows)
        with patcher:
            result = await usage_service.get_usage_by_session()

        assert result[0]["cost_complete"] is False
        assert result[0]["cost_eur"] == 0.0

    @pytest.mark.asyncio
    async def test_calcula_coste_real_con_modelo_conocido(self, monkeypatch):
        monkeypatch.setenv("USD_TO_EUR_RATE", "1.0")
        rows = [
            {
                "thread_id": "thread-1",
                "customer_id": None,
                "order_id": None,
                "node": "triage",
                "model": "gpt-5-mini",
                "input_tokens": 1_000_000,
                "output_tokens": 1_000_000,
                "total_tokens": 2_000_000,
                "latency_ms": 500,
                "created_at": "2026-09-11T20:00:00+00:00",
                "customers": None,
                "orders": None,
            },
        ]
        _, patcher = _patched_client(table_data=rows)
        with patcher:
            result = await usage_service.get_usage_by_session()

        assert result[0]["cost_complete"] is True
        assert result[0]["cost_eur"] == pytest.approx(2.25)  # 0.25 + 2.00

    @pytest.mark.asyncio
    async def test_respeta_el_limite_de_sesiones_devueltas(self):
        rows = [
            {
                "thread_id": f"thread-{i}",
                "customer_id": None,
                "order_id": None,
                "node": "triage",
                "model": "gpt-5-mini",
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "latency_ms": 100,
                "created_at": f"2026-09-11T20:0{i}:00+00:00",
                "customers": None,
                "orders": None,
            }
            for i in range(5)
        ]
        _, patcher = _patched_client(table_data=rows)
        with patcher:
            result = await usage_service.get_usage_by_session(limit=2)

        assert len(result) == 2


class TestGetUsageDetail:
    @pytest.mark.asyncio
    async def test_sin_filas_devuelve_lista_vacia(self):
        _, patcher = _patched_client(table_data=[])
        with patcher:
            result = await usage_service.get_usage_detail("thread-sin-uso")
        assert result == []

    @pytest.mark.asyncio
    async def test_filtra_por_thread_id(self):
        client, patcher = _patched_client(table_data=[])
        with patcher:
            await usage_service.get_usage_detail("thread-123")

        client.table.return_value.eq.assert_called_once_with(
            "thread_id", "thread-123"
        )

    @pytest.mark.asyncio
    async def test_anade_cost_eur_a_cada_fila(self, monkeypatch):
        monkeypatch.setenv("USD_TO_EUR_RATE", "1.0")
        rows = [
            {
                "id": "req-1",
                "node": "triage",
                "model": "gpt-5-mini",
                "input_tokens": 1_000_000,
                "output_tokens": 0,
                "total_tokens": 1_000_000,
                "latency_ms": 900,
                "created_at": "2026-09-11T20:00:00+00:00",
            },
        ]
        _, patcher = _patched_client(table_data=rows)
        with patcher:
            result = await usage_service.get_usage_detail("thread-1")

        assert result[0]["cost_eur"] == pytest.approx(0.25)

    @pytest.mark.asyncio
    async def test_modelo_desconocido_da_cost_eur_none(self, monkeypatch):
        monkeypatch.delenv(
            "LLM_PRICE_MODELO_RARO_INPUT_PER_1M", raising=False
        )
        rows = [
            {
                "id": "req-1",
                "node": "triage",
                "model": "modelo-raro",
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "latency_ms": 100,
                "created_at": "2026-09-11T20:00:00+00:00",
            },
        ]
        _, patcher = _patched_client(table_data=rows)
        with patcher:
            result = await usage_service.get_usage_detail("thread-1")

        assert result[0]["cost_eur"] is None
