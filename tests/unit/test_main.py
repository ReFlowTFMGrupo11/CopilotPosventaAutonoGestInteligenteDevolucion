"""Tests unitarios de backend/api/main.py (app-level, fuera de cualquier router).

Usan dependency_overrides para inyectar mocks del grafo y de Supabase,
de modo que NO se necesita OpenAI, Supabase ni servidores MCP.

`async_client` (ASGITransport) NO dispara lifespan (startup/shutdown) --
por eso test_health_check ve checkpointer=None (ningún grafo construido
todavía). Los tests de `TestLifespan` invocan `lifespan(app)` directamente
como context manager async, mockeando get_return_graph/get_langfuse/
pricing para no depender de OpenAI/Supabase/Langfuse reales.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.main import app, lifespan


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


class TestLifespanMissingPricesWarning:
    """pricing.configured_models_missing_price() se comprueba al arrancar
    (ver docstring de main.py::lifespan). El log es la señal garantizada
    (funciona sin Langfuse configurado); el evento a Langfuse es un canal
    EXTRA, no un sustituto -- mismo patrón que checkpointer_degraded en
    graph.py."""

    @pytest.mark.asyncio
    async def test_sin_modelos_sin_precio_no_hace_nada(self):
        with (
            patch(
                "backend.api.main.get_return_graph", new=AsyncMock(return_value=None)
            ),
            patch("backend.api.main.get_langfuse", return_value=None),
            patch(
                "backend.api.main.pricing.configured_models_missing_price",
                return_value=[],
            ),
            patch("backend.api.main.logger") as mock_logger,
        ):
            async with lifespan(app):
                pass

        mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_con_modelo_sin_precio_loguea_aunque_no_haya_langfuse(self):
        """El aviso debe salir SIEMPRE por log, incluso sin Langfuse
        configurado -- no puede depender de un servicio opcional para dar
        una señal (mismo principio que justifica el dashboard propio, ver
        defenderDashboardCostes.md §4)."""
        with (
            patch(
                "backend.api.main.get_return_graph", new=AsyncMock(return_value=None)
            ),
            patch("backend.api.main.get_langfuse", return_value=None),
            patch(
                "backend.api.main.pricing.configured_models_missing_price",
                return_value=["gpt-9-ultra"],
            ),
            patch("backend.api.main.logger") as mock_logger,
        ):
            async with lifespan(app):
                pass

        mock_logger.warning.assert_called_once()
        assert "gpt-9-ultra" in mock_logger.warning.call_args[0][1]

    @pytest.mark.asyncio
    async def test_con_langfuse_configurado_ademas_manda_el_evento(self):
        """Con Langfuse configurado, el aviso también queda visible ahí --
        canal extra, no sustituye al log."""
        mock_lf = MagicMock()
        with (
            patch(
                "backend.api.main.get_return_graph", new=AsyncMock(return_value=None)
            ),
            patch("backend.api.main.get_langfuse", return_value=mock_lf),
            patch(
                "backend.api.main.pricing.configured_models_missing_price",
                return_value=["gpt-9-ultra"],
            ),
            patch("backend.api.main.logger"),
        ):
            async with lifespan(app):
                pass

        mock_lf.create_event.assert_any_call(
            name="pricing_models_missing_price",
            level="WARNING",
            metadata={"models": ["gpt-9-ultra"]},
        )

    @pytest.mark.asyncio
    async def test_un_fallo_al_mandar_el_evento_a_langfuse_no_rompe_el_arranque(self):
        mock_lf = MagicMock()

        def _fail_solo_para_el_evento_de_pricing(*, name, **kwargs):
            if name == "pricing_models_missing_price":
                raise Exception("Langfuse caído")

        mock_lf.create_event.side_effect = _fail_solo_para_el_evento_de_pricing
        with (
            patch(
                "backend.api.main.get_return_graph", new=AsyncMock(return_value=None)
            ),
            patch("backend.api.main.get_langfuse", return_value=mock_lf),
            patch(
                "backend.api.main.pricing.configured_models_missing_price",
                return_value=["gpt-9-ultra"],
            ),
            patch("backend.api.main.logger") as mock_logger,
        ):
            # No debe lanzar ninguna excepción.
            async with lifespan(app):
                pass

        # Un warning por el precio que falta + otro por el fallo de Langfuse.
        assert mock_logger.warning.call_count == 2
