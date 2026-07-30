"""Tests unitarios para las funciones de routing del grafo."""

import pytest

from backend.agents.graph import route_after_triage, route_after_fetch, route_after_evaluator


class TestRouteAfterTriage:
    """Tests para la decisión de routing post-triaje."""

    def test_advances_when_order_id_and_items_present(self):
        state = {
            "order_id": "ord-001",
            "items_to_return": [{"order_item_id": "oi-1", "quantity": 1}],
        }
        assert route_after_triage(state) == "fetch_order_data"

    def test_loops_back_when_no_order_id(self):
        state = {
            "order_id": None,
            "items_to_return": [{"order_item_id": "oi-1", "quantity": 1}],
        }
        assert route_after_triage(state) == "triage"

    def test_loops_back_when_no_items(self):
        state = {
            "order_id": "ord-001",
            "items_to_return": [],
        }
        assert route_after_triage(state) == "triage"

    def test_loops_back_when_both_missing(self):
        state = {}
        assert route_after_triage(state) == "triage"

    def test_loops_back_when_order_id_empty_string(self):
        state = {
            "order_id": "",
            "items_to_return": [{"order_item_id": "oi-1", "quantity": 1}],
        }
        assert route_after_triage(state) == "triage"


class TestRouteAfterFetch:
    """Tests para la decisión de routing post-fetch."""

    def test_advances_to_evaluator_when_no_error(self):
        state = {"error": None}
        assert route_after_fetch(state) == "evaluator"

    def test_advances_to_evaluator_when_no_error_key(self):
        state = {}
        assert route_after_fetch(state) == "evaluator"

    def test_returns_to_triage_on_error(self):
        state = {"error": "Pedido no encontrado"}
        assert route_after_fetch(state) == "triage"


class TestRouteAfterEvaluator:
    """Tests para la decisión de routing post-evaluador."""

    def test_routes_to_resolver_when_eligible(self):
        state = {"is_eligible": True}
        assert route_after_evaluator(state) == "resolver"

    def test_routes_to_reject_when_not_eligible(self):
        state = {"is_eligible": False}
        assert route_after_evaluator(state) == "reject"

    def test_routes_to_reject_when_none(self):
        state = {"is_eligible": None}
        assert route_after_evaluator(state) == "reject"

    def test_routes_to_reject_when_missing(self):
        state = {}
        assert route_after_evaluator(state) == "reject"
