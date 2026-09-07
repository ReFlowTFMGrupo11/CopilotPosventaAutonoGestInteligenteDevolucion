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
        """Verifica que con order_number e items_to_return presentes se avanza a fetch_order_data."""
        state = {
            "order_number": "ORD-2026-00001",
            "order_details": {"items": [{"id": "oi-1"}]},
            "items_to_return": [{"order_item_id": "oi-1", "quantity": 1}],
        }
        assert route_after_triage(state) == "fetch_order_data"

    def test_ends_when_no_order_number(self):
        """Verifica que sin order_number el turno termina para seguir pidiendo datos."""
        state = {
            "order_number": None,
            "items_to_return": [{"order_item_id": "oi-1", "quantity": 1}],
        }
        assert route_after_triage(state) == "__end__"

    def test_advances_when_order_details_missing(self):
        """Verifica que con order_number pero sin order_details aún se avanza a fetch_order_data."""
        state = {
            "order_number": "ORD-2026-00001",
            "order_details": None,
            "items_to_return": [],
        }
        assert route_after_triage(state) == "fetch_order_data"

    def test_ends_when_order_present_but_no_items_selected_yet(self):
        """Verifica que sin artículos seleccionados el turno termina para pedirlos."""
        state = {
            "order_number": "ORD-2026-00001",
            "order_details": {"items": [{"id": "oi-1"}]},
            "items_to_return": [],
        }
        assert route_after_triage(state) == "__end__"

    def test_ends_when_both_missing(self):
        """Verifica que sin order_number ni items_to_return el turno termina."""
        state = {}
        assert route_after_triage(state) == "__end__"

    def test_ends_when_order_number_empty_string(self):
        """Verifica que un order_number vacío ('') se trata igual que ausente."""
        state = {
            "order_number": "",
            "items_to_return": [{"order_item_id": "oi-1", "quantity": 1}],
        }
        assert route_after_triage(state) == "__end__"


class TestRouteAfterFetch:
    """Tests para la decisión de routing post-fetch."""

    def test_advances_to_evaluator_when_no_error_and_items_present(self):
        """Verifica que sin error, con datos completos y confirmados se avanza a evaluator."""
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
        """Verifica que sin items_to_return el turno termina aunque no haya error."""
        state = {"error": None}
        assert route_after_fetch(state) == "__end__"

    def test_ends_when_condition_is_unknown(self):
        """Verifica que una condición de artículo 'unknown' hace terminar el turno para aclararla."""
        state = {
            "error": None,
            "items_to_return": [{"order_item_id": "oi-1", "condition": "unknown"}],
            "reason": "No lo necesito",
            "reason_category": "no_longer_needed",
        }
        assert route_after_fetch(state) == "__end__"

    def test_ends_when_reason_data_missing(self):
        """Verifica que sin reason/reason_category el turno termina para pedirlos."""
        state = {
            "error": None,
            "items_to_return": [{"order_item_id": "oi-1", "condition": "unopened"}],
            "reason": "",
            "reason_category": "",
        }
        assert route_after_fetch(state) == "__end__"

    def test_ends_on_error(self):
        """Verifica que un error en el estado hace terminar el turno inmediatamente."""
        state = {"error": "Pedido no encontrado"}
        assert route_after_fetch(state) == "__end__"


class TestRouteAfterEvaluator:
    """Tests para la decisión de routing post-evaluador."""

    def test_routes_to_resolver_when_eligible(self):
        """Verifica que any_eligible=True enruta hacia resolver."""
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
        """Verifica que any_eligible=False enruta hacia reject."""
        state = {"any_eligible": False}
        assert route_after_evaluator(state) == "reject"

    def test_routes_to_reject_when_none(self):
        """Verifica que any_eligible=None enruta hacia reject."""
        state = {"any_eligible": None}
        assert route_after_evaluator(state) == "reject"

    def test_routes_to_reject_when_missing(self):
        """Verifica que la ausencia de any_eligible en el estado enruta hacia reject."""
        state = {}
        assert route_after_evaluator(state) == "reject"
