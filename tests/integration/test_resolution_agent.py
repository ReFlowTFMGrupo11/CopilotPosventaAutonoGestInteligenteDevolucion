"""Tests de integración para el agente de Resolución."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from langchain_core.messages import AIMessage

from backend.agents.nodes.resolution import rejection_agent


class TestRejectionAgent:
    """Tests para el nodo de rechazo empático."""

    @pytest.mark.asyncio
    async def test_generates_empathetic_rejection(self):
        """Genera un mensaje de rechazo."""
        mock_response = AIMessage(
            content="Lamentamos informarte que no es posible procesar tu devolución..."
        )
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = {
            "eligibility_reason": "El plazo de 30 días ha expirado.",
        }

        with patch("backend.agents.nodes.resolution._build_llm", return_value=mock_llm):
            result = await rejection_agent(state)

        assert result["resolution"] == "rejected"
        assert result["current_agent"] == "resolver"
        assert len(result["messages"]) == 1
