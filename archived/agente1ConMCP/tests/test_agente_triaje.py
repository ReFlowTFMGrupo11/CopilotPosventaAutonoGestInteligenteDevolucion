"""
Tests unitarios del Agente 1 (Triaje y Empatia).

No requieren servidor MCP ni API key reales: el cliente MCP y el modelo se
sustituyen por dobles de prueba. Ejecutar con:
    pytest agente1ConMCP/tests
"""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from agente1ConMCP.agente_triaje import (
    TRIAGE_TOOL_NAMES,
    TriageOutput,
    build_triage_agent,
    get_triage_tools,
    run_agent_triaje,
)


class _FakeTool:
    """Doble minimo de una BaseTool de langchain_mcp_adapters."""

    def __init__(self, name: str):
        self.name = name


class _FakeAgent:
    """Doble de un agente langgraph compilado: registra la llamada y devuelve una salida fija."""

    def __init__(self, structured_response: TriageOutput):
        self.structured_response = structured_response
        self.last_input = None

    async def ainvoke(self, payload: dict) -> dict:
        self.last_input = payload
        return {"structured_response": self.structured_response}


# ---------------------------------------------------------------------------
# get_triage_tools: debe filtrar solo la tool que necesita el Agente 1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_triage_tools_filters_to_get_order_details():
    all_tools = [
        _FakeTool("get_order_details"),
        _FakeTool("get_customer_return_history"),
        _FakeTool("search_return_policy"),
        _FakeTool("create_return_record"),
        _FakeTool("update_return_status"),
    ]
    fake_client = AsyncMock()
    fake_client.get_tools.return_value = all_tools

    with patch(
        "agente1ConMCP.agente_triaje._get_mcp_client", return_value=fake_client
    ) as mock_get_client:
        tools = await get_triage_tools(mcp_url="http://localhost:8001/mcp")

    mock_get_client.assert_called_once_with("http://localhost:8001/mcp")
    fake_client.get_tools.assert_awaited_once_with(server_name="supabase")
    assert [t.name for t in tools] == ["get_order_details"]
    assert {t.name for t in tools} == TRIAGE_TOOL_NAMES


@pytest.mark.asyncio
async def test_get_triage_tools_returns_empty_when_tool_missing():
    fake_client = AsyncMock()
    fake_client.get_tools.return_value = [_FakeTool("create_return_record")]

    with patch("agente1ConMCP.agente_triaje._get_mcp_client", return_value=fake_client):
        tools = await get_triage_tools()

    assert tools == []


# ---------------------------------------------------------------------------
# build_triage_agent: debe construir el agente con el prompt/response_format
# correctos y sin llamar al MCP real cuando se inyectan tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_triage_agent_wires_create_agent_with_injected_tools():
    injected_tools = [_FakeTool("get_order_details")]

    with patch("agente1ConMCP.agente_triaje.create_agent") as mock_create_agent, patch(
        "agente1ConMCP.agente_triaje.get_triage_tools"
    ) as mock_get_tools:
        mock_create_agent.return_value = "compiled-agent"

        result = await build_triage_agent(model="openai:gpt-4o-mini", tools=injected_tools)

    mock_get_tools.assert_not_called()
    mock_create_agent.assert_called_once()
    _, kwargs = mock_create_agent.call_args
    assert kwargs["model"] == "openai:gpt-4o-mini"
    assert kwargs["tools"] == injected_tools
    assert kwargs["response_format"] is TriageOutput
    assert "get_order_details" in kwargs["system_prompt"]
    assert result == "compiled-agent"


@pytest.mark.asyncio
async def test_build_triage_agent_fetches_tools_from_mcp_when_not_injected():
    with patch("agente1ConMCP.agente_triaje.create_agent") as mock_create_agent, patch(
        "agente1ConMCP.agente_triaje.get_triage_tools", new_callable=AsyncMock
    ) as mock_get_tools:
        mock_get_tools.return_value = [_FakeTool("get_order_details")]
        mock_create_agent.return_value = "compiled-agent"

        await build_triage_agent(mcp_url="http://localhost:8001/mcp")

    mock_get_tools.assert_awaited_once_with("http://localhost:8001/mcp")


# ---------------------------------------------------------------------------
# run_agent_triaje: arma los mensajes correctamente y devuelve la salida estructurada
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_triaje_appends_message_to_history_and_returns_structured_response():
    expected_output = TriageOutput(
        order_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        reason="llego roto",
        reason_category="defective",
        ready_for_evaluation=True,
        response_to_customer="Siento el inconveniente, ya verifique tu pedido.",
    )
    fake_agent = _FakeAgent(expected_output)
    history = [{"role": "assistant", "content": "Hola, en que puedo ayudarte?"}]

    result = await run_agent_triaje(
        "Quiero devolver mi pedido, llego roto",
        history=history,
        agent=fake_agent,
    )

    assert result is expected_output
    assert fake_agent.last_input == {
        "messages": [
            {"role": "assistant", "content": "Hola, en que puedo ayudarte?"},
            {"role": "user", "content": "Quiero devolver mi pedido, llego roto"},
        ]
    }


@pytest.mark.asyncio
async def test_run_agent_triaje_without_history_sends_single_user_message():
    expected_output = TriageOutput(response_to_customer="Hola! Cuentame que ocurrio con tu pedido.")
    fake_agent = _FakeAgent(expected_output)

    result = await run_agent_triaje("Hola", agent=fake_agent)

    assert result is expected_output
    assert fake_agent.last_input == {"messages": [{"role": "user", "content": "Hola"}]}


@pytest.mark.asyncio
async def test_run_agent_triaje_builds_agent_when_none_injected():
    expected_output = TriageOutput(response_to_customer="ok")
    fake_agent = _FakeAgent(expected_output)

    with patch(
        "agente1ConMCP.agente_triaje.build_triage_agent", new_callable=AsyncMock
    ) as mock_build_agent:
        mock_build_agent.return_value = fake_agent

        result = await run_agent_triaje(
            "Hola", model="openai:gpt-4o-mini", mcp_url="http://localhost:8001/mcp"
        )

    mock_build_agent.assert_awaited_once_with(
        model="openai:gpt-4o-mini", mcp_url="http://localhost:8001/mcp"
    )
    assert result is expected_output


# ---------------------------------------------------------------------------
# TriageOutput: contrato de datos hacia el Agente Evaluador
# ---------------------------------------------------------------------------


def test_triage_output_defaults_when_order_not_yet_known():
    output = TriageOutput(response_to_customer="Claro, dime el numero de tu pedido.")

    assert output.order_id is None
    assert output.reason is None
    assert output.reason_category is None
    assert output.ready_for_evaluation is False


def test_triage_output_requires_response_to_customer():
    with pytest.raises(ValidationError):
        TriageOutput()
