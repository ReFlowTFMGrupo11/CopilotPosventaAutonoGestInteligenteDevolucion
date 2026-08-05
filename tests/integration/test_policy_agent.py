"""Tests de integración para el agente Evaluador de Políticas."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from backend.agents.policy_agent import policy_evaluator_agent


class TestPolicyEvaluatorAgent:
    """Tests para el nodo evaluador de políticas."""

    @pytest.mark.asyncio
    async def test_eligible_return(self, mock_order_details, mock_return_history_clean, mock_policy_results):
        """Devuelve is_eligible=True para una devolución válida."""
        llm_response_content = (
            "Tras evaluar la solicitud:\n\n"
            "```json\n"
            '{"is_eligible": true, "eligibility_reason": "Producto defectuoso dentro del plazo", '
            '"refund_amount": 79.99, "policy_applied": {"category": "electronics", "max_days": 30}}\n'
            "```"
        )
        mock_response = AIMessage(content=llm_response_content)
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = {
            "messages": [HumanMessage(content="test")],
            "order_details": mock_order_details,
            "return_history": mock_return_history_clean,
            "reason": "El producto está defectuoso",
            "reason_category": "defective",
            "items_to_return": [{"order_item_id": "oi-001-uuid", "quantity": 1, "condition": "defective"}],
        }

        with patch("backend.agents.policy_agent._build_llm", return_value=mock_llm), \
             patch("backend.agents.policy_agent.search_return_policy", new_callable=AsyncMock, return_value=mock_policy_results):
            result = await policy_evaluator_agent(state)

        assert result["is_eligible"] is True
        assert result["refund_amount"] == 79.99
        assert result["current_agent"] == "evaluator"

    @pytest.mark.asyncio
    async def test_not_eligible_return(self, mock_order_details, mock_return_history_clean, mock_policy_results):
        """Devuelve is_eligible=False cuando no cumple la política."""
        llm_response_content = (
            "La solicitud no cumple la política:\n\n"
            "```json\n"
            '{"is_eligible": false, "eligibility_reason": "Fuera del plazo de 30 días", '
            '"refund_amount": 0, "policy_applied": {"category": "electronics", "max_days": 30}}\n'
            "```"
        )
        mock_response = AIMessage(content=llm_response_content)
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = {
            "messages": [],
            "order_details": mock_order_details,
            "return_history": mock_return_history_clean,
            "reason": "Ya no lo quiero",
            "reason_category": "no_longer_needed",
            "items_to_return": [{"order_item_id": "oi-001-uuid", "quantity": 1, "condition": "used"}],
        }

        with patch("backend.agents.policy_agent._build_llm", return_value=mock_llm), \
             patch("backend.agents.policy_agent.search_return_policy", new_callable=AsyncMock, return_value=mock_policy_results):
            result = await policy_evaluator_agent(state)

        assert result["is_eligible"] is False
        assert result["refund_amount"] == 0

    @pytest.mark.asyncio
    async def test_handles_malformed_llm_response(self, mock_order_details, mock_return_history_clean, mock_policy_results):
        """Maneja correctamente respuestas del LLM sin JSON válido."""
        mock_response = AIMessage(content="No puedo evaluar esto correctamente.")
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = {
            "messages": [],
            "order_details": mock_order_details,
            "return_history": mock_return_history_clean,
            "reason": "test",
            "reason_category": "other",
            "items_to_return": [],
        }

        with patch("backend.agents.policy_agent._build_llm", return_value=mock_llm), \
             patch("backend.agents.policy_agent.search_return_policy", new_callable=AsyncMock, return_value=mock_policy_results):
            result = await policy_evaluator_agent(state)

        # Debe defaultear a no elegible si no puede parsear
        assert result["is_eligible"] is False
        assert result["eligibility_reason"] is not None
