"""Tests unitarios para las funciones de routing del grafo."""

import pytest

from backend.agents.graph import (
    route_after_triage,
    route_after_fetch,
    route_after_evaluator,
)


class TestRouteAfterTriage:
    """Tests para la decisión de routing post-triaje."""

    def test_advances_when_order_number_and_items_present(self):
        state = {
            "order_number": "ORD-2026-00001",
            "order_details": {"items": [{"id": "oi-1"}]},
            "items_to_return": [{"order_item_id": "oi-1", "quantity": 1}],
        }
        assert route_after_triage(state) == "fetch_order_data"

    def test_ends_when_no_order_number(self):
        state = {
            "order_number": None,
            "items_to_return": [{"order_item_id": "oi-1", "quantity": 1}],
        }
        assert route_after_triage(state) == "__end__"

    def test_advances_when_order_details_missing(self):
        state = {
            "order_number": "ORD-2026-00001",
            "order_details": None,
            "items_to_return": [],
        }
        assert route_after_triage(state) == "fetch_order_data"

    def test_ends_when_order_present_but_no_items_selected_yet(self):
        state = {
            "order_number": "ORD-2026-00001",
            "order_details": {"items": [{"id": "oi-1"}]},
            "items_to_return": [],
        }
        assert route_after_triage(state) == "__end__"

    def test_ends_when_both_missing(self):
        state = {}
        assert route_after_triage(state) == "__end__"

    def test_ends_when_order_number_empty_string(self):
        state = {
            "order_number": "",
            "items_to_return": [{"order_item_id": "oi-1", "quantity": 1}],
        }
        assert route_after_triage(state) == "__end__"


class TestRouteAfterFetch:
    """Tests para la decisión de routing post-fetch."""

    def test_advances_to_evaluator_when_no_error_and_items_present(self):
        state = {
            "error": None,
            "items_to_return": [{"order_item_id": "oi-1", "condition": "defective"}],
            "reason": "Llegó roto",
            "reason_category": "defective",
            # El cliente ya confirmó el resumen (ver triage.py::_items_confirmed);
            # sin esto, route_after_fetch termina el turno para pedir confirmación
            # en vez de avanzar, aunque el resto de datos ya estén completos.
            "items_confirmed": True,
        }
        assert route_after_fetch(state) == "evaluator"

    def test_ends_when_no_error_but_items_missing(self):
        state = {"error": None}
        assert route_after_fetch(state) == "__end__"

    def test_ends_when_condition_is_unknown(self):
        state = {
            "error": None,
            "items_to_return": [{"order_item_id": "oi-1", "condition": "unknown"}],
            "reason": "No lo necesito",
            "reason_category": "no_longer_needed",
        }
        assert route_after_fetch(state) == "__end__"

    def test_ends_when_reason_data_missing(self):
        state = {
            "error": None,
            "items_to_return": [{"order_item_id": "oi-1", "condition": "unopened"}],
            "reason": "",
            "reason_category": "",
        }
        assert route_after_fetch(state) == "__end__"

    def test_ends_on_error(self):
        state = {"error": "Pedido no encontrado"}
        assert route_after_fetch(state) == "__end__"


class TestRouteAfterEvaluator:
    """Tests para la decisión de routing post-evaluador."""

    def test_routes_to_resolver_when_eligible(self):
        state = {"any_eligible": True}
        assert route_after_evaluator(state) == "resolver"

    def test_routes_to_resolver_when_mixed_eligibility(self):
        """Basta con que UN artículo sea elegible para avanzar a resolver."""
        state = {
            "any_eligible": True,
            "items_eligibility": [
                {"order_item_id": "oi-1", "is_eligible": True},
                {"order_item_id": "oi-2", "is_eligible": False},
            ],
        }
        assert route_after_evaluator(state) == "resolver"

    def test_routes_to_reject_when_not_eligible(self):
        state = {"any_eligible": False}
        assert route_after_evaluator(state) == "reject"

    def test_routes_to_reject_when_none(self):
        state = {"any_eligible": None}
        assert route_after_evaluator(state) == "reject"

    def test_routes_to_reject_when_missing(self):
        state = {}
        assert route_after_evaluator(state) == "reject"
