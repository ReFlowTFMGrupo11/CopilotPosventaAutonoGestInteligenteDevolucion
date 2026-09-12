"""Tests unitarios de backend/agents/usage_tracking.py.

Mockea usage_service.log_llm_usage directamente (ya cubierto en
test_usage_service.py) para aislar la lógica propia de este módulo:
extracción de tokens de usage_metadata, el guard de "sin thread_id no hay
sesión", y que un fallo al registrar el uso JAMÁS se propaga (contrato
explícito del propio docstring del módulo).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from backend.agents.usage_tracking import (
    _log_usage,
    _usage_from_message,
    invoke_structured_tracked,
    invoke_tracked,
)


class TestUsageFromMessage:
    def test_extrae_tokens_de_un_mensaje_con_usage_metadata(self):
        message = AIMessage(
            content="hola",
            usage_metadata={
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            },
        )
        assert _usage_from_message(message) == (100, 50, 150)

    def test_mensaje_sin_usage_metadata_devuelve_ceros(self):
        message = AIMessage(content="hola")
        assert _usage_from_message(message) == (0, 0, 0)

    def test_mensaje_none_devuelve_ceros(self):
        assert _usage_from_message(None) == (0, 0, 0)

    def test_usage_metadata_con_claves_ausentes_no_rompe(self):
        """AIMessage valida usage_metadata estrictamente (no admite None en
        sus campos), así que se usa un MagicMock para simular un dict de
        usage_metadata incompleto -- el caso real que `.get(...) or 0`
        protege (claves ausentes, no necesariamente en None)."""
        message = MagicMock()
        message.usage_metadata = {}  # ninguna clave presente
        assert _usage_from_message(message) == (0, 0, 0)


class TestLogUsage:
    @pytest.mark.asyncio
    async def test_sin_thread_id_no_llama_al_servicio(self):
        mock_log = AsyncMock()
        with patch(
            "backend.agents.usage_tracking.usage_service.log_llm_usage", mock_log
        ):
            await _log_usage(
                node="triage",
                model="gpt-5-mini",
                thread_id=None,
                customer_id=None,
                order_id=None,
                latency_ms=100,
                tokens=(10, 5, 15),
            )
        mock_log.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_con_thread_id_llama_al_servicio_con_los_datos_correctos(self):
        mock_log = AsyncMock()
        with patch(
            "backend.agents.usage_tracking.usage_service.log_llm_usage", mock_log
        ):
            await _log_usage(
                node="evaluator",
                model="gpt-5-mini",
                thread_id="thread-1",
                customer_id="cust-1",
                order_id="ord-1",
                latency_ms=850,
                tokens=(200, 50, 250),
            )
        mock_log.assert_awaited_once_with(
            thread_id="thread-1",
            customer_id="cust-1",
            order_id="ord-1",
            node="evaluator",
            model="gpt-5-mini",
            input_tokens=200,
            output_tokens=50,
            total_tokens=250,
            latency_ms=850,
        )

    @pytest.mark.asyncio
    async def test_un_fallo_al_registrar_no_se_propaga(self):
        """Contrato explícito del docstring del módulo: un fallo al registrar
        uso JAMÁS debe romper el turno del cliente."""
        mock_log = AsyncMock(side_effect=Exception("BD caída"))
        with patch(
            "backend.agents.usage_tracking.usage_service.log_llm_usage", mock_log
        ):
            # No debe lanzar ninguna excepción.
            await _log_usage(
                node="triage",
                model="gpt-5-mini",
                thread_id="thread-1",
                customer_id=None,
                order_id=None,
                latency_ms=100,
                tokens=(10, 5, 15),
            )


class TestInvokeTracked:
    @pytest.mark.asyncio
    async def test_devuelve_el_resultado_del_llm_y_registra_uso(self):
        response = AIMessage(
            content="respuesta",
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )
        llm = MagicMock()
        llm.model_name = "gpt-5-mini"
        llm.ainvoke = AsyncMock(return_value=response)

        mock_log = AsyncMock()
        with patch(
            "backend.agents.usage_tracking.usage_service.log_llm_usage", mock_log
        ):
            result = await invoke_tracked(
                llm, ["mensaje"], node="triage", thread_id="thread-1"
            )

        assert result is response
        mock_log.assert_awaited_once()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["node"] == "triage"
        assert kwargs["model"] == "gpt-5-mini"
        assert kwargs["input_tokens"] == 10
        assert kwargs["total_tokens"] == 15


class TestInvokeStructuredTracked:
    def _mock_llm(self, raw_result):
        structured = MagicMock()
        structured.ainvoke = AsyncMock(return_value=raw_result)
        llm = MagicMock()
        llm.model_name = "gpt-5-mini"
        llm.with_structured_output.return_value = structured
        return llm

    @pytest.mark.asyncio
    async def test_devuelve_el_objeto_parseado_si_no_hay_error(self):
        parsed = {"campo": "valor"}
        raw_result = {
            "raw": AIMessage(content=""),
            "parsed": parsed,
            "parsing_error": None,
        }
        llm = self._mock_llm(raw_result)

        with patch(
            "backend.agents.usage_tracking.usage_service.log_llm_usage",
            new=AsyncMock(),
        ):
            result = await invoke_structured_tracked(
                llm, dict, ["mensaje"], node="evaluator", thread_id="thread-1"
            )

        assert result is parsed

    @pytest.mark.asyncio
    async def test_devuelve_none_si_hay_error_de_parseo(self):
        raw_result = {
            "raw": AIMessage(content=""),
            "parsed": None,
            "parsing_error": "no se pudo parsear",
        }
        llm = self._mock_llm(raw_result)

        with patch(
            "backend.agents.usage_tracking.usage_service.log_llm_usage",
            new=AsyncMock(),
        ):
            result = await invoke_structured_tracked(
                llm, dict, ["mensaje"], node="evaluator", thread_id="thread-1"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_registra_uso_a_partir_del_mensaje_raw_no_del_parseado(self):
        raw_message = AIMessage(
            content="",
            usage_metadata={
                "input_tokens": 300,
                "output_tokens": 100,
                "total_tokens": 400,
            },
        )
        raw_result = {
            "raw": raw_message,
            "parsed": {"ok": True},
            "parsing_error": None,
        }
        llm = self._mock_llm(raw_result)

        mock_log = AsyncMock()
        with patch(
            "backend.agents.usage_tracking.usage_service.log_llm_usage", mock_log
        ):
            await invoke_structured_tracked(
                llm, dict, ["mensaje"], node="evaluator", thread_id="thread-1"
            )

        kwargs = mock_log.call_args.kwargs
        assert kwargs["input_tokens"] == 300
        assert kwargs["total_tokens"] == 400
