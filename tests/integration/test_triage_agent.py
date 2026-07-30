"""Tests de integración para el agente de Triaje."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from backend.agents.triage_agent import triage_agent, fetch_order_data


class TestTriageAgent:
    """Tests para el nodo de triaje."""

    @pytest.mark.asyncio
    async def test_responds_to_user_message(self):
        """El agente genera una respuesta ante un mensaje del usuario."""
        mock_response = AIMessage(
            content="¡Hola! Lamento que tengas un problema. ¿Podrías indicarme tu número de pedido?"
        )

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = {
            "messages": [HumanMessage(content="Quiero devolver un producto")],
        }

        with patch("backend.agents.triage_agent._build_llm", return_value=mock_llm):
            result = await triage_agent(state)

        assert "messages" in result
        assert result["current_agent"] == "triage"
        # No tiene order_id aún
        assert result.get("order_id") is None

    @pytest.mark.asyncio
    async def test_extracts_json_when_complete(self):
        """Extrae datos cuando el LLM responde con JSON."""
        json_response = (
            "Perfecto, he registrado tu solicitud.\n\n"
            "```json\n"
            '{"order_id": "ord-123", "reason": "Producto roto", '
            '"reason_category": "defective", '
            '"items_to_return": [{"order_item_id": "oi-1", "quantity": 1, "condition": "defective"}]}\n'
            "```"
        )
        mock_response = AIMessage(content=json_response)

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = {
            "messages": [HumanMessage(content="Mi pedido es ord-123, el artículo está roto")],
        }

        with patch("backend.agents.triage_agent._build_llm", return_value=mock_llm):
            result = await triage_agent(state)

        assert result["order_id"] == "ord-123"
        assert result["reason"] == "Producto roto"
        assert result["reason_category"] == "defective"
        assert len(result["items_to_return"]) == 1


class TestFetchOrderData:
    """Tests para el nodo de carga de datos del pedido."""

    @pytest.mark.asyncio
    async def test_fetches_order_and_history(self, mock_order_details, mock_return_history_clean):
        """Carga correctamente los datos del pedido y el historial."""
        with patch(
            "backend.agents.triage_agent.get_order_details",
            new_callable=AsyncMock,
            return_value=mock_order_details,
        ), patch(
            "backend.agents.triage_agent.get_customer_return_history",
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
            "backend.agents.triage_agent.get_order_details",
            new_callable=AsyncMock,
            side_effect=Exception("DB connection failed"),
        ):
            state = {"order_id": "ord-invalid"}
            result = await fetch_order_data(state)

        assert "error" in result
        assert "messages" in result  # mensaje empático al usuario
