"""Tests unitarios para las reglas de negocio deterministas del evaluador.

backend/agents/nodes/policy_rules.py es código puro Python (sin LLM, sin
MCP, sin BD), pensado para testearse en aislamiento total. Antes de este
fichero no tenía ningún test.
"""

from backend.agents.nodes.policy_rules import (
    compute_refund,
    deterministic_check,
)


class TestDeterministicCheck:
    """Tests de la cadena de reglas orquestada por deterministic_check()."""

    def test_valid_within_deadline_and_allowed_condition(self):
        """Verifica que un caso dentro de plazo y con condición permitida da veredicto 'valid'."""
        verdict, reasons = deterministic_check(
            days_since_order=10,
            max_return_days=30,
            allowed_conditions=["unopened", "defective", "wrong_item"],
            condition="defective",
            category="electronics",
            reason_category="defective",
            refund_amount=50.0,
            approved_returns=0,
        )
        assert verdict == "valid"
        assert reasons == []

    def test_invalid_when_deadline_exceeded_beyond_grace_period(self):
        """> max_return_days + 5 días es un veto absoluto, no revisión."""
        verdict, reasons = deterministic_check(
            days_since_order=40,
            max_return_days=30,
            allowed_conditions=["unopened", "defective", "wrong_item"],
            condition="defective",
            category="electronics",
            reason_category="defective",
            refund_amount=50.0,
            approved_returns=0,
        )
        assert verdict == "invalid"
        assert "Plazo superado" in reasons[0]

    def test_human_review_when_deadline_in_grace_period(self):
        """Dentro del margen de gracia (max_days-2 .. max_days+5): revisión, no veto."""
        verdict, reasons = deterministic_check(
            days_since_order=33,
            max_return_days=30,
            allowed_conditions=["unopened", "defective", "wrong_item"],
            condition="defective",
            category="electronics",
            reason_category="defective",
            refund_amount=50.0,
            approved_returns=0,
        )
        assert verdict == "human_review"
        assert any("zona frontera" in r for r in reasons)

    def test_invalid_hygiene_exclusion_changed_mind_regardless_of_condition(self):
        """Categoría de higiene + motivo de 'cambio de opinión' -> veto legal
        SIEMPRE, incluso si el artículo está unopened (el derecho de
        desistimiento no aplica a estas categorías, no solo el precinto)."""
        for condition in ("used", "unopened", "defective"):
            verdict, reasons = deterministic_check(
                days_since_order=5,
                max_return_days=21,
                allowed_conditions=["unopened", "defective", "wrong_item"],
                condition=condition,
                category="cosmetica_perfumeria",
                reason_category="no_longer_needed",
                refund_amount=30.0,
                approved_returns=0,
            )
            assert verdict == "invalid", f"condition={condition} debería vetarse igual"
            assert "cambio de opinión" in reasons[0]

    def test_valid_hygiene_category_but_mercadia_fault(self):
        """Misma categoría de higiene, pero el motivo SÍ es imputable a
        Mercadia (defective) -> la exclusión de higiene no aplica."""
        verdict, reasons = deterministic_check(
            days_since_order=5,
            max_return_days=21,
            allowed_conditions=["unopened", "defective", "wrong_item"],
            condition="used",
            category="cosmetica_perfumeria",
            reason_category="defective",
            refund_amount=30.0,
            approved_returns=0,
        )
        assert verdict == "valid"

    def test_valid_hygiene_category_wrong_item_is_mercadia_fault(self):
        """Categoría de higiene + 'wrong_item' (fallo de Mercadia, no cambio
        de opinión del cliente) -> no hay exclusión de higiene."""
        verdict, _ = deterministic_check(
            days_since_order=5,
            max_return_days=21,
            allowed_conditions=["unopened", "defective", "wrong_item"],
            condition="unopened",
            category="cosmetica_perfumeria",
            reason_category="wrong_item",
            refund_amount=30.0,
            approved_returns=0,
        )
        assert verdict == "valid"

    def test_condition_allowed_bypass_for_damaged_and_used(self):
        """'damaged'/'used' nunca aparecen literalmente en ningún
        allowed_conditions real (ver data/generate_dataset.py) -> deben
        quedar exentos de esta comprobación en vez de rechazarse siempre."""
        for condition in ("damaged", "used"):
            verdict, _ = deterministic_check(
                days_since_order=5,
                max_return_days=30,
                allowed_conditions=["unopened", "defective", "wrong_item"],
                condition=condition,
                category="electronics",  # no es categoría de higiene
                reason_category="defective",
                refund_amount=30.0,
                approved_returns=0,
            )
            assert verdict == "valid", f"condition={condition} debería pasar el bypass"

    def test_invalid_condition_not_allowed_and_not_mercadia_fault(self):
        """Verifica que una condición sí permitida ('wrong_item') no veta el caso aunque el motivo sea 'other'."""
        verdict, reasons = deterministic_check(
            days_since_order=5,
            max_return_days=30,
            allowed_conditions=["unopened", "defective", "wrong_item"],
            condition="wrong_item",  # sí está permitida
            category="fashion",
            reason_category="other",
            refund_amount=30.0,
            approved_returns=0,
        )
        assert verdict == "valid"

    def test_human_review_high_amount(self):
        """Verifica que un reembolso por encima del umbral (100€) fuerza revisión humana."""
        verdict, reasons = deterministic_check(
            days_since_order=5,
            max_return_days=30,
            allowed_conditions=["unopened", "defective", "wrong_item"],
            condition="defective",
            category="electronics",
            reason_category="defective",
            refund_amount=150.0,
            approved_returns=0,
        )
        assert verdict == "human_review"
        assert any("100" in r or "umbral" in r for r in reasons)

    def test_human_review_frequent_returner(self):
        """Verifica que un cliente con muchas devoluciones aprobadas fuerza revisión humana por posible abuso."""
        verdict, reasons = deterministic_check(
            days_since_order=5,
            max_return_days=30,
            allowed_conditions=["unopened", "defective", "wrong_item"],
            condition="defective",
            category="electronics",
            reason_category="defective",
            refund_amount=20.0,
            approved_returns=6,
        )
        assert verdict == "human_review"
        assert any("abuso" in r for r in reasons)

    def test_no_max_return_days_never_blocks_on_deadline(self):
        """max_return_days=None (categoría sin política cargada) no debe
        vetar por plazo; el resto de reglas siguen aplicando igual."""
        verdict, _ = deterministic_check(
            days_since_order=9999,
            max_return_days=None,
            allowed_conditions=None,
            condition="defective",
            category="unknown",
            reason_category="defective",
            refund_amount=10.0,
            approved_returns=0,
        )
        assert verdict == "valid"


class TestComputeRefund:
    """Tests del cálculo determinista del importe de reembolso."""

    ORDER_ITEMS = [
        {"id": "oi-1", "unit_price": 79.99},
        {"id": "oi-2", "unit_price": 15.00},
    ]

    def test_single_item_no_restocking_fee(self):
        """Verifica que sin recargo de reposición el reembolso es igual al precio unitario."""
        refund = compute_refund(
            self.ORDER_ITEMS,
            [{"order_item_id": "oi-1", "quantity": 1}],
            restocking_fee_percent=0,
        )
        assert refund == 79.99

    def test_applies_restocking_fee_percent(self):
        """Verifica que el recargo de reposición se descuenta del reembolso, redondeado a 2 decimales."""
        refund = compute_refund(
            self.ORDER_ITEMS,
            [{"order_item_id": "oi-1", "quantity": 1}],
            restocking_fee_percent=10,
        )
        assert refund == 71.99  # 79.99 * 0.9, redondeado a 2 decimales

    def test_multiplies_by_quantity(self):
        """Verifica que el reembolso se multiplica por la cantidad de unidades devueltas."""
        refund = compute_refund(
            self.ORDER_ITEMS,
            [{"order_item_id": "oi-2", "quantity": 2}],
            restocking_fee_percent=0,
        )
        assert refund == 30.00

    def test_ignores_items_not_in_order(self):
        """Un order_item_id que no está en el pedido no debe romper el cálculo."""
        refund = compute_refund(
            self.ORDER_ITEMS,
            [{"order_item_id": "oi-does-not-exist", "quantity": 1}],
            restocking_fee_percent=0,
        )
        assert refund == 0.0
