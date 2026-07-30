"""Tests de integración para el agente de Resolución."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from langchain_core.messages import AIMessage

from backend.agents.resolution_agent import rejection_agent, hitl_admin_node


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

        with patch("backend.agents.resolution_agent._build_llm", return_value=mock_llm):
            result = await rejection_agent(state)

        assert result["resolution"] == "rejected"
        assert result["current_agent"] == "resolver"
        assert len(result["messages"]) == 1


class TestHitlAdminNode:
    """Tests para el nodo HITL de administrador."""

    @pytest.mark.asyncio
    async def test_approved_message(self):
        """Genera mensaje de aprobación cuando admin aprueba."""
        state = {"admin_decision": "approved"}
        result = await hitl_admin_node(state)

        assert result["resolution"] == "approved"
        assert "aprobada" in result["messages"][0].content.lower()

    @pytest.mark.asyncio
    async def test_rejected_message(self):
        """Genera mensaje de rechazo cuando admin rechaza."""
        state = {"admin_decision": "rejected"}
        result = await hitl_admin_node(state)

        assert result["resolution"] == "rejected"
        assert "no ha sido posible" in result["messages"][0].content.lower()

    @pytest.mark.asyncio
    async def test_defaults_to_approved(self):
        """Si no hay decisión explícita, asume aprobado."""
        state = {}
        result = await hitl_admin_node(state)
        assert result["resolution"] == "approved"
