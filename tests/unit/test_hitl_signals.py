"""Tests unitarios para las señales deterministas de HITL (resolution.py).

dataset/policies/00_marco_general_devoluciones.md, sección 5: estas son las
señales que, con independencia de la elegibilidad, obligan a revisión
humana. Se prueban aquí como funciones puras, sin mockear LLM ni MCP.
"""

from datetime import datetime, timedelta, timezone

from backend.agents.nodes.resolution import (
    _needs_admin_approval,
    _recent_approved_returns_count,
)


class TestRecentApprovedReturnsCount:
    """Tests para el conteo de devoluciones aprobadas recientes."""

    def test_counts_only_approved_within_window(self):
        now = datetime.now(timezone.utc)
        return_history = {
            "returns": [
                {"status": "approved", "created_at": (now - timedelta(days=10)).isoformat()},
                # Fuera de la ventana de 90 días: no cuenta.
                {"status": "approved", "created_at": (now - timedelta(days=95)).isoformat()},
                # Rechazada: no cuenta aunque esté dentro de la ventana.
                {"status": "rejected", "created_at": (now - timedelta(days=5)).isoformat()},
                {"status": "approved", "created_at": (now - timedelta(days=1)).isoformat()},
            ]
        }
        assert _recent_approved_returns_count(return_history, 90) == 2

    def test_empty_history_returns_zero(self):
        assert _recent_approved_returns_count({}, 90) == 0
        assert _recent_approved_returns_count({"returns": []}, 90) == 0

    def test_ignores_entries_without_created_at(self):
        return_history = {"returns": [{"status": "approved"}]}
        assert _recent_approved_returns_count(return_history, 90) == 0

    def test_handles_z_suffix(self):
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return_history = {"returns": [{"status": "approved", "created_at": recent}]}
        assert _recent_approved_returns_count(return_history, 90) == 1


class TestNeedsAdminApproval:
    """Tests para la decisión combinada de HITL (varias señales acumulables)."""

    def test_no_signals_returns_false(self):
        state = {"refund_amount": 20.0, "reason_category": "defective"}
        needs, reasons = _needs_admin_approval(state)
        assert needs is False
        assert reasons == []

    def test_refund_above_threshold(self):
        state = {"refund_amount": 150.0}
        needs, reasons = _needs_admin_approval(state)
        assert needs is True
        assert any("importe" in r for r in reasons)

    def test_refund_exactly_at_threshold_does_not_trigger(self):
        """100.00€ exactos no supera el umbral (es "<=", no "<")."""
        state = {"refund_amount": 100.0}
        needs, reasons = _needs_admin_approval(state)
        assert needs is False

    def test_sensitive_reason_category_allergic_reaction(self):
        state = {"refund_amount": 10.0, "reason_category": "allergic_reaction"}
        needs, reasons = _needs_admin_approval(state)
        assert needs is True
        assert any("motivo sensible" in r for r in reasons)

    def test_sensitive_reason_category_counterfeit_suspicion(self):
        state = {"refund_amount": 10.0, "reason_category": "counterfeit_suspicion"}
        needs, reasons = _needs_admin_approval(state)
        assert needs is True
        assert any("motivo sensible" in r for r in reasons)

    def test_boundary_zone_before_deadline(self):
        """Día 28 de una política de 30 días: dentro de la zona frontera."""
        state = {
            "refund_amount": 10.0,
            "days_since_delivery": 28,
            "policy_max_return_days": 30,
        }
        needs, reasons = _needs_admin_approval(state)
        assert needs is True
        assert any("zona frontera" in r for r in reasons)

    def test_boundary_zone_just_after_deadline(self):
        """Día 31 de una política de 30 días: sigue en zona frontera (diferencia +1)."""
        state = {
            "refund_amount": 10.0,
            "days_since_delivery": 31,
            "policy_max_return_days": 30,
        }
        needs, reasons = _needs_admin_approval(state)
        assert needs is True

    def test_not_boundary_zone_when_far_from_deadline(self):
        state = {
            "refund_amount": 10.0,
            "days_since_delivery": 5,
            "policy_max_return_days": 30,
        }
        needs, reasons = _needs_admin_approval(state)
        assert needs is False

    def test_boundary_zone_skipped_when_data_missing(self):
        """Sin days_since_delivery/policy_max_return_days no se puede evaluar
        la zona frontera: se omite la señal en vez de fallar."""
        state = {"refund_amount": 10.0}
        needs, reasons = _needs_admin_approval(state)
        assert needs is False
        assert reasons == []

    def test_frequent_returner_triggers_hitl(self):
        now = datetime.now(timezone.utc)
        state = {
            "refund_amount": 10.0,
            "return_history": {
                "returns": [
                    {"status": "approved", "created_at": (now - timedelta(days=d)).isoformat()}
                    for d in (1, 2, 3, 4)
                ]
            },
        }
        needs, reasons = _needs_admin_approval(state)
        assert needs is True
        assert any("posible abuso" in r for r in reasons)

    def test_three_recent_approved_does_not_trigger(self):
        """El umbral es "más de 3", así que exactamente 3 no dispara HITL."""
        now = datetime.now(timezone.utc)
        state = {
            "refund_amount": 10.0,
            "return_history": {
                "returns": [
                    {"status": "approved", "created_at": (now - timedelta(days=d)).isoformat()}
                    for d in (1, 2, 3)
                ]
            },
        }
        needs, reasons = _needs_admin_approval(state)
        assert needs is False

    def test_multiple_signals_accumulate(self):
        """Varias señales a la vez: todas deben quedar reflejadas en las razones."""
        state = {
            "refund_amount": 150.0,
            "reason_category": "counterfeit_suspicion",
        }
        needs, reasons = _needs_admin_approval(state)
        assert needs is True
        assert len(reasons) == 2
