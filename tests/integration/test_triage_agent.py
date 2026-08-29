"""Tests de integración para el agente de Triaje."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from backend.models import TriageOutput
from backend.agents.nodes.triage import triage_agent, fetch_order_data


class TestTriageAgent:
    """Tests para el nodo de triaje."""

    @pytest.mark.asyncio
    async def test_responds_to_user_message(self):
        """El agente genera una respuesta ante un mensaje del usuario."""
        mock_response = TriageOutput(
            response_to_customer="¡Hola! Lamento que tengas un problema. ¿Podrías indicarme tu número de pedido?",
            order_number=None,
            reason=None,
            reason_category=None,
            items_to_return=None,
        )

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=mock_response
        )

        state = {
            "messages": [HumanMessage(content="Quiero devolver un producto")],
        }

        with patch("backend.agents.nodes.triage._build_llm", return_value=mock_llm):
            result = await triage_agent(state)

        assert "messages" in result
        assert result["current_agent"] == "triage"
        # No tiene order_number aún
        assert result.get("order_number") is None

    @pytest.mark.asyncio
    async def test_extracts_json_when_complete(self):
        """Extrae datos cuando el LLM devuelve salida estructurada completa."""
        triage_out = TriageOutput(
            response_to_customer="Perfecto, he registrado tu solicitud.",
            order_number="ORD-2026-00123",
            reason="Producto roto",
            reason_category="defective",
            items_to_return=[
                {
                    "order_item_id": "oi-1",
                    "quantity": 1,
                    "condition": "defective",
                }
            ],
        )

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=triage_out
        )

        state = {
            "messages": [
                HumanMessage(
                    content="Mi pedido es ORD-2026-00123, el artículo está roto"
                )
            ],
        }

        with patch("backend.agents.nodes.triage._build_llm", return_value=mock_llm):
            result = await triage_agent(state)

        assert result["order_number"] == "ORD-2026-00123"
        assert result["reason"] == "Producto roto"
        assert result["reason_category"] == "defective"
        assert len(result["items_to_return"]) == 1


class TestFetchOrderData:
    """Tests para el nodo de carga de datos del pedido."""

    @pytest.mark.asyncio
    async def test_fetches_order_and_history(
        self, mock_order_details, mock_return_history_clean
    ):
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
            state = {"order_number": "ORD-2026-00123"}
            result = await fetch_order_data(state)

        assert result["customer_id"] == "cust-001-uuid"
        assert result["customer_name"] == "Ana García"
        assert result["customer_email"] == "ana.garcia@example.com"
        assert result["order_details"] == mock_order_details
        assert result["return_history"] == mock_return_history_clean

    @pytest.mark.asyncio
    async def test_returns_error_when_no_order_number(self):
        """Devuelve error si no hay order_number."""
        state = {"order_number": None}
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
            state = {"order_number": "ORD-INVALID"}
            result = await fetch_order_data(state)

        assert "error" in result
        assert "messages" in result  # mensaje empático al usuario
