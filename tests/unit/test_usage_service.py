"""Tests unitarios de backend/services/usage_service.py.

Mockea el cliente Supabase (cadena .table().select()...().execute()), no
usage_service en sí: a diferencia de test_usage.py (que mockea
usage_service para probar solo el router), aquí se ejercita la lógica de
agregación real -- suma de tokens, latencia media/máxima, cost_complete,
y qué customer_id/order_id "gana" cuando hay varias filas por sesión.

`cost_eur` se calcula una sola vez en `log_llm_usage()` (con pricing.py
real, ya cubierto en test_pricing.py) y se congela en la fila -- ver
supabase/migrations/016_add_cost_to_llm_usage.sql y
docs/REMAINING_TASKS.md §2. `list_usage_sessions()`/`get_usage_detail()`
solo agregan/devuelven ese valor ya calculado, nunca vuelven a llamar a
pricing.py -- de ahí que varios tests mockeen `usage_service.pricing` para
comprobar explícitamente que NO se invoca en tiempo de lectura.

pricing.py lee el tipo de cambio de `Settings.usd_to_eur_rate`
(env var `USD_TO_EUR_RATE`, ver backend/config.py), cacheado con
`@lru_cache` -- el test que fija esa env var limpia la cache antes/después
(mismo patrón que tests/unit/test_llm_factory.py).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.config import get_settings
from backend.services import usage_service


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """pricing.py lee USD_TO_EUR_RATE/LLM_PRICES_JSON vía Settings, cacheado
    con @lru_cache -- limpiar antes/después evita que un test que fije esas
    env vars contamine los siguientes (mismo patrón que
    tests/unit/test_llm_factory.py y tests/unit/test_pricing.py)."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
    async def test_inserta_una_fila_con_los_campos_correctos(self, monkeypatch):
        monkeypatch.setenv("USD_TO_EUR_RATE", "1.0")
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
                "cost_eur": pytest.approx(0.000125),  # 100*0.25/1M + 50*2.00/1M
            }
        )

    @pytest.mark.asyncio
    async def test_congela_cost_eur_none_si_el_modelo_no_tiene_precio(self):
        client, patcher = _patched_client()
        with patcher:
            await usage_service.log_llm_usage(
                thread_id="thread-1",
                node="triage",
                model="modelo-sin-precio-conocido",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                latency_ms=800,
            )

        inserted = client.table.return_value.insert.call_args[0][0]
        assert inserted["cost_eur"] is None

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
            result = await usage_service.list_usage_sessions()
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
                "cost_eur": 0.0005,
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
                "cost_eur": 0.0001,
                "created_at": "2026-09-11T20:00:00+00:00",
                "customers": {"full_name": "Ana García"},
                "orders": {"order_number": "ORD-2026-00081"},
            },
        ]
        _, patcher = _patched_client(table_data=rows)
        with patcher:
            result = await usage_service.list_usage_sessions()

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
                "cost_eur": 0.00001,
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
                "cost_eur": 0.00001,
                "created_at": "2026-09-11T20:00:00+00:00",
                "customers": {"full_name": "Cliente Viejo"},
                "orders": {"order_number": "ORD-VIEJO"},
            },
        ]
        _, patcher = _patched_client(table_data=rows)
        with patcher:
            result = await usage_service.list_usage_sessions()

        session = result[0]
        assert session["customer_id"] == "cust-nuevo"
        assert session["order_number"] == "ORD-NUEVO"

    @pytest.mark.asyncio
    async def test_fila_con_cost_eur_none_marca_cost_complete_false(self):
        """`cost_eur=None` significa que el modelo no tenía precio configurado
        EN EL MOMENTO de la llamada (congelado por log_llm_usage) -- la
        agregación no debe intentar recalcularlo con el precio de hoy."""
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
                "cost_eur": None,
                "created_at": "2026-09-11T20:00:00+00:00",
                "customers": None,
                "orders": None,
            },
        ]
        _, patcher = _patched_client(table_data=rows)
        with patcher:
            result = await usage_service.list_usage_sessions()

        assert result[0]["cost_complete"] is False
        assert result[0]["cost_eur"] == 0.0

    @pytest.mark.asyncio
    async def test_suma_el_cost_eur_ya_congelado_sin_recalcularlo(self):
        """La agregación debe limitarse a sumar `cost_eur` tal cual viene de
        la fila -- no debe llamar a pricing.py en tiempo de lectura (ver
        docs/REMAINING_TASKS.md §2)."""
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
                "cost_eur": 2.25,
                "created_at": "2026-09-11T20:00:00+00:00",
                "customers": None,
                "orders": None,
            },
        ]
        _, patcher = _patched_client(table_data=rows)
        with patch("backend.services.usage_service.pricing") as mock_pricing:
            with patcher:
                result = await usage_service.list_usage_sessions()

        mock_pricing.estimate_cost_eur.assert_not_called()
        assert result[0]["cost_complete"] is True
        assert result[0]["cost_eur"] == pytest.approx(2.25)

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
            result = await usage_service.list_usage_sessions(limit=2)

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

        client.table.return_value.eq.assert_called_once_with("thread_id", "thread-123")

    @pytest.mark.asyncio
    async def test_devuelve_el_cost_eur_ya_congelado_sin_recalcularlo(self):
        """El detalle no debe llamar a pricing.py: `cost_eur` ya viene
        calculado y congelado desde log_llm_usage (ver
        docs/REMAINING_TASKS.md §2)."""
        rows = [
            {
                "id": "req-1",
                "node": "triage",
                "model": "gpt-5-mini",
                "input_tokens": 1_000_000,
                "output_tokens": 0,
                "total_tokens": 1_000_000,
                "latency_ms": 900,
                "cost_eur": 0.25,
                "created_at": "2026-09-11T20:00:00+00:00",
            },
        ]
        _, patcher = _patched_client(table_data=rows)
        with patch("backend.services.usage_service.pricing") as mock_pricing:
            with patcher:
                result = await usage_service.get_usage_detail("thread-1")

        mock_pricing.estimate_cost_eur.assert_not_called()
        assert result[0]["cost_eur"] == pytest.approx(0.25)

    @pytest.mark.asyncio
    async def test_modelo_desconocido_da_cost_eur_none(self):
        """`cost_eur=None` congelado (modelo sin precio conocido cuando se
        hizo la llamada) se devuelve tal cual, no se rellena a posteriori."""
        rows = [
            {
                "id": "req-1",
                "node": "triage",
                "model": "modelo-raro",
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "latency_ms": 100,
                "cost_eur": None,
                "created_at": "2026-09-11T20:00:00+00:00",
            },
        ]
        _, patcher = _patched_client(table_data=rows)
        with patcher:
            result = await usage_service.get_usage_detail("thread-1")

        assert result[0]["cost_eur"] is None
