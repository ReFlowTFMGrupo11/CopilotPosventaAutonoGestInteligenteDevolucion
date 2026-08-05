"""Tests de integración para el flujo completo del grafo."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from backend.agents.graph import build_return_graph, route_after_triage, route_after_evaluator


class TestGraphCompilation:
    """Tests para verificar que el grafo se compila correctamente."""

    def test_graph_compiles(self):
        """El grafo se compila sin errores."""
        graph = build_return_graph()
        assert graph is not None

    def test_graph_has_expected_nodes(self):
        """El grafo contiene todos los nodos esperados."""
        graph = build_return_graph()
        # El grafo compilado tiene un atributo con los nodos
        node_names = set(graph.get_graph().nodes.keys())
        expected = {"triage", "fetch_order_data", "evaluator", "resolver", "reject", "hitl_admin"}
        assert expected.issubset(node_names)


class TestGraphFlow:
    """Tests end-to-end del flujo del grafo (todo mockeado)."""

    @pytest.mark.asyncio
    async def test_eligible_return_auto_approved(
        self, mock_order_details, mock_return_history_clean, mock_policy_results, mock_label_result
    ):
        """Flujo completo: devolución elegible ≤100€ → aprobada automáticamente."""
        graph = build_return_graph()

        # Mock del triaje: simula que ya extrajo toda la info
        triage_response = AIMessage(
            content='```json\n{"order_id": "ord-001-uuid", "reason": "Defectuoso", '
            '"reason_category": "defective", '
            '"items_to_return": [{"order_item_id": "oi-001-uuid", "quantity": 1, "condition": "defective"}]}\n```'
        )

        # Mock del evaluador: elegible
        eval_response = AIMessage(
            content='```json\n{"is_eligible": true, "eligibility_reason": "Cumple política", '
            '"refund_amount": 79.99, "policy_applied": {}}\n```'
        )

        # Mock del resolver: mensaje final
        resolve_response = AIMessage(
            content="¡Tu devolución ha sido aprobada! Tracking: RF-ABC1234567"
        )

        call_count = {"n": 0}

        async def mock_ainvoke(messages):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return triage_response
            elif call_count["n"] == 2:
                return eval_response
            else:
                return resolve_response

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=mock_ainvoke)

        with patch("backend.agents.triage_agent._build_llm", return_value=mock_llm), \
             patch("backend.agents.policy_agent._build_llm", return_value=mock_llm), \
             patch("backend.agents.resolution_agent._build_llm", return_value=mock_llm), \
             patch("backend.services.supabase_service.get_order_details", new_callable=AsyncMock, return_value=mock_order_details), \
             patch("backend.services.supabase_service.get_customer_return_history", new_callable=AsyncMock, return_value=mock_return_history_clean), \
             patch("backend.services.supabase_service.search_return_policy", new_callable=AsyncMock, return_value=mock_policy_results), \
             patch("backend.services.supabase_service.create_return_record", new_callable=AsyncMock, return_value={"return_request": {"id": "ret-1"}, "items_created": 1}), \
             patch("backend.services.logistics_service.generate_shipping_label", new_callable=AsyncMock, return_value=mock_label_result), \
             patch("backend.services.logistics_service.send_customer_notification", new_callable=AsyncMock, return_value={"status": "sent_simulated"}):

            config = {"configurable": {"thread_id": "test-flow-1"}}
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content="Quiero devolver mis auriculares, están defectuosos")]},
                config=config,
            )

        assert result.get("resolution") == "approved"
        assert result.get("tracking_number") == "RF-ABC1234567"

    @pytest.mark.asyncio
    async def test_not_eligible_gets_rejected(
        self, mock_order_details, mock_return_history_clean, mock_policy_results
    ):
        """Flujo completo: devolución no elegible → rechazo empático."""
        graph = build_return_graph()

        triage_response = AIMessage(
            content='```json\n{"order_id": "ord-001-uuid", "reason": "Ya no lo quiero", '
            '"reason_category": "no_longer_needed", '
            '"items_to_return": [{"order_item_id": "oi-001-uuid", "quantity": 1, "condition": "used"}]}\n```'
        )

        eval_response = AIMessage(
            content='```json\n{"is_eligible": false, "eligibility_reason": "Producto usado fuera de plazo", '
            '"refund_amount": 0, "policy_applied": {}}\n```'
        )

        reject_response = AIMessage(
            content="Lamentamos informarte que no podemos procesar tu devolución..."
        )

        call_count = {"n": 0}

        async def mock_ainvoke(messages):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return triage_response
            elif call_count["n"] == 2:
                return eval_response
            else:
                return reject_response

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=mock_ainvoke)

        with patch("backend.agents.triage_agent._build_llm", return_value=mock_llm), \
             patch("backend.agents.policy_agent._build_llm", return_value=mock_llm), \
             patch("backend.agents.resolution_agent._build_llm", return_value=mock_llm), \
             patch("backend.services.supabase_service.get_order_details", new_callable=AsyncMock, return_value=mock_order_details), \
             patch("backend.services.supabase_service.get_customer_return_history", new_callable=AsyncMock, return_value=mock_return_history_clean), \
             patch("backend.services.supabase_service.search_return_policy", new_callable=AsyncMock, return_value=mock_policy_results):

            config = {"configurable": {"thread_id": "test-flow-2"}}
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content="Quiero devolver, ya no lo necesito")]},
                config=config,
            )

        assert result.get("resolution") == "rejected"
        assert result.get("tracking_number") is None
