"""Tests de integración para el flujo completo del grafo."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from backend.agents.graph import build_return_graph, route_after_triage, route_after_evaluator
from backend.models import ReturnItem, TriageOutput


def _mock_triage_llm(triage_output: TriageOutput) -> MagicMock:
    """triage_agent llama a llm.with_structured_output(TriageOutput).ainvoke(...):
    hay que mockear esa cadena completa, no solo .ainvoke() del LLM base
    (ver también tests/integration/test_triage_agent.py)."""
    structured_runnable = MagicMock()
    structured_runnable.ainvoke = AsyncMock(return_value=triage_output)

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = structured_runnable
    return mock_llm


class TestGraphCompilation:
    """Tests para verificar que el grafo se compila correctamente."""

    @pytest.mark.asyncio
    async def test_graph_compiles(self):
        """El grafo se compila sin errores."""
        graph = await build_return_graph(checkpointer=InMemorySaver())
        assert graph is not None

    @pytest.mark.asyncio
    async def test_graph_has_expected_nodes(self):
        """El grafo contiene todos los nodos esperados."""
        graph = await build_return_graph(checkpointer=InMemorySaver())
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
        graph = await build_return_graph(checkpointer=InMemorySaver())

        # Mock del triaje: simula que ya extrajo toda la info (structured output).
        triage_output = TriageOutput(
            response_to_customer="Perfecto, vamos a procesar tu devolución.",
            order_id="ord-001-uuid",
            reason="Defectuoso",
            reason_category="defective",
            items_to_return=[ReturnItem(order_item_id="oi-001-uuid", quantity=1, condition="defective")],
        )

        # Mock del evaluador: elegible (el refund_amount de aquí se ignora a
        # propósito — policy.py lo recalcula en Python a partir del pedido).
        eval_response = AIMessage(
            content='```json\n{"is_eligible": true, "eligibility_reason": "Cumple política", '
            '"refund_amount": 79.99, "policy_applied": {}}\n```'
        )

        # Mock del resolver: mensaje final
        resolve_response = AIMessage(
            content="¡Tu devolución ha sido aprobada! Tracking: RF-ABC1234567"
        )

        mock_policy_llm = MagicMock()
        mock_policy_llm.ainvoke = AsyncMock(return_value=eval_response)

        mock_resolution_llm = MagicMock()
        mock_resolution_llm.ainvoke = AsyncMock(return_value=resolve_response)

        with patch("backend.agents.nodes.triage._build_llm", return_value=_mock_triage_llm(triage_output)), \
             patch("backend.agents.nodes.policy._build_llm", return_value=mock_policy_llm), \
             patch("backend.agents.nodes.resolution._build_llm", return_value=mock_resolution_llm), \
             patch("backend.agents.nodes.triage.get_order_details", new_callable=AsyncMock, return_value=mock_order_details), \
             patch("backend.agents.nodes.triage.get_customer_return_history", new_callable=AsyncMock, return_value=mock_return_history_clean), \
             patch("backend.agents.nodes.policy.search_return_policy", new_callable=AsyncMock, return_value=mock_policy_results), \
             patch("backend.agents.nodes.resolution.create_return_record", new_callable=AsyncMock, return_value={"return_request": {"id": "ret-1"}, "items_created": 1}), \
             patch("backend.agents.nodes.resolution.generate_shipping_label", new_callable=AsyncMock, return_value=mock_label_result), \
             patch("backend.agents.nodes.resolution.send_customer_notification", new_callable=AsyncMock, return_value={"status": "sent_simulated"}):

            config = {"configurable": {"thread_id": "test-flow-1"}}
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content="Quiero devolver mis auriculares, están defectuosos")]},
                config=config,
            )

        assert result.get("resolution") == "approved"
        assert result.get("tracking_number") == "RF-ABC1234567"
        # refund_amount recalculado en Python (unit_price 79.99 x quantity 1
        # de oi-001-uuid en mock_order_details), no el 79.99 "de coincidencia"
        # del JSON del evaluador.
        assert result.get("refund_amount") == 79.99

    @pytest.mark.asyncio
    async def test_not_eligible_gets_rejected(
        self, mock_order_details, mock_return_history_clean, mock_policy_results
    ):
        """Flujo completo: devolución no elegible → rechazo empático."""
        graph = await build_return_graph(checkpointer=InMemorySaver())

        triage_output = TriageOutput(
            response_to_customer="Entendido, vamos a revisar tu solicitud.",
            order_id="ord-001-uuid",
            reason="Ya no lo quiero",
            reason_category="no_longer_needed",
            items_to_return=[ReturnItem(order_item_id="oi-001-uuid", quantity=1, condition="used")],
        )

        eval_response = AIMessage(
            content='```json\n{"is_eligible": false, "eligibility_reason": "Producto usado fuera de plazo", '
            '"refund_amount": 0, "policy_applied": {}}\n```'
        )

        reject_response = AIMessage(
            content="Lamentamos informarte que no podemos procesar tu devolución..."
        )

        mock_policy_llm = MagicMock()
        mock_policy_llm.ainvoke = AsyncMock(return_value=eval_response)

        mock_resolution_llm = MagicMock()
        mock_resolution_llm.ainvoke = AsyncMock(return_value=reject_response)

        with patch("backend.agents.nodes.triage._build_llm", return_value=_mock_triage_llm(triage_output)), \
             patch("backend.agents.nodes.policy._build_llm", return_value=mock_policy_llm), \
             patch("backend.agents.nodes.resolution._build_llm", return_value=mock_resolution_llm), \
             patch("backend.agents.nodes.triage.get_order_details", new_callable=AsyncMock, return_value=mock_order_details), \
             patch("backend.agents.nodes.triage.get_customer_return_history", new_callable=AsyncMock, return_value=mock_return_history_clean), \
             patch("backend.agents.nodes.policy.search_return_policy", new_callable=AsyncMock, return_value=mock_policy_results):

            config = {"configurable": {"thread_id": "test-flow-2"}}
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content="Quiero devolver, ya no lo necesito")]},
                config=config,
            )

        assert result.get("resolution") == "rejected"
        assert result.get("tracking_number") is None

    @pytest.mark.asyncio
    async def test_eligible_return_above_threshold_pauses_for_hitl(
        self, mock_order_details, mock_return_history_clean, mock_policy_results, mock_label_result
    ):
        """Flujo completo: devolución elegible >100€ → se pausa en hitl_admin,
        y al reanudar con Command(resume=...) es hitl_admin quien la completa."""
        from langgraph.types import Command

        graph = await build_return_graph(checkpointer=InMemorySaver())

        # Dos artículos devueltos para superar el umbral de 100€
        # (oi-001-uuid: 79.99 + oi-002-uuid: 30.00 = 109.99, ver conftest.py).
        triage_output = TriageOutput(
            response_to_customer="Perfecto, vamos a procesar tu devolución.",
            order_id="ord-001-uuid",
            reason="Defectuoso",
            reason_category="defective",
            items_to_return=[
                ReturnItem(order_item_id="oi-001-uuid", quantity=1, condition="defective"),
                ReturnItem(order_item_id="oi-002-uuid", quantity=2, condition="defective"),
            ],
        )

        eval_response = AIMessage(
            content='```json\n{"is_eligible": true, "eligibility_reason": "Cumple política", '
            '"refund_amount": 0, "policy_applied": {}}\n```'
        )

        resolve_response = AIMessage(
            content="Tu devolución ha sido revisada y aprobada por un administrador."
        )

        mock_policy_llm = MagicMock()
        mock_policy_llm.ainvoke = AsyncMock(return_value=eval_response)

        mock_resolution_llm = MagicMock()
        mock_resolution_llm.ainvoke = AsyncMock(return_value=resolve_response)

        with patch("backend.agents.nodes.triage._build_llm", return_value=_mock_triage_llm(triage_output)), \
             patch("backend.agents.nodes.policy._build_llm", return_value=mock_policy_llm), \
             patch("backend.agents.nodes.resolution._build_llm", return_value=mock_resolution_llm), \
             patch("backend.agents.nodes.triage.get_order_details", new_callable=AsyncMock, return_value=mock_order_details), \
             patch("backend.agents.nodes.triage.get_customer_return_history", new_callable=AsyncMock, return_value=mock_return_history_clean), \
             patch("backend.agents.nodes.policy.search_return_policy", new_callable=AsyncMock, return_value=mock_policy_results), \
             patch("backend.agents.nodes.resolution.create_return_record", new_callable=AsyncMock, return_value={"return_request": {"id": "ret-1"}, "items_created": 2}), \
             patch("backend.agents.nodes.resolution.generate_shipping_label", new_callable=AsyncMock, return_value=mock_label_result), \
             patch("backend.agents.nodes.resolution.send_customer_notification", new_callable=AsyncMock, return_value={"status": "sent_simulated"}):

            config = {"configurable": {"thread_id": "test-flow-hitl"}}
            paused = await graph.ainvoke(
                {"messages": [HumanMessage(content="Quiero devolver dos artículos defectuosos")]},
                config=config,
            )

            # El grafo se pausó: no hay resolución todavía, y el checkpointer
            # tiene una tarea pendiente en el nodo "resolver".
            state = await graph.aget_state(config)
            assert state.next == ("resolver",)
            assert paused.get("resolution") is None

            # Reanuda como haría POST /api/admin/approve/{thread_id} en
            # backend/main.py: Command(resume={"approved": True}).
            result = await graph.ainvoke(Command(resume={"approved": True}), config=config)

        assert result.get("resolution") == "approved"
        assert result.get("current_agent") == "hitl_admin"
        assert result.get("tracking_number") == "RF-ABC1234567"
