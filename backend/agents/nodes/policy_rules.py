"""
Reglas de negocio deterministas para el evaluador de políticas.

Patrón "Chain of Rules": cada regla es una función pura que recibe un
contexto inmutable (PolicyContext) y devuelve un veredicto parcial
(RuleResult). Se evalúan en orden; el primer "invalid" es un veto
absoluto. Los "human_review" se acumulan.

Este módulo es código puro Python — no depende de LangChain, OpenAI,
ni ningún servicio externo. Se puede testear unitariamente en
aislamiento total.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# ── Constantes de negocio ──────────────────────────────────────────────────

HITL_REFUND_THRESHOLD = 100.0
"""Umbral de importe (€) a partir del cual se requiere aprobación manual."""

SENSITIVE_REASONS = {"allergic_reaction", "counterfeit_suspicion"}
"""Motivos que siempre requieren revisión humana."""

HYGIENE_CATEGORIES = {
    "cosmetica_perfumeria", "drogueria_salud", "alimentacion",
    "mascotas", "bebe_puericultura",
}
"""Categorías con exclusión legal de devolución por higiene."""

MERCADIA_FAULT_REASONS = {
    "defective", "damaged_in_transit", "wrong_item_shipped",
    "missing_parts", "not_as_described",
}
"""Motivos imputables a Mercadia (anulan exclusiones del cliente)."""

FREQUENT_RETURNER_THRESHOLD = 5
"""Número de devoluciones aprobadas a partir del cual se sospecha abuso."""

NO_RETURN_BY_CHOICE_REASONS = {"no_longer_needed", "arrived_late", "other"}
"""Motivos de 'cambio de opinión' que no aplican a categorías con exclusión legal."""


# ── Modelos de datos ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class PolicyContext:
    """Datos inmutables que cada regla necesita para evaluar.

    Se construye una vez por evaluación y se pasa a todas las reglas.
    """
    days_since_order: int
    max_return_days: int | None
    allowed_conditions: list[str] | None
    condition: str
    category: str
    reason_category: str
    refund_amount: float
    approved_returns: int


@dataclass
class RuleResult:
    """Resultado de una regla individual."""
    verdict: Literal["invalid", "human_review", "valid"]
    reason: str | None = None


# ── Reglas individuales (funciones puras, fácilmente testeables) ───────────


def rule_deadline(ctx: PolicyContext) -> RuleResult:
    """Rechaza si se superó el plazo máximo + margen de gracia (5 días)."""
    if ctx.max_return_days is None:
        return RuleResult("valid")
    if ctx.days_since_order > ctx.max_return_days + 5:
        return RuleResult(
            "invalid",
            f"Plazo superado: {ctx.days_since_order} días desde la entrega "
            f"(máximo {ctx.max_return_days}).",
        )
    return RuleResult("valid")


def rule_hygiene(ctx: PolicyContext) -> RuleResult:
    """Rechaza productos de higiene abiertos/usados (exclusión legal) o por cambio de opinión."""
    if ctx.category not in HYGIENE_CATEGORIES:
        return RuleResult("valid")
    if ctx.reason_category in MERCADIA_FAULT_REASONS:
        return RuleResult("valid")
    # Cambio de opinión en categoría con exclusión legal → siempre inválido
    if ctx.reason_category in NO_RETURN_BY_CHOICE_REASONS:
        return RuleResult(
            "invalid",
            f"Categoría '{ctx.category}' no admite devolución por cambio de opinión "
            f"('{ctx.reason_category}'). Solo se aceptan devoluciones por defecto, "
            f"artículo incorrecto o daño imputable a Mercadia.",
        )
    # Producto abierto/usado en categoría de higiene → exclusión legal
    if ctx.condition in {"opened_tested", "opened_unused", "used"}:
        return RuleResult(
            "invalid",
            f"Precinto/uso roto ('{ctx.condition}') en categoría con exclusión "
            f"legal de higiene y motivo '{ctx.reason_category}' no imputable a Mercadia.",
        )
    return RuleResult("valid")


def rule_condition_allowed(ctx: PolicyContext) -> RuleResult:
    """Rechaza si el estado del producto no está en las condiciones permitidas."""
    if (
        ctx.allowed_conditions
        and ctx.condition not in ctx.allowed_conditions
        and ctx.reason_category not in MERCADIA_FAULT_REASONS
    ):
        return RuleResult(
            "invalid",
            f"Estado '{ctx.condition}' no admitido para esta categoría "
            f"({ctx.allowed_conditions}).",
        )
    return RuleResult("valid")


def rule_high_amount(ctx: PolicyContext) -> RuleResult:
    """Marca para revisión humana si el importe supera el umbral HITL."""
    if ctx.refund_amount > HITL_REFUND_THRESHOLD:
        return RuleResult(
            "human_review",
            f"Importe {ctx.refund_amount:.2f}€ supera el umbral de "
            f"{HITL_REFUND_THRESHOLD:.2f}€.",
        )
    return RuleResult("valid")


def rule_deadline_borderline(ctx: PolicyContext) -> RuleResult:
    """Marca para revisión si la solicitud está en zona frontera del plazo."""
    if ctx.max_return_days is None:
        return RuleResult("valid")
    if ctx.max_return_days - 2 <= ctx.days_since_order <= ctx.max_return_days + 5:
        return RuleResult(
            "human_review",
            f"Solicitud en zona frontera del plazo "
            f"({ctx.days_since_order} de {ctx.max_return_days} días).",
        )
    return RuleResult("valid")


def rule_sensitive_reason(ctx: PolicyContext) -> RuleResult:
    """Marca para revisión si el motivo es sensible (alergia, falsificación)."""
    if ctx.reason_category in SENSITIVE_REASONS:
        return RuleResult(
            "human_review",
            f"Motivo sensible ('{ctx.reason_category}').",
        )
    return RuleResult("valid")


def rule_frequent_returner(ctx: PolicyContext) -> RuleResult:
    """Marca para revisión si el cliente tiene historial excesivo."""
    if ctx.approved_returns > FREQUENT_RETURNER_THRESHOLD:
        return RuleResult(
            "human_review",
            f"Cliente con {ctx.approved_returns} devoluciones aprobadas "
            f"(posible abuso).",
        )
    return RuleResult("valid")


# ── Cadena de reglas (orden importa: las de veto van primero) ──────────────

POLICY_RULES = [
    rule_deadline,
    rule_hygiene,
    rule_condition_allowed,
    rule_high_amount,
    rule_deadline_borderline,
    rule_sensitive_reason,
    rule_frequent_returner,
]


# ── Evaluador determinista (orquesta la cadena) ───────────────────────────

def deterministic_check(
    days_since_order: int,
    max_return_days: int | None,
    allowed_conditions: list[str] | None,
    condition: str,
    category: str,
    reason_category: str,
    refund_amount: float,
    approved_returns: int,
) -> tuple[str, list[str]]:
    """Aplica la cadena de reglas de negocio.

    Devuelve (veredicto, motivos):
      - "invalid"      → veto absoluto, primer fallo corta la cadena.
      - "human_review" → se acumulan todos los motivos de revisión.
      - "valid"        → ninguna regla objetó.
    """
    ctx = PolicyContext(
        days_since_order=days_since_order,
        max_return_days=max_return_days,
        allowed_conditions=allowed_conditions,
        condition=condition,
        category=category,
        reason_category=reason_category,
        refund_amount=refund_amount,
        approved_returns=approved_returns,
    )

    review_reasons: list[str] = []

    for rule in POLICY_RULES:
        result = rule(ctx)
        if result.verdict == "invalid":
            return "invalid", [result.reason or "Regla de negocio no cumplida."]
        if result.verdict == "human_review" and result.reason:
            review_reasons.append(result.reason)

    return ("human_review", review_reasons) if review_reasons else ("valid", [])


def compute_refund(
    order_items: list[dict],
    items_to_return: list[dict],
    restocking_fee_percent: float,
) -> float:
    """Calcula el importe exacto del reembolso a partir de las líneas del pedido.

    No se confía en que el LLM haga aritmética de dinero.
    Descuenta el recargo de reposición si aplica.
    """
    by_id = {item["id"]: item for item in order_items if item.get("id")}
    total = sum(
        by_id[item["order_item_id"]]["unit_price"] * item.get("quantity", 1)
        for item in items_to_return
        if item.get("order_item_id") in by_id
    )
    return round(total * (1 - restocking_fee_percent / 100), 2)
