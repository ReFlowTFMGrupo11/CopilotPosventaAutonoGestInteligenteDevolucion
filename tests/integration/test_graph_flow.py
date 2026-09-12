"""Tests de integración para el flujo completo del grafo.

Notas de mocking (alineadas con el resto de la suite, ver
test_triage_agent.py / test_mixed_category_order_returns.py):

- ``build_return_graph()`` es ``async`` (crea el checkpointer) -> siempre
  con ``await``.
- Los nodos viven en ``backend.agents.nodes.{triage,evaluator,resolution}``,
  no en ``backend.agents.<nombre>_agent`` (ese layout es de una versión
  anterior del grafo).
- triage/evaluator usan salida estructurada (``with_structured_output``):
  el mock debe configurarse en
  ``mock_llm.with_structured_output.return_value.ainvoke``, devolviendo
  directamente una instancia Pydantic (``TriageOutput``/
  ``PolicyEvaluationOutput``), no un ``AIMessage`` con JSON en markdown.
- Las llamadas a Supabase/MCP/logística se importan con
  ``from backend.agents.infra.mcp_client import ...`` dentro de cada nodo,
  así que hay que mockearlas en el namespace del nodo
  (``backend.agents.nodes.<modulo>.<función>``), no en
  ``mcp_client``/``orders_service``/``returns_service``/``policy_service``/
  ``logistics_service`` directamente.
- ``items_confirmed`` solo se fija a True si ``items_to_return`` NO cambia
  respecto al turno anterior (ver triage.py::_items_key) — se simula un
  estado inicial que ya trae ``items_to_return`` fijado y una respuesta de
  triaje que lo mantiene (``items_to_return=None`` = "sin cambios") con
  ``items_confirmed=True``, en vez de reproducir la conversación completa
  turno a turno (esa dinámica multi-turno ya la cubre test_triage_agent.py
  y test_routing.py).
- ``max_return_days``/``allowed_conditions`` se omiten del policy_info
  mockeado a propósito: con ``None``, las reglas de plazo/condición de
  policy_rules.py no vetan nada (ver test_policy_rules.py::
  test_no_max_return_days_never_blocks_on_deadline), así el test no
  depende de la fecha real del sistema en el momento de ejecutarlo.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from backend.agents.graph import (
    build_return_graph,
    route_after_triage,
    route_after_evaluator,
)
from backend.models import ItemEligibility, PolicyEvaluationOutput, TriageOutput


class TestGraphCompilation:
    """Tests para verificar que el grafo se compila correctamente."""

    @pytest.mark.asyncio
    async def test_graph_compiles(self):
        """El grafo se compila sin errores."""
        graph = await build_return_graph()
        assert graph is not None

    @pytest.mark.asyncio
    async def test_graph_has_expected_nodes(self):
        """El grafo contiene todos los nodos esperados."""
        graph = await build_return_graph()
        # El grafo compilado tiene un atributo con los nodos
        node_names = set(graph.get_graph().nodes.keys())
        expected = {
            "triage",
            "fetch_order_data",
            "evaluator",
            "resolver",
            "reject",
        }
        assert expected.issubset(node_names)


def _mock_llm_with_structured_output(output) -> MagicMock:
    """Mock de un ChatOpenAI que usa .with_structured_output(..., include_raw=True).ainvoke()
    (ver backend/agents/usage_tracking.py::invoke_structured_tracked) — la forma real es un
    dict con "raw"/"parsed"/"parsing_error", no el objeto Pydantic a secas."""
    llm = MagicMock()
    llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value={
            "raw": AIMessage(content=""),
            "parsed": output,
            "parsing_error": None,
        }
    )
    return llm


def _mock_llm_freeform(response: AIMessage) -> MagicMock:
    """Mock de un ChatOpenAI usado con .ainvoke() directo (sin structured output)."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=response)
    return llm


class TestGraphFlow:
    """Tests end-to-end del flujo del grafo (todo mockeado)."""

    @pytest.mark.asyncio
    async def test_eligible_return_auto_approved(
        self, mock_order_details, mock_return_history_clean, mock_label_result
    ):
        """Flujo completo: devolución elegible ≤100€ → aprobada automáticamente."""
        graph = await build_return_graph()

        # Turno de confirmación: mismo item_to_return que ya viene en el
        # estado semillado (ver docstring del módulo) -> items_confirmed=True.
        triage_out = TriageOutput(
            response_to_customer="Perfecto, tramitando tu devolución.",
            items_confirmed=True,
        )
        eval_out = PolicyEvaluationOutput(
            items=[
                ItemEligibility(
                    order_item_id="oi-001-uuid",
                    is_eligible=True,
                    eligibility_reason="Defectuoso, cumple la política de la categoría.",
                    refund_amount=79.99,
                    policy_category="electronics",
                ),
            ]
        )
        resolve_response = AIMessage(
            content="¡Tu devolución ha sido aprobada! Tracking: RF-ABC1234567"
        )

        with patch(
            "backend.agents.nodes.triage._build_llm",
            return_value=_mock_llm_with_structured_output(triage_out),
        ), patch(
            "backend.agents.nodes.triage.get_order_details",
            new_callable=AsyncMock,
            return_value=mock_order_details,
        ), patch(
            "backend.agents.nodes.triage.get_customer_return_history",
            new_callable=AsyncMock,
            return_value=mock_return_history_clean,
        ), patch(
            "backend.agents.nodes.evaluator._build_llm",
            return_value=_mock_llm_with_structured_output(eval_out),
        ), patch(
            "backend.agents.nodes.evaluator.get_policy_info",
            new_callable=AsyncMock,
            # Sin max_return_days/allowed_conditions: las reglas de plazo y
            # condición de policy_rules.py no vetan nada (ver docstring).
            return_value={"restocking_fee_percent": 0.0},
        ), patch(
            "backend.agents.nodes.evaluator.search_return_policy",
            new_callable=AsyncMock,
            return_value={"policy_info": {"restocking_fee_percent": 0.0}},
        ), patch(
            "backend.agents.nodes.resolution._build_llm",
            return_value=_mock_llm_freeform(resolve_response),
        ), patch(
            "backend.agents.nodes.resolution.create_return_record",
            new_callable=AsyncMock,
            return_value={"return_request": {"id": "ret-1"}, "items_created": 1},
        ), patch(
            "backend.agents.nodes.resolution.generate_shipping_label",
            new_callable=AsyncMock,
            return_value=mock_label_result,
        ), patch(
            "backend.agents.nodes.resolution.update_return_status",
            new_callable=AsyncMock,
            return_value={"updated_return": {"id": "ret-1"}},
        ), patch(
            "backend.agents.nodes.resolution.send_customer_notification",
            new_callable=AsyncMock,
            return_value={"status": "sent_simulated"},
        ):
            config = {"configurable": {"thread_id": "test-flow-1"}}
            result = await graph.ainvoke(
                {
                    "messages": [
                        HumanMessage(
                            content="Sí, confirmo la devolución de los auriculares"
                        )
                    ],
                    "order_number": "ORD-2026-00123",
                    "reason": "Defectuoso",
                    "reason_category": "defective",
                    "items_to_return": [
                        {
                            "order_item_id": "oi-001-uuid",
                            "quantity": 1,
                            "condition": "defective",
                        }
                    ],
                    "thread_id": "test-flow-1",
                },
                config=config,
            )

        assert result.get("resolution") == "approved"
        assert result.get("tracking_number") == "RF-ABC1234567"

    @pytest.mark.asyncio
    async def test_not_eligible_gets_rejected(
        self, mock_order_details, mock_return_history_clean
    ):
        """Flujo completo: devolución no elegible → rechazo empático."""
        graph = await build_return_graph()

        triage_out = TriageOutput(
            response_to_customer="Entendido, reviso tu solicitud.",
            items_confirmed=True,
        )
        eval_out = PolicyEvaluationOutput(
            items=[
                ItemEligibility(
                    order_item_id="oi-001-uuid",
                    is_eligible=False,
                    eligibility_reason="Producto usado; cambio de opinión fuera de plazo.",
                    refund_amount=0.0,
                    policy_category="electronics",
                ),
            ]
        )
        reject_response = AIMessage(
            content="Lamentamos informarte que no podemos procesar tu devolución..."
        )

        with patch(
            "backend.agents.nodes.triage._build_llm",
            return_value=_mock_llm_with_structured_output(triage_out),
        ), patch(
            "backend.agents.nodes.triage.get_order_details",
            new_callable=AsyncMock,
            return_value=mock_order_details,
        ), patch(
            "backend.agents.nodes.triage.get_customer_return_history",
            new_callable=AsyncMock,
            return_value=mock_return_history_clean,
        ), patch(
            "backend.agents.nodes.evaluator._build_llm",
            return_value=_mock_llm_with_structured_output(eval_out),
        ), patch(
            "backend.agents.nodes.evaluator.get_policy_info",
            new_callable=AsyncMock,
            return_value={"restocking_fee_percent": 0.0},
        ), patch(
            "backend.agents.nodes.evaluator.search_return_policy",
            new_callable=AsyncMock,
            return_value={"policy_info": {"restocking_fee_percent": 0.0}},
        ), patch(
            "backend.agents.nodes.resolution._build_llm",
            return_value=_mock_llm_freeform(reject_response),
        ):
            config = {"configurable": {"thread_id": "test-flow-2"}}
            result = await graph.ainvoke(
                {
                    "messages": [HumanMessage(content="Sí, confirmo, ya no lo quiero")],
                    "order_number": "ORD-2026-00123",
                    "reason": "Ya no lo quiero",
                    "reason_category": "no_longer_needed",
                    "items_to_return": [
                        {
                            "order_item_id": "oi-001-uuid",
                            "quantity": 1,
                            "condition": "used",
                        }
                    ],
                    "thread_id": "test-flow-2",
                },
                config=config,
            )

        assert result.get("resolution") == "rejected"
        assert result.get("tracking_number") is None
