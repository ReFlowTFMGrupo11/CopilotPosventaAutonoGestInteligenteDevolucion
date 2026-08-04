"""
Tests unitarios del Agente 3 (Resolucion y Logistica).

No requieren servidores MCP ni API key reales: el cliente MCP y el agente
se sustituyen por dobles de prueba. Ejecutar con:
    pytest agente3ConMCP/tests
"""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from langchain_openai import ChatOpenAI

from agente3ConMCP.agente_resolucion import (
    HITL_THRESHOLD_EUR,
    RESOLUTION_TOOL_NAMES,
    ResolutionOutput,
    ResolutionRequest,
    _resolve_model,
    build_resolution_agent,
    get_resolution_tools,
    run_agent_resolucion,
)


class _FakeTool:
    """Doble minimo de una BaseTool de langchain_mcp_adapters."""

    def __init__(self, name: str):
        self.name = name


class _FakeAgent:
    """Doble de un agente langgraph compilado: registra la llamada y devuelve una salida fija."""

    def __init__(self, structured_response: ResolutionOutput):
        self.structured_response = structured_response
        self.last_input = None

    async def ainvoke(self, payload: dict) -> dict:
        self.last_input = payload
        return {"structured_response": self.structured_response}


def _make_request(**overrides) -> ResolutionRequest:
    defaults = dict(
        order_id="e1f2a3b4-c5d6-7890-efab-901234567890",
        customer_id="c3d4e5f6-a7b8-9012-cdef-123456789012",
        customer_email="laura.fernandez@email.com",
        reason="No era lo que esperaba",
        reason_category="changed_mind",
        refund_amount=34.99,
        products=[{"order_item_id": "d6e7f8a9-b0c1-2345-defa-456789012345", "quantity": 1}],
    )
    defaults.update(overrides)
    return ResolutionRequest(**defaults)


# ---------------------------------------------------------------------------
# get_resolution_tools: debe filtrar y unir las tools de los dos servidores
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_resolution_tools_filters_tools_from_both_servers():
    all_tools = [
        _FakeTool("get_order_details"),  # supabase, de otro agente
        _FakeTool("create_return_record"),  # supabase, Agente 3
        _FakeTool("update_return_status"),  # supabase, Admin/HITL
        _FakeTool("generate_shipping_label"),  # logistics, Agente 3
        _FakeTool("send_customer_notification"),  # logistics, Agente 3
    ]
    fake_client = AsyncMock()
    fake_client.get_tools.return_value = all_tools

    with patch(
        "agente3ConMCP.agente_resolucion._get_mcp_client", return_value=fake_client
    ) as mock_get_client:
        tools = await get_resolution_tools(
            mcp_supabase_url="http://localhost:8001/mcp",
            mcp_logistics_url="http://localhost:8002/mcp",
        )

    mock_get_client.assert_called_once_with(
        "http://localhost:8001/mcp", "http://localhost:8002/mcp"
    )
    # get_tools() se llama sin server_name: trae tools de ambos servidores.
    fake_client.get_tools.assert_awaited_once_with()
    assert {t.name for t in tools} == RESOLUTION_TOOL_NAMES


@pytest.mark.asyncio
async def test_get_resolution_tools_returns_empty_when_tools_missing():
    fake_client = AsyncMock()
    fake_client.get_tools.return_value = [_FakeTool("get_order_details")]

    with patch("agente3ConMCP.agente_resolucion._get_mcp_client", return_value=fake_client):
        tools = await get_resolution_tools()

    assert tools == []


# ---------------------------------------------------------------------------
# build_resolution_agent: wiring de create_agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_resolution_agent_wires_create_agent_with_injected_tools():
    injected_tools = [_FakeTool("create_return_record")]

    with patch("agente3ConMCP.agente_resolucion.create_agent") as mock_create_agent, patch(
        "agente3ConMCP.agente_resolucion.get_resolution_tools"
    ) as mock_get_tools, patch(
        "agente3ConMCP.agente_resolucion._resolve_model"
    ) as mock_resolve_model:
        mock_create_agent.return_value = "compiled-agent"
        mock_resolve_model.return_value = "resolved-model"

        result = await build_resolution_agent(model="openai:gpt-4o-mini", tools=injected_tools)

    mock_get_tools.assert_not_called()
    mock_resolve_model.assert_called_once_with("openai:gpt-4o-mini")
    mock_create_agent.assert_called_once()
    _, kwargs = mock_create_agent.call_args
    # build_resolution_agent pasa a create_agent el modelo YA resuelto por
    # _resolve_model, no el string original (ver test_resolve_model_* mas
    # abajo para el porque de esa conversion).
    assert kwargs["model"] == "resolved-model"
    assert kwargs["tools"] == injected_tools
    assert kwargs["response_format"] is ResolutionOutput
    assert "create_return_record" in kwargs["system_prompt"]
    assert result == "compiled-agent"


@pytest.mark.asyncio
async def test_build_resolution_agent_fetches_tools_from_mcp_when_not_injected():
    with patch("agente3ConMCP.agente_resolucion.create_agent") as mock_create_agent, patch(
        "agente3ConMCP.agente_resolucion.get_resolution_tools", new_callable=AsyncMock
    ) as mock_get_tools, patch("agente3ConMCP.agente_resolucion._resolve_model"):
        mock_get_tools.return_value = [_FakeTool("create_return_record")]
        mock_create_agent.return_value = "compiled-agent"

        await build_resolution_agent(
            mcp_supabase_url="http://localhost:8001/mcp",
            mcp_logistics_url="http://localhost:8002/mcp",
        )

    mock_get_tools.assert_awaited_once_with(
        "http://localhost:8001/mcp", "http://localhost:8002/mcp"
    )


# ---------------------------------------------------------------------------
# _resolve_model: convierte "openai:<modelo>" en un ChatOpenAI normal.
#
# Ya no fuerza use_responses_api=True (ver docstring de _resolve_model en
# agente_resolucion.py): desde que create_return_record y
# generate_shipping_label tipan `items` (ReturnItem / ShippingLabelItem en
# backend/mcp/), el modo "strict" de OpenAI ya no rechaza su schema cuando
# el agente combina tools + response_format.
# ---------------------------------------------------------------------------


def test_resolve_model_converts_openai_prefixed_string(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy-key")

    resolved = _resolve_model("openai:gpt-4o-mini")

    assert isinstance(resolved, ChatOpenAI)
    assert resolved.model_name == "gpt-4o-mini"
    assert not resolved.use_responses_api


def test_resolve_model_leaves_non_openai_strings_untouched():
    resolved = _resolve_model("anthropic:claude-3-5-sonnet")

    assert resolved == "anthropic:claude-3-5-sonnet"


def test_resolve_model_leaves_prebuilt_chat_models_untouched(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy-key")
    already_built = ChatOpenAI(model="gpt-4o-mini")

    resolved = _resolve_model(already_built)

    assert resolved is already_built


# ---------------------------------------------------------------------------
# run_agent_resolucion: corte HITL determinista
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_resolucion_requires_approval_above_threshold_without_touching_agent():
    request = _make_request(refund_amount=HITL_THRESHOLD_EUR + 0.01)

    with patch(
        "agente3ConMCP.agente_resolucion.build_resolution_agent", new_callable=AsyncMock
    ) as mock_build_agent:
        output = await run_agent_resolucion(request)

    mock_build_agent.assert_not_called()
    assert output.requires_human_approval is True
    assert output.refund_amount == request.refund_amount
    assert output.return_id is None
    assert output.tracking_number is None
    assert output.label_path is None
    assert "administrador" in output.response_to_customer


@pytest.mark.asyncio
async def test_run_agent_resolucion_executes_agent_at_threshold_boundary():
    # refund_amount == HITL_THRESHOLD_EUR (no ">") debe ejecutarse, no derivarse.
    request = _make_request(refund_amount=HITL_THRESHOLD_EUR)
    expected_output = ResolutionOutput(
        return_id="return-1",
        tracking_number="RF-ABC123",
        label_path="/tmp/label.pdf",
        requires_human_approval=True,  # deliberadamente "mal": debe ser sobreescrito
        refund_amount=999.0,  # deliberadamente "mal": debe ser sobreescrito
        response_to_customer="Tu devolucion ha sido aprobada.",
    )
    fake_agent = _FakeAgent(expected_output)

    output = await run_agent_resolucion(request, agent=fake_agent)

    assert output is expected_output
    assert output.return_id == "return-1"
    assert output.tracking_number == "RF-ABC123"
    # run_agent_resolucion no confia en lo que devuelva el LLM para estos dos campos.
    assert output.refund_amount == request.refund_amount
    assert output.requires_human_approval is False


@pytest.mark.asyncio
async def test_run_agent_resolucion_case_brief_includes_request_fields():
    request = _make_request()
    expected_output = ResolutionOutput(response_to_customer="ok", refund_amount=request.refund_amount)
    fake_agent = _FakeAgent(expected_output)

    await run_agent_resolucion(request, agent=fake_agent)

    sent_content = fake_agent.last_input["messages"][0]["content"]
    assert request.order_id in sent_content
    assert request.customer_email in sent_content
    assert str(request.refund_amount) in sent_content


@pytest.mark.asyncio
async def test_run_agent_resolucion_builds_agent_when_none_injected():
    request = _make_request()
    expected_output = ResolutionOutput(response_to_customer="ok", refund_amount=request.refund_amount)
    fake_agent = _FakeAgent(expected_output)

    with patch(
        "agente3ConMCP.agente_resolucion.build_resolution_agent", new_callable=AsyncMock
    ) as mock_build_agent:
        mock_build_agent.return_value = fake_agent

        result = await run_agent_resolucion(
            request,
            model="openai:gpt-4o-mini",
            mcp_supabase_url="http://localhost:8001/mcp",
            mcp_logistics_url="http://localhost:8002/mcp",
        )

    mock_build_agent.assert_awaited_once_with(
        model="openai:gpt-4o-mini",
        mcp_supabase_url="http://localhost:8001/mcp",
        mcp_logistics_url="http://localhost:8002/mcp",
    )
    assert result.response_to_customer == "ok"


# ---------------------------------------------------------------------------
# Esquemas: ResolutionRequest / ResolutionOutput
# ---------------------------------------------------------------------------


def test_resolution_request_defaults_products_to_empty_list():
    request = ResolutionRequest(
        order_id="order-1",
        customer_id="customer-1",
        customer_email="a@b.com",
        reason="roto",
        reason_category="defective",
        refund_amount=10.0,
    )
    assert request.products == []
    assert request.customer_name == ""
    assert request.notes == ""


def test_resolution_request_requires_core_fields():
    with pytest.raises(ValidationError):
        ResolutionRequest(order_id="order-1")


def test_resolution_output_defaults_when_pending_approval():
    output = ResolutionOutput(refund_amount=150.0, response_to_customer="Derivado a un administrador.")

    assert output.return_id is None
    assert output.tracking_number is None
    assert output.label_path is None
    assert output.requires_human_approval is False


def test_resolution_output_requires_refund_amount_and_response():
    with pytest.raises(ValidationError):
        ResolutionOutput()
