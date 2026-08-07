"""Tests de integración para el agente de Resolución."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from langchain_core.messages import AIMessage

from backend.agents.nodes.resolution import rejection_agent, resolution_agent, hitl_admin_node


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


class TestResolutionAgent:
    """Tests para el routing del nodo de Resolución: auto-aprobado vs. HITL.

    No repiten la lógica de negocio completa (etiqueta/registro/notificación),
    que se cubre en TestHitlAdminNode a través de _build_approved_return_updates.
    """

    @pytest.mark.asyncio
    async def test_auto_approved_below_threshold(self, mock_order_details, mock_label_result):
        """Reembolso <= 100€: resuelve directamente, sin pasar por hitl_admin."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(content="Tu devolución ha sido aprobada.")
        )

        state = {
            "refund_amount": 79.99,
            "order_id": "ord-001-uuid",
            "customer_id": "cust-001-uuid",
            "customer_name": "Ana García",
            "customer_email": "ana.garcia@example.com",
            "reason": "Producto defectuoso",
            "reason_category": "defective",
            "items_to_return": [{"order_item_id": "oi-001-uuid", "quantity": 1}],
            "order_details": mock_order_details,
        }

        with patch("backend.agents.nodes.resolution._build_llm", return_value=mock_llm), \
             patch("backend.agents.nodes.resolution.generate_shipping_label", new_callable=AsyncMock, return_value=mock_label_result), \
             patch("backend.agents.nodes.resolution.create_return_record", new_callable=AsyncMock, return_value={"return_request": {"id": "ret-1"}, "items_created": 1}), \
             patch("backend.agents.nodes.resolution.send_customer_notification", new_callable=AsyncMock, return_value={"status": "sent_simulated"}):
            result = await resolution_agent(state)

        assert result.goto == "__end__"
        assert result.update["resolution"] == "approved"
        assert result.update["admin_decision"] == "auto_approved"
        assert result.update["tracking_number"] == "RF-ABC1234567"

    @pytest.mark.asyncio
    async def test_hands_off_to_hitl_admin_when_approved(self):
        """Reembolso > 100€: al reanudar el interrupt() con aprobación, cede el
        turno a hitl_admin en vez de resolver el caso aquí mismo."""
        state = {
            "refund_amount": 250.0,
            "order_id": "ord-001-uuid",
            "customer_id": "cust-001-uuid",
            "reason": "Producto defectuoso",
        }

        with patch(
            "backend.agents.nodes.resolution.interrupt", return_value={"approved": True}
        ) as mock_interrupt:
            result = await resolution_agent(state)

        mock_interrupt.assert_called_once()
        assert result.goto == "hitl_admin"
        assert result.update["admin_decision"] == "approved"

    @pytest.mark.asyncio
    async def test_hands_off_to_hitl_admin_when_rejected(self):
        """Igual que arriba, pero si el admin rechaza en el interrupt():
        tampoco se resuelve aquí, hitl_admin es quien redacta el rechazo."""
        state = {
            "refund_amount": 250.0,
            "order_id": "ord-001-uuid",
            "customer_id": "cust-001-uuid",
            "reason": "Producto defectuoso",
        }

        with patch("backend.agents.nodes.resolution.interrupt", return_value={"approved": False}):
            result = await resolution_agent(state)

        assert result.goto == "hitl_admin"
        assert result.update["admin_decision"] == "rejected"

    @pytest.mark.asyncio
    async def test_hands_off_to_hitl_admin_for_sensitive_reason_even_below_threshold(self):
        """Reembolso bajo el umbral, pero motivo sensible (allergic_reaction):
        también debe pasar por HITL — no solo el importe dispara la pausa."""
        state = {
            "refund_amount": 20.0,
            "order_id": "ord-001-uuid",
            "customer_id": "cust-001-uuid",
            "reason": "Reacción alérgica al usar el producto",
            "reason_category": "allergic_reaction",
        }

        with patch(
            "backend.agents.nodes.resolution.interrupt", return_value={"approved": True}
        ) as mock_interrupt:
            result = await resolution_agent(state)

        mock_interrupt.assert_called_once()
        payload = mock_interrupt.call_args[0][0]
        assert any("motivo sensible" in r for r in payload["hitl_reasons"])
        assert result.goto == "hitl_admin"


class TestHitlAdminNode:
    """Tests para el nodo HITL de administrador (retoma tras resolution_agent)."""

    @pytest.mark.asyncio
    async def test_approved_completes_the_return(self, mock_order_details, mock_label_result):
        """Si el admin aprobó, completa el proceso igual que una aprobación
        automática: etiqueta, registro y notificación."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(content="Tu devolución ha sido aprobada por un administrador.")
        )

        state = {
            "admin_decision": "approved",
            "refund_amount": 250.0,
            "order_id": "ord-001-uuid",
            "customer_id": "cust-001-uuid",
            "customer_name": "Ana García",
            "customer_email": "ana.garcia@example.com",
            "reason": "Producto defectuoso",
            "reason_category": "defective",
            "items_to_return": [{"order_item_id": "oi-001-uuid", "quantity": 1}],
            "order_details": mock_order_details,
        }

        with patch("backend.agents.nodes.resolution._build_llm", return_value=mock_llm), \
             patch("backend.agents.nodes.resolution.generate_shipping_label", new_callable=AsyncMock, return_value=mock_label_result), \
             patch("backend.agents.nodes.resolution.create_return_record", new_callable=AsyncMock, return_value={"return_request": {"id": "ret-1"}, "items_created": 1}), \
             patch("backend.agents.nodes.resolution.send_customer_notification", new_callable=AsyncMock, return_value={"status": "sent_simulated"}):
            result = await hitl_admin_node(state)

        assert result["resolution"] == "approved"
        assert result["admin_decision"] == "approved"
        assert result["current_agent"] == "hitl_admin"
        assert result["tracking_number"] == "RF-ABC1234567"

    @pytest.mark.asyncio
    async def test_rejected_drafts_rejection_message(self):
        """Si el admin rechazó, redacta el rechazo sin generar etiqueta ni registrar nada."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(content="Lamentablemente no ha sido posible aprobar tu devolución.")
        )

        state = {"admin_decision": "rejected"}

        with patch("backend.agents.nodes.resolution._build_llm", return_value=mock_llm):
            result = await hitl_admin_node(state)

        assert result["resolution"] == "rejected_by_admin"
        assert result["admin_decision"] == "rejected"
        assert result["current_agent"] == "hitl_admin"
        assert len(result["messages"]) == 1

    @pytest.mark.asyncio
    async def test_defaults_to_approved_when_missing(self, mock_order_details, mock_label_result):
        """Si no hay admin_decision explícita en el estado, asume aprobado (mismo default que antes)."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="Aprobada."))

        state = {
            "refund_amount": 250.0,
            "order_id": "ord-001-uuid",
            "customer_id": "cust-001-uuid",
            "items_to_return": [],
            "order_details": mock_order_details,
        }

        with patch("backend.agents.nodes.resolution._build_llm", return_value=mock_llm), \
             patch("backend.agents.nodes.resolution.generate_shipping_label", new_callable=AsyncMock, return_value=mock_label_result), \
             patch("backend.agents.nodes.resolution.create_return_record", new_callable=AsyncMock, return_value={"return_request": {"id": "ret-1"}, "items_created": 0}), \
             patch("backend.agents.nodes.resolution.send_customer_notification", new_callable=AsyncMock, return_value={"status": "sent_simulated"}):
            result = await hitl_admin_node(state)

        assert result["admin_decision"] == "approved"
