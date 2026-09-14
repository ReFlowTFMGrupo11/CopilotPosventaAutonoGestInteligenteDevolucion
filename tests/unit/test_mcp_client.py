"""Tests unitarios de backend/agents/infra/mcp_client.py.

Mockea MultiServerMCPClient (nunca conecta a un server MCP real) y las
"tools" que devuelve como objetos con .name/.ainvoke. Cubre la parte que
tenía cero tests: el parseo de las distintas formas en que puede llegar
una respuesta MCP (string JSON, string plano, content-blocks, con o sin
prefijo de error) y la cache de tools por server.

_clients/_tools_cache son estado a nivel de módulo (no por instancia) --
un fixture autouse los limpia antes/después de cada test para que el
orden de ejecución no contamine resultados entre tests.

call_tool() registra cada invocación en tool_call_service.log_tool_call()
(ver _log_tool_call) -- sin mockearlo, un entorno con credenciales reales
de Supabase en .env haría una escritura de verdad en cada test (probado:
pasa en silencio por el try/except de _log_tool_call, pero es una llamada
de red real en un test "unitario"). Un fixture autouse lo mockea para
TODOS los tests de este fichero, salvo los de TestCallToolInstrumentacion
que lo mockean explícitamente para comprobar cómo se llama.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from backend.agents.infra import mcp_client


@pytest_asyncio.fixture(autouse=True)
async def _reset_mcp_state():
    await mcp_client.close_mcp_client()
    yield
    await mcp_client.close_mcp_client()


@pytest.fixture(autouse=True)
def _mock_tool_call_logging():
    """Evita escrituras reales a mcp_tool_calls en tests que no comprueban
    la instrumentación en sí (ver docstring del módulo)."""
    with patch(
        "backend.agents.infra.mcp_client.tool_call_service.log_tool_call",
        new=AsyncMock(),
    ):
        yield


def _make_tool(name: str, result):
    """Crea un mock de tool MCP con .name y .ainvoke(...) configurables."""
    tool = MagicMock()
    tool.name = name
    tool.ainvoke = AsyncMock(return_value=result)
    return tool


def _patch_tools(tools_by_server: dict[str, list]):
    """Parchea _get_tools() para devolver una lista de tools fija por server,
    sin tocar MultiServerMCPClient ni hacer ninguna conexión real."""

    async def fake_get_tools(server_name):
        return tools_by_server.get(server_name, [])

    return patch("backend.agents.infra.mcp_client._get_tools", new=fake_get_tools)


class TestCallToolParseoDeResultados:
    @pytest.mark.asyncio
    async def test_tool_no_mapeada_lanza_value_error(self):
        with pytest.raises(ValueError, match="no está mapeada"):
            await mcp_client.call_tool("tool_inexistente", {})

    @pytest.mark.asyncio
    async def test_resultado_string_json_se_parsea_a_dict(self):
        tool = _make_tool("get_order_details", '{"order_number": "ORD-001"}')
        with _patch_tools({"supabase": [tool]}):
            result = await mcp_client.call_tool("get_order_details", {})
        assert result == {"order_number": "ORD-001"}

    @pytest.mark.asyncio
    async def test_resultado_string_no_json_se_devuelve_tal_cual(self):
        tool = _make_tool("get_order_details", "texto plano, no JSON")
        with _patch_tools({"supabase": [tool]}):
            result = await mcp_client.call_tool("get_order_details", {})
        assert result == "texto plano, no JSON"

    @pytest.mark.asyncio
    async def test_resultado_string_con_prefijo_de_error_lanza_runtime_error(self):
        tool = _make_tool(
            "get_order_details", "Error executing tool: pedido no encontrado"
        )
        with _patch_tools({"supabase": [tool]}):
            with pytest.raises(RuntimeError, match="pedido no encontrado"):
                await mcp_client.call_tool("get_order_details", {})

    @pytest.mark.asyncio
    async def test_resultado_content_blocks_se_parsea_a_dict(self):
        tool = _make_tool(
            "search_return_policy",
            [{"type": "text", "text": '{"category": "alimentacion"}'}],
        )
        with _patch_tools({"supabase": [tool]}):
            result = await mcp_client.call_tool("search_return_policy", {})
        assert result == {"category": "alimentacion"}

    @pytest.mark.asyncio
    async def test_content_blocks_con_texto_no_json_devuelve_la_lista_cruda(self):
        raw = [{"type": "text", "text": "no es json"}]
        tool = _make_tool("search_return_policy", raw)
        with _patch_tools({"supabase": [tool]}):
            result = await mcp_client.call_tool("search_return_policy", {})
        assert result == raw

    @pytest.mark.asyncio
    async def test_content_blocks_con_prefijo_de_error_lanza_runtime_error(self):
        tool = _make_tool(
            "search_return_policy",
            [{"type": "text", "text": "Error executing tool: fallo interno"}],
        )
        with _patch_tools({"supabase": [tool]}):
            with pytest.raises(RuntimeError, match="fallo interno"):
                await mcp_client.call_tool("search_return_policy", {})

    @pytest.mark.asyncio
    async def test_resultado_dict_directo_se_devuelve_tal_cual(self):
        tool = _make_tool("get_order_details", {"ya": "es un dict"})
        with _patch_tools({"supabase": [tool]}):
            result = await mcp_client.call_tool("get_order_details", {})
        assert result == {"ya": "es un dict"}

    @pytest.mark.asyncio
    async def test_lista_vacia_se_devuelve_tal_cual(self):
        tool = _make_tool("get_order_details", [])
        with _patch_tools({"supabase": [tool]}):
            result = await mcp_client.call_tool("get_order_details", {})
        assert result == []


class TestCallToolBusquedaDeTool:
    @pytest.mark.asyncio
    async def test_pasa_los_args_correctos_a_la_tool(self):
        tool = _make_tool("get_order_details", "{}")
        with _patch_tools({"supabase": [tool]}):
            await mcp_client.call_tool("get_order_details", {"order_number": "ORD-001"})
        tool.ainvoke.assert_awaited_once_with({"order_number": "ORD-001"})

    @pytest.mark.asyncio
    async def test_tool_no_encontrada_refresca_cache_una_vez_y_luego_falla(self):
        """Simula un server MCP que se reinició con otro set de tools: la
        primera búsqueda en cache no la encuentra, se refresca una vez, y
        si tampoco aparece ahí, se rinde con ValueError (no en bucle)."""
        call_count = {"n": 0}

        async def fake_get_tools(server_name):
            call_count["n"] += 1
            return []  # nunca está la tool, en ninguna de las dos consultas

        with (
            patch("backend.agents.infra.mcp_client._get_tools", new=fake_get_tools),
            patch(
                "backend.agents.infra.mcp_client._tools_cache",
                {"supabase": [_make_tool("otra_tool", "{}")]},
            ),
        ):
            with pytest.raises(ValueError, match="no encontrada en server"):
                await mcp_client.call_tool("get_order_details", {})

        assert call_count["n"] == 2  # una consulta inicial + un refresh


class TestGetTools:
    @pytest.mark.asyncio
    async def test_cachea_las_tools_tras_la_primera_consulta(self):
        mock_client = MagicMock()
        mock_client.get_tools = AsyncMock(return_value=["tool-a", "tool-b"])

        with patch(
            "backend.agents.infra.mcp_client._get_server_client",
            new=AsyncMock(return_value=mock_client),
        ):
            first = await mcp_client._get_tools("supabase")
            second = await mcp_client._get_tools("supabase")

        assert first == ["tool-a", "tool-b"]
        assert second == ["tool-a", "tool-b"]
        # Solo UNA llamada real, la segunda sale de cache.
        mock_client.get_tools.assert_awaited_once()


class TestGetServerClient:
    @pytest.mark.asyncio
    async def test_server_desconocido_lanza_value_error(self):
        with pytest.raises(ValueError, match="Server MCP desconocido"):
            await mcp_client._get_server_client("servidor-inventado")

    @pytest.mark.asyncio
    async def test_reutiliza_el_mismo_cliente_en_llamadas_sucesivas(self):
        with patch("backend.agents.infra.mcp_client.MultiServerMCPClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            first = await mcp_client._get_server_client("supabase")
            second = await mcp_client._get_server_client("supabase")

        assert first is second
        mock_cls.assert_called_once()  # solo se instancia una vez


class TestCloseMcpClient:
    @pytest.mark.asyncio
    async def test_limpia_clientes_y_cache_de_tools(self):
        with patch("backend.agents.infra.mcp_client.MultiServerMCPClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            await mcp_client._get_server_client("supabase")

        assert "supabase" in mcp_client._clients
        await mcp_client.close_mcp_client()
        assert mcp_client._clients == {}
        assert mcp_client._tools_cache == {}


class TestSearchReturnPolicyWrapper:
    @pytest.mark.asyncio
    async def test_registra_score_rag_con_los_semantic_results(self):
        fake_result = {
            "semantic_results": [{"chunk_text": "...", "similarity": 0.8}],
            "policy_info": {"max_return_days": 30},
        }
        with (
            patch(
                "backend.agents.infra.mcp_client.call_tool",
                new=AsyncMock(return_value=fake_result),
            ),
            patch("backend.agents.infra.mcp_client.score_rag_similarity") as mock_score,
        ):
            result = await mcp_client.search_return_policy(
                query="política de devolución",
                category="electronica_informatica",
                thread_id="thread-1",
            )

        assert result == fake_result
        mock_score.assert_called_once_with(
            "thread-1",
            "política de devolución",
            "electronica_informatica",
            [{"chunk_text": "...", "similarity": 0.8}],
        )

    @pytest.mark.asyncio
    async def test_sin_semantic_results_registra_score_con_lista_vacia(self):
        fake_result = {"policy_info": {}}  # sin la clave semantic_results
        with (
            patch(
                "backend.agents.infra.mcp_client.call_tool",
                new=AsyncMock(return_value=fake_result),
            ),
            patch("backend.agents.infra.mcp_client.score_rag_similarity") as mock_score,
        ):
            await mcp_client.search_return_policy(query="q", category="c")

        mock_score.assert_called_once_with(None, "q", "c", [])


class TestCallToolInstrumentacion:
    """call_tool() registra éxito/fallo y latencia de cada invocación real
    en mcp_tool_calls (tabla propia, señal garantizada) + un score de
    LangFuse (canal extra) -- ver _log_tool_call. Antes, un fallo de tool
    solo marcaba el TURNO completo como error, sin registro de qué tool
    falló (docs/defensaTFM/defenderLangfuse.md)."""

    @pytest.mark.asyncio
    async def test_llamada_exitosa_registra_success_true_con_latencia(self):
        tool = _make_tool("get_order_details", '{"order_number": "ORD-001"}')
        with (
            _patch_tools({"supabase": [tool]}),
            patch(
                "backend.agents.infra.mcp_client.tool_call_service.log_tool_call",
                new=AsyncMock(),
            ) as mock_log,
            patch("backend.agents.infra.mcp_client.score_tool_call") as mock_score,
        ):
            await mcp_client.call_tool("get_order_details", {"order_number": "ORD-001"})

        mock_log.assert_awaited_once()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["tool_name"] == "get_order_details"
        assert kwargs["success"] is True
        assert kwargs["error_message"] is None
        assert kwargs["thread_id"] is None  # no venía en los args
        assert isinstance(kwargs["latency_ms"], int)
        mock_score.assert_called_once_with(
            None, "get_order_details", success=True, error=None
        )

    @pytest.mark.asyncio
    async def test_extrae_thread_id_de_los_args_de_forma_oportunista(self):
        tool = _make_tool("search_return_policy", '{"semantic_results": []}')
        with (
            _patch_tools({"supabase": [tool]}),
            patch(
                "backend.agents.infra.mcp_client.tool_call_service.log_tool_call",
                new=AsyncMock(),
            ) as mock_log,
            patch("backend.agents.infra.mcp_client.score_tool_call"),
        ):
            await mcp_client.call_tool(
                "search_return_policy",
                {"query": "q", "category": "c", "thread_id": "thread-1"},
            )

        assert mock_log.call_args.kwargs["thread_id"] == "thread-1"

    @pytest.mark.asyncio
    async def test_error_de_la_tool_registra_success_false_y_relanza(self):
        """Un fallo MCP (prefijo 'Error executing tool') debe registrarse
        como success=False Y seguir propagando el RuntimeError -- la
        instrumentación no puede enmascarar el error real."""
        tool = _make_tool(
            "create_return_record", "Error executing tool: constraint violada"
        )
        with (
            _patch_tools({"supabase": [tool]}),
            patch(
                "backend.agents.infra.mcp_client.tool_call_service.log_tool_call",
                new=AsyncMock(),
            ) as mock_log,
            patch("backend.agents.infra.mcp_client.score_tool_call") as mock_score,
        ):
            with pytest.raises(RuntimeError, match="constraint violada"):
                await mcp_client.call_tool(
                    "create_return_record", {"thread_id": "thread-2"}
                )

        kwargs = mock_log.call_args.kwargs
        assert kwargs["tool_name"] == "create_return_record"
        assert kwargs["success"] is False
        assert "constraint violada" in kwargs["error_message"]
        assert kwargs["thread_id"] == "thread-2"
        mock_score.assert_called_once()
        assert mock_score.call_args.kwargs["success"] is False

    @pytest.mark.asyncio
    async def test_excepcion_inesperada_de_ainvoke_tambien_se_registra_y_relanza(self):
        """No solo el prefijo de error de MCP -- cualquier excepción de
        tool.ainvoke() (timeout, conexión caída...) debe quedar registrada
        igual, no solo el caso "bonito" del prefijo de texto."""
        tool = MagicMock()
        tool.name = "generate_shipping_label"
        tool.ainvoke = AsyncMock(side_effect=TimeoutError("MCP server no responde"))
        with (
            _patch_tools({"logistics": [tool]}),
            patch(
                "backend.agents.infra.mcp_client.tool_call_service.log_tool_call",
                new=AsyncMock(),
            ) as mock_log,
            patch("backend.agents.infra.mcp_client.score_tool_call"),
        ):
            with pytest.raises(TimeoutError):
                await mcp_client.call_tool("generate_shipping_label", {})

        kwargs = mock_log.call_args.kwargs
        assert kwargs["success"] is False
        assert "no responde" in kwargs["error_message"]

    @pytest.mark.asyncio
    async def test_un_fallo_al_registrar_no_rompe_ni_enmascara_el_resultado(self):
        """Contrato explícito de _log_tool_call: un fallo al escribir en
        mcp_tool_calls (BD caída, etc.) nunca debe romper el turno del
        cliente ni cambiar el resultado real de la tool."""
        tool = _make_tool("get_order_details", '{"order_number": "ORD-001"}')
        with (
            _patch_tools({"supabase": [tool]}),
            patch(
                "backend.agents.infra.mcp_client.tool_call_service.log_tool_call",
                new=AsyncMock(side_effect=Exception("BD caída")),
            ),
            patch("backend.agents.infra.mcp_client.score_tool_call"),
        ):
            # No debe lanzar ninguna excepción, y debe devolver el resultado real.
            result = await mcp_client.call_tool("get_order_details", {})

        assert result == {"order_number": "ORD-001"}

    @pytest.mark.asyncio
    async def test_tool_no_encontrada_no_registra_nada(self):
        """Un error de lookup (tool no mapeada/no encontrada) es un
        problema de configuración/wiring, no "la tool falló al ejecutarse"
        -- no debe generar una fila en mcp_tool_calls."""
        with patch(
            "backend.agents.infra.mcp_client.tool_call_service.log_tool_call",
            new=AsyncMock(),
        ) as mock_log:
            with pytest.raises(ValueError):
                await mcp_client.call_tool("tool_inexistente", {})

        mock_log.assert_not_awaited()


class TestGetPendingReturnRequestIdWrapper:
    """La tool MCP devuelve {"return_request_id": ...} (no un string plano
    -- ver el porqué en el docstring de la tool en mcp_supabase.py); este
    wrapper debe desenvolverlo para mantener la misma interfaz que
    returns_service.get_pending_return_request_id (un string)."""

    @pytest.mark.asyncio
    async def test_desenvuelve_el_id_del_dict(self):
        with patch(
            "backend.agents.infra.mcp_client.call_tool",
            new=AsyncMock(return_value={"return_request_id": "ret-123"}),
        ) as mock_call:
            result = await mcp_client.get_pending_return_request_id("ord-1")

        assert result == "ret-123"
        mock_call.assert_awaited_once_with(
            "get_pending_return_request_id", {"order_id": "ord-1"}
        )

    @pytest.mark.asyncio
    async def test_sin_devolucion_pendiente_devuelve_cadena_vacia(self):
        with patch(
            "backend.agents.infra.mcp_client.call_tool",
            new=AsyncMock(return_value={"return_request_id": ""}),
        ):
            result = await mcp_client.get_pending_return_request_id("ord-1")

        assert result == ""
