"""Tests de integración para el agente de Triaje."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from langchain_core.messages import HumanMessage

from backend.agents.nodes.triage import triage_agent, fetch_order_data
from backend.models import ReturnItem, TriageOutput


def _mock_structured_llm(triage_output: TriageOutput | None) -> MagicMock:
    """triage_agent llama a llm.with_structured_output(TriageOutput).ainvoke(...),
    no a llm.ainvoke(...) directamente: with_structured_output devuelve un
    "runnable" nuevo, distinto del objeto LLM original, así que hay que
    mockear esa cadena completa (no basta con parchear .ainvoke en el mock
    del LLM base).
    """
    structured_runnable = MagicMock()
    structured_runnable.ainvoke = AsyncMock(return_value=triage_output)

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = structured_runnable
    return mock_llm


class TestTriageAgent:
    """Tests para el nodo de triaje."""

    @pytest.mark.asyncio
    async def test_responds_to_user_message(self):
        """El agente genera una respuesta ante un mensaje del usuario."""
        triage_output = TriageOutput(
            response_to_customer="¡Hola! Lamento que tengas un problema. ¿Podrías indicarme tu número de pedido?"
        )
        mock_llm = _mock_structured_llm(triage_output)

        state = {
            "messages": [HumanMessage(content="Quiero devolver un producto")],
        }

        with patch("backend.agents.nodes.triage._build_llm", return_value=mock_llm):
            result = await triage_agent(state)

        assert "messages" in result
        assert result["current_agent"] == "triage"
        # No tiene order_id aún
        assert result.get("order_id") is None

    @pytest.mark.asyncio
    async def test_extracts_data_when_complete(self):
        """Extrae order_id/reason/items cuando el LLM ya tiene toda la información."""
        triage_output = TriageOutput(
            response_to_customer="Perfecto, he registrado tu solicitud.",
            order_id="ord-123",
            reason="Producto roto",
            reason_category="defective",
            items_to_return=[
                ReturnItem(order_item_id="oi-1", quantity=1, condition="defective")
            ],
        )
        mock_llm = _mock_structured_llm(triage_output)

        state = {
            "messages": [HumanMessage(content="Mi pedido es ord-123, el artículo está roto")],
        }

        with patch("backend.agents.nodes.triage._build_llm", return_value=mock_llm):
            result = await triage_agent(state)

        assert result["order_id"] == "ord-123"
        assert result["reason"] == "Producto roto"
        assert result["reason_category"] == "defective"
        assert len(result["items_to_return"]) == 1

    @pytest.mark.asyncio
    async def test_falls_back_when_structured_output_is_none(self):
        """Si el LLM no devuelve structured output válido, responde con un fallback genérico."""
        mock_llm = _mock_structured_llm(None)

        state = {
            "messages": [HumanMessage(content="???")],
        }

        with patch("backend.agents.nodes.triage._build_llm", return_value=mock_llm):
            result = await triage_agent(state)

        assert "messages" in result
        assert result["current_agent"] == "triage"
        assert result.get("order_id") is None


class TestFetchOrderData:
    """Tests para el nodo de carga de datos del pedido."""

    @pytest.mark.asyncio
    async def test_fetches_order_and_history(self, mock_order_details, mock_return_history_clean):
        """Carga correctamente los datos del pedido y el historial."""
        with patch(
            "backend.agents.nodes.triage.get_order_details",
            new_callable=AsyncMock,
            return_value=mock_order_details,
        ), patch(
            "backend.agents.nodes.triage.get_customer_return_history",
            new_callable=AsyncMock,
            return_value=mock_return_history_clean,
        ):
            state = {"order_id": "ord-001-uuid"}
            result = await fetch_order_data(state)

        assert result["customer_id"] == "cust-001-uuid"
        assert result["customer_name"] == "Ana García"
        assert result["customer_email"] == "ana.garcia@example.com"
        assert result["order_details"] == mock_order_details
        assert result["return_history"] == mock_return_history_clean

    @pytest.mark.asyncio
    async def test_returns_error_when_no_order_id(self):
        """Devuelve error si no hay order_id."""
        state = {"order_id": None}
        result = await fetch_order_data(state)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_returns_error_on_exception(self):
        """Devuelve error si la consulta falla."""
        with patch(
            "backend.agents.nodes.triage.get_order_details",
            new_callable=AsyncMock,
            side_effect=Exception("DB connection failed"),
        ):
            state = {"order_id": "ord-invalid"}
            result = await fetch_order_data(state)

        assert "error" in result
        assert "messages" in result  # mensaje empático al usuario
