"""
Tests unitarios del Agente 2 (Evaluador de Politicas).

No requieren servidor MCP ni API key reales: el cliente MCP y el agente se
sustituyen por dobles de prueba. Ejecutar con:
    pytest agente2ConMCP/tests
"""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from agente2ConMCP.agente_evaluacion import (
    EVALUATION_TOOL_NAMES,
    EvaluationOutput,
    EvaluationRequest,
    _classify_return,
    _sum_refund_amount,
    build_evaluation_agent,
    get_evaluation_tools,
    run_agent_evaluacion,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class _FakeTool:
    """Doble minimo de una BaseTool de langchain_mcp_adapters."""

    def __init__(self, name: str):
        self.name = name


class _FakeAgent:
    """Doble de un agente langgraph compilado: registra la llamada y devuelve una salida fija."""

    def __init__(self, structured_response: EvaluationOutput):
        self.structured_response = structured_response
        self.last_input = None

    async def ainvoke(self, payload: dict) -> dict:
        self.last_input = payload
        return {"structured_response": self.structured_response}


def _raw_llm_output(**overrides) -> EvaluationOutput:
    """Salida "cruda" tal y como la dejaria el LLM: solo hechos, decision aun
    en sus valores por defecto (los recalcula _apply_deterministic_decision)."""
    defaults = dict(
        order_id="e1f2a3b4-c5d6-7890-efab-901234567890",
        customer_id="c3d4e5f6-a7b8-9012-cdef-123456789012",
        customer_email="laura.fernandez@email.com",
        customer_name="Laura Fernandez Soto",
        customer_address="Calle Sierpes 15, Sevilla",
        category="books",
        delivered_at=_iso_days_ago(5),
        products=[
            {
                "order_item_id": "d6e7f8a9-b0c1-2345-defa-456789012345",
                "name": "Clean Code (Edicion Espanol)",
                "category": "books",
                "quantity": 1,
                "unit_price": 34.99,
                "total_price": 34.99,
            }
        ],
        policy_max_return_days=14,
        customer_approved_returns=0,
    )
    defaults.update(overrides)
    return EvaluationOutput(**defaults)


# ---------------------------------------------------------------------------
# get_evaluation_tools: debe filtrar solo las 3 tools que necesita el Agente 2
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_evaluation_tools_filters_to_evaluation_tools():
    all_tools = [
        _FakeTool("get_order_details"),
        _FakeTool("search_return_policy"),
        _FakeTool("get_customer_return_history"),
        _FakeTool("create_return_record"),
        _FakeTool("update_return_status"),
    ]
    fake_client = AsyncMock()
    fake_client.get_tools.return_value = all_tools

    with patch(
        "agente2ConMCP.agente_evaluacion._get_mcp_client", return_value=fake_client
    ) as mock_get_client:
        tools = await get_evaluation_tools(mcp_supabase_url="http://localhost:8001/mcp")

    mock_get_client.assert_called_once_with("http://localhost:8001/mcp")
    fake_client.get_tools.assert_awaited_once_with(server_name="supabase")
    assert {t.name for t in tools} == EVALUATION_TOOL_NAMES


@pytest.mark.asyncio
async def test_get_evaluation_tools_returns_empty_when_tools_missing():
    fake_client = AsyncMock()
    fake_client.get_tools.return_value = [_FakeTool("create_return_record")]

    with patch("agente2ConMCP.agente_evaluacion._get_mcp_client", return_value=fake_client):
        tools = await get_evaluation_tools()

    assert tools == []


# ---------------------------------------------------------------------------
# build_evaluation_agent: debe construir el agente con el prompt/response_format
# correctos y sin llamar al MCP real cuando se inyectan tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_evaluation_agent_wires_create_agent_with_injected_tools():
    injected_tools = [_FakeTool("get_order_details")]

    with patch("agente2ConMCP.agente_evaluacion.create_agent") as mock_create_agent, patch(
        "agente2ConMCP.agente_evaluacion.get_evaluation_tools"
    ) as mock_get_tools:
        mock_create_agent.return_value = "compiled-agent"

        result = await build_evaluation_agent(model="openai:gpt-4o-mini", tools=injected_tools)

    mock_get_tools.assert_not_called()
    mock_create_agent.assert_called_once()
    _, kwargs = mock_create_agent.call_args
    assert kwargs["tools"] == injected_tools
    assert kwargs["response_format"] is EvaluationOutput
    assert "get_order_details" in kwargs["system_prompt"]
    assert result == "compiled-agent"


@pytest.mark.asyncio
async def test_build_evaluation_agent_fetches_tools_from_mcp_when_not_injected():
    with patch("agente2ConMCP.agente_evaluacion.create_agent") as mock_create_agent, patch(
        "agente2ConMCP.agente_evaluacion.get_evaluation_tools", new_callable=AsyncMock
    ) as mock_get_tools:
        mock_get_tools.return_value = [_FakeTool("get_order_details")]
        mock_create_agent.return_value = "compiled-agent"

        await build_evaluation_agent(mcp_supabase_url="http://localhost:8001/mcp")

    mock_get_tools.assert_awaited_once_with("http://localhost:8001/mcp")


# ---------------------------------------------------------------------------
# run_agent_evaluacion: debe ignorar la decision del LLM y recalcularla
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_evaluacion_overrides_llm_decision_with_deterministic_one():
    # El LLM "miente" y dice que el caso es valido con importe 0; el pedido
    # entrego hace 5 dias con un plazo de 14, asi que el resultado real
    # deterministico deberia ser 'valid' con el importe real (34.99).
    llm_output = _raw_llm_output(
        decision="invalid", eligible=False, refund_amount=0.0, rationale="mentira del LLM"
    )
    fake_agent = _FakeAgent(llm_output)
    request = EvaluationRequest(
        order_id="e1f2a3b4-c5d6-7890-efab-901234567890",
        reason="No era lo que esperaba",
        reason_category="changed_mind",
    )

    result = await run_agent_evaluacion(request, agent=fake_agent)

    assert result.decision == "valid"
    assert result.eligible is True
    assert result.refund_amount == 34.99
    assert "mentira del LLM" not in result.rationale


@pytest.mark.asyncio
async def test_run_agent_evaluacion_invalid_when_deadline_far_exceeded():
    llm_output = _raw_llm_output(delivered_at=_iso_days_ago(40), policy_max_return_days=14)
    fake_agent = _FakeAgent(llm_output)
    request = EvaluationRequest(order_id="e1f2a3b4-...", reason="ya no lo quiero", reason_category="changed_mind")

    result = await run_agent_evaluacion(request, agent=fake_agent)

    assert result.decision == "invalid"
    assert result.eligible is False


@pytest.mark.asyncio
async def test_run_agent_evaluacion_human_review_when_amount_exceeds_hitl_threshold():
    llm_output = _raw_llm_output(
        products=[
            {
                "order_item_id": "x",
                "name": "Portatil",
                "category": "electronics",
                "quantity": 1,
                "unit_price": 899.99,
                "total_price": 899.99,
            }
        ],
        category="electronics",
        delivered_at=_iso_days_ago(2),
        policy_max_return_days=15,
    )
    fake_agent = _FakeAgent(llm_output)
    request = EvaluationRequest(order_id="c9d0e1f2-...", reason="cambie de opinion", reason_category="changed_mind")

    result = await run_agent_evaluacion(request, agent=fake_agent)

    assert result.decision == "human_review"
    assert "100" in result.rationale


@pytest.mark.asyncio
async def test_run_agent_evaluacion_builds_agent_when_none_injected():
    expected = _raw_llm_output()
    fake_agent = _FakeAgent(expected)

    with patch(
        "agente2ConMCP.agente_evaluacion.build_evaluation_agent", new_callable=AsyncMock
    ) as mock_build_agent:
        mock_build_agent.return_value = fake_agent

        await run_agent_evaluacion(
            EvaluationRequest(order_id="o1", reason="r", reason_category="changed_mind"),
            model="openai:gpt-4o-mini",
            mcp_supabase_url="http://localhost:8001/mcp",
        )

    mock_build_agent.assert_awaited_once_with(
        model="openai:gpt-4o-mini", mcp_supabase_url="http://localhost:8001/mcp"
    )


@pytest.mark.asyncio
async def test_run_agent_evaluacion_tolerates_explicit_nulls_from_llm():
    # Visto en produccion: con schema estricto de OpenAI, el modelo a veces
    # devuelve null explicito en vez de omitir un campo que no sabe rellenar,
    # incluidos customer_name/customer_address (no solo los campos de
    # decision). No debe lanzar ValidationError ni propagar None a los
    # campos que otro agente (Resolucion) espera como str.
    llm_output = _raw_llm_output(
        customer_name=None,
        customer_address=None,
        decision=None,
        eligible=None,
        refund_amount=None,
        rationale=None,
        response_to_customer=None,
    )
    fake_agent = _FakeAgent(llm_output)
    request = EvaluationRequest(order_id="e1f2a3b4-...", reason="ya no lo quiero", reason_category="changed_mind")

    result = await run_agent_evaluacion(request, agent=fake_agent)

    assert result.customer_name == ""
    assert result.customer_address == ""
    assert isinstance(result.decision, str)
    assert isinstance(result.refund_amount, float)
    assert result.response_to_customer != ""


@pytest.mark.asyncio
async def test_run_agent_evaluacion_falls_back_to_invalid_when_order_not_found():
    # El LLM no pudo rellenar nada porque get_order_details fallo.
    llm_output = EvaluationOutput()
    fake_agent = _FakeAgent(llm_output)
    request = EvaluationRequest(order_id="no-existe", reason="r", reason_category="other")

    result = await run_agent_evaluacion(request, agent=fake_agent)

    assert result.decision == "invalid"
    assert result.eligible is False


# ---------------------------------------------------------------------------
# _classify_return: casos representativos de la seccion 5 de la politica general
# ---------------------------------------------------------------------------


def test_classify_return_valid_within_window_and_amount():
    decision, rationale = _classify_return(
        days_since_delivery=5, max_return_days=30, reason_category="changed_mind",
        refund_amount=59.99, customer_approved_returns=0,
    )
    assert decision == "valid"
    assert "dentro de plazo" in rationale


def test_classify_return_invalid_far_past_deadline():
    decision, rationale = _classify_return(
        days_since_delivery=40, max_return_days=14, reason_category="changed_mind",
        refund_amount=20.0, customer_approved_returns=0,
    )
    assert decision == "invalid"
    assert "superado ampliamente" in rationale


def test_classify_return_human_review_boundary_zone():
    decision, rationale = _classify_return(
        days_since_delivery=29, max_return_days=30, reason_category="changed_mind",
        refund_amount=20.0, customer_approved_returns=0,
    )
    assert decision == "human_review"
    assert "frontera" in rationale


def test_classify_return_human_review_amount_over_hitl_threshold():
    decision, rationale = _classify_return(
        days_since_delivery=2, max_return_days=30, reason_category="changed_mind",
        refund_amount=150.0, customer_approved_returns=0,
    )
    assert decision == "human_review"
    assert "100" in rationale


def test_classify_return_human_review_sensitive_reason():
    decision, rationale = _classify_return(
        days_since_delivery=2, max_return_days=30, reason_category="allergic_reaction",
        refund_amount=20.0, customer_approved_returns=0,
    )
    assert decision == "human_review"
    assert "motivo sensible" in rationale


def test_classify_return_human_review_frequent_returner():
    decision, rationale = _classify_return(
        days_since_delivery=2, max_return_days=30, reason_category="changed_mind",
        refund_amount=20.0, customer_approved_returns=4,
    )
    assert decision == "human_review"
    assert "abuso" in rationale


# ---------------------------------------------------------------------------
# _classify_return contra el golden dataset (dataset/eval_cases.csv, 480 casos
# generados por dataset/generate_dataset.py::classify_case)
# ---------------------------------------------------------------------------


def _load_eval_cases_without_condition_dependent_rows() -> list[dict]:
    """Filtra las filas cuya etiqueta depende de `condition` (estado del
    articulo) o de evidencia fotografica: _classify_return no modela esas
    ramas (ver su docstring), asi que no se pueden comparar 1:1."""
    condition_markers = ("precinto", "Estado del art", "evidencia fotogr")
    with open(REPO_ROOT / "dataset" / "eval_cases.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if not any(m in r["rationale"] for m in condition_markers)]


def test_classify_return_matches_golden_dataset():
    rows = _load_eval_cases_without_condition_dependent_rows()
    assert len(rows) > 300  # sanity check: el filtro no se ha comido el dataset entero

    mismatches = []
    for row in rows:
        approved_returns = 4 if row["is_frequent_returner"] == "True" else 0
        decision, _ = _classify_return(
            days_since_delivery=int(row["days_since_delivery"]),
            max_return_days=int(row["max_return_days"]),
            reason_category=row["reason_category"],
            refund_amount=float(row["refund_amount"]),
            customer_approved_returns=approved_returns,
        )
        if decision != row["expected_label"]:
            mismatches.append((row["case_id"], decision, row["expected_label"]))

    assert mismatches == []


# ---------------------------------------------------------------------------
# _sum_refund_amount
# ---------------------------------------------------------------------------


def test_sum_refund_amount_uses_total_price_when_present():
    products = [{"total_price": 34.99}, {"total_price": 10.0}]
    assert _sum_refund_amount(products) == 44.99


def test_sum_refund_amount_falls_back_to_unit_price_times_quantity():
    products = [{"unit_price": 20.0, "quantity": 3}]
    assert _sum_refund_amount(products) == 60.0


# ---------------------------------------------------------------------------
# Esquemas: EvaluationRequest / EvaluationOutput
# ---------------------------------------------------------------------------


def test_evaluation_output_defaults_are_conservative():
    output = EvaluationOutput()
    assert output.decision == "human_review"
    assert output.eligible is False
    assert output.refund_amount == 0.0
    # products es None hasta que _apply_deterministic_decision lo normaliza a
    # [] (ver docstring de EvaluationOutput sobre por que el default no es []).
    assert output.products is None


def test_evaluation_request_requires_core_fields():
    with pytest.raises(ValidationError):
        EvaluationRequest(order_id="o1")
