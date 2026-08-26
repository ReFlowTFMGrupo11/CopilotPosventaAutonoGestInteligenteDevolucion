"""Tests de integración para el agente Evaluador de Políticas."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from langchain_core.messages import HumanMessage

from backend.agents.nodes.policy import policy_evaluator_agent
from backend.models import ItemEligibility, PolicyEvaluationOutput


def _mock_llm_with_structured_output(output: PolicyEvaluationOutput | None) -> MagicMock:
    """Construye un LLM mockeado que imita ``llm.with_structured_output(...).ainvoke``."""
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=output)
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


class TestPolicyEvaluatorAgent:
    """Tests para el nodo evaluador de políticas."""

    @pytest.mark.asyncio
    async def test_eligible_return(self, mock_order_details, mock_return_history_clean, mock_policy_results):
        """Marca el artículo como elegible cuando cumple la política de su categoría."""
        mock_output = PolicyEvaluationOutput(items=[
            ItemEligibility(
                order_item_id="oi-001-uuid",
                is_eligible=True,
                eligibility_reason="Producto defectuoso dentro del plazo",
                refund_amount=79.99,
                policy_category="electronics",
            ),
        ])
        mock_llm = _mock_llm_with_structured_output(mock_output)

        state = {
            "messages": [HumanMessage(content="test")],
            "order_details": mock_order_details,
            "return_history": mock_return_history_clean,
            "reason": "El producto está defectuoso",
            "reason_category": "defective",
            "items_to_return": [{"order_item_id": "oi-001-uuid", "quantity": 1, "condition": "defective"}],
        }

        with patch("backend.agents.nodes.policy._build_llm", return_value=mock_llm), \
             patch("backend.agents.nodes.policy.search_return_policy", new_callable=AsyncMock, return_value=mock_policy_results):
            result = await policy_evaluator_agent(state)

        assert result["any_eligible"] is True
        assert result["refund_amount"] == 79.99
        assert result["current_agent"] == "evaluator"
        assert result["items_eligibility"] == [
            {
                "order_item_id": "oi-001-uuid",
                "is_eligible": True,
                "eligibility_reason": "Producto defectuoso dentro del plazo",
                "refund_amount": 79.99,
                "policy_category": "electronics",
            }
        ]

    @pytest.mark.asyncio
    async def test_not_eligible_return(self, mock_order_details, mock_return_history_clean, mock_policy_results):
        """Marca el artículo como no elegible cuando incumple la política."""
        mock_output = PolicyEvaluationOutput(items=[
            ItemEligibility(
                order_item_id="oi-001-uuid",
                is_eligible=False,
                eligibility_reason="Fuera del plazo de 30 días",
                refund_amount=0.0,
                policy_category="electronics",
            ),
        ])
        mock_llm = _mock_llm_with_structured_output(mock_output)

        state = {
            "messages": [],
            "order_details": mock_order_details,
            "return_history": mock_return_history_clean,
            "reason": "Ya no lo quiero",
            "reason_category": "no_longer_needed",
            "items_to_return": [{"order_item_id": "oi-001-uuid", "quantity": 1, "condition": "used"}],
        }

        with patch("backend.agents.nodes.policy._build_llm", return_value=mock_llm), \
             patch("backend.agents.nodes.policy.search_return_policy", new_callable=AsyncMock, return_value=mock_policy_results):
            result = await policy_evaluator_agent(state)

        assert result["any_eligible"] is False
        assert result["refund_amount"] == 0

    @pytest.mark.asyncio
    async def test_handles_empty_structured_output(self, mock_order_details, mock_return_history_clean, mock_policy_results):
        """Si el LLM no devuelve salida estructurada (None), se marca todo como no elegible."""
        mock_llm = _mock_llm_with_structured_output(None)

        state = {
            "messages": [],
            "order_details": mock_order_details,
            "return_history": mock_return_history_clean,
            "reason": "test",
            "reason_category": "other",
            "items_to_return": [{"order_item_id": "oi-001-uuid", "quantity": 1, "condition": "used"}],
        }

        with patch("backend.agents.nodes.policy._build_llm", return_value=mock_llm), \
             patch("backend.agents.nodes.policy.search_return_policy", new_callable=AsyncMock, return_value=mock_policy_results):
            result = await policy_evaluator_agent(state)

        # Debe defaultear a no elegible si no puede evaluar
        assert result["any_eligible"] is False
        assert result["eligibility_reason"] is not None
        assert result["items_eligibility"][0]["is_eligible"] is False

    @pytest.mark.asyncio
    async def test_no_items_to_return_skips_rag_and_returns_empty(
        self, mock_order_details, mock_return_history_clean
    ):
        """Sin artículos a devolver, no se hace ninguna búsqueda RAG."""
        mock_output = PolicyEvaluationOutput(items=[])
        mock_llm = _mock_llm_with_structured_output(mock_output)
        search_mock = AsyncMock()

        state = {
            "messages": [],
            "order_details": mock_order_details,
            "return_history": mock_return_history_clean,
            "reason": "test",
            "reason_category": "other",
            "items_to_return": [],
        }

        with patch("backend.agents.nodes.policy._build_llm", return_value=mock_llm), \
             patch("backend.agents.nodes.policy.search_return_policy", search_mock):
            result = await policy_evaluator_agent(state)

        search_mock.assert_not_awaited()
        assert result["any_eligible"] is False
