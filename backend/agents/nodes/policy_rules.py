"""
Reglas de negocio deterministas para el evaluador de políticas.

Patrón "Chain of Rules": cada regla es una función pura que recibe un
contexto inmutable (PolicyContext) y devuelve un veredicto parcial
(RuleResult). Se evalúan en orden; el primer "invalid" es un veto
absoluto. Los "human_review" se acumulan.

Este módulo es código puro Python — no depende de LangChain, OpenAI,
ni ningún servicio externo. Se puede testear unitariamente en
aislamiento total.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 VOCABULARIO: alineado con el enum EN VIVO de triage.py, NO con el
 dataset sintético (data/generate_dataset.py) ni con las políticas RAG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 `condition` (5 valores, ver TriageOutput/ReturnItem):
   unopened, defective, damaged, used, wrong_item

 `reason_category` (6 valores, ver TriageOutput):
   defective, wrong_item, not_as_described, no_longer_needed,
   arrived_late, other

 data/generate_dataset.py usa un vocabulario mucho más granular (15
 reason_category, 9 condition) para generar el golden dataset de QA
 (dataset/qa/eval_cases.csv) y las políticas RAG en data/rag/policies/.
 Ese vocabulario NUNCA llega a producción: triage.py solo extrae los
 valores de arriba de la conversación real con el cliente. Las
 constantes de este módulo están alineadas con lo que triage.py
 produce de verdad, no con el dataset — de lo contrario reglas como
 rule_hygiene/rule_condition_allowed rechazarían casos válidos por
 buscar valores (p. ej. "opened_tested", "wrong_item_shipped") que el
 LLM de triaje nunca genera.

 Limitación conocida: `reason_category` es ÚNICO por solicitud completa
 en ReturnState (no por artículo). En un pedido con varios artículos y
 motivos distintos, el bypass de MERCADIA_FAULT_REASONS en rule_hygiene
 usa el motivo agregado de la solicitud, no el de cada artículo — puede
 dar un falso negativo (no vetar higiene) si un artículo del mismo
 turno es defectuoso y otro es "cambié de opinión". Arreglarlo requiere
 capturar reason_category por artículo en triage.py (fuera de alcance
 de este módulo).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.config import get_settings

# ── Constantes de negocio ──────────────────────────────────────────────────
#
# HITL_REFUND_THRESHOLD (umbral de importe a partir del cual se requiere
# aprobación manual) vive en Settings.hitl_threshold_eur (backend/config.py,
# env var HITL_THRESHOLD_EUR), no como constante de módulo: antes estaba
# duplicado aquí Y en resolution.py con el mismo valor (100.0) hardcodeado,
# y aunque .env.example ya documentaba HITL_THRESHOLD_EUR como configurable,
# cambiarlo no tenía ningún efecto real. get_settings() no hace I/O (solo
# parsea env vars con default), así que este módulo sigue siendo testable
# sin mocks.

SENSITIVE_REASONS: set[str] = set()
"""Vacío a propósito: el reason_category de 6 valores que triage.py
produce hoy no distingue motivos "sensibles" (alergia, sospecha de
falsificación...) de un "other" genérico. rule_sensitive_reason queda
definida pero excluida de POLICY_RULES hasta que triage.py capture esa
granularidad; ver docstring del módulo."""

HYGIENE_CATEGORIES = {
    "cosmetica_perfumeria",
    "drogueria_salud",
    "alimentacion",
    "mascotas",
    "bebe_puericultura",
}
"""Categorías con exclusión legal de devolución por higiene."""

MERCADIA_FAULT_REASONS = {"defective", "wrong_item", "not_as_described"}
"""Motivos imputables a Mercadia (anulan exclusiones del cliente).

Alineado con el reason_category de 6 valores de triage.py (ver
docstring del módulo) — no con el vocabulario más granular de
data/generate_dataset.py (wrong_item_shipped, damaged_in_transit,
missing_parts), que triage.py nunca produce en vivo."""

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
    # Producto usado en categoría de higiene → exclusión legal.
    # (Del enum de 5 valores de triage.py, solo "used" implica precinto/uso
    # roto por decisión del cliente; "unopened"/"defective"/"damaged"/
    # "wrong_item" no indican manipulación voluntaria del producto.)
    #
    # NOTA: con el reason_category de 6 valores actual, MERCADIA_FAULT_REASONS
    # ∪ NO_RETURN_BY_CHOICE_REASONS cubre las 6 categorías posibles — este
    # bloque es hoy inalcanzable (una de las dos ramas de arriba siempre
    # decide antes de llegar aquí). Se deja como red de seguridad explícita
    # para si el reason_category se amplía en el futuro (ver docstring del
    # módulo); no se elimina porque documenta la intención de la regla.
    if ctx.condition == "used":
        return RuleResult(
            "invalid",
            f"Precinto/uso roto ('{ctx.condition}') en categoría con exclusión "
            f"legal de higiene y motivo '{ctx.reason_category}' no imputable a Mercadia.",
        )
    return RuleResult("valid")


def rule_condition_allowed(ctx: PolicyContext) -> RuleResult:
    """Rechaza si el estado del producto no está en las condiciones permitidas.

    `allowed_conditions` viene de `return_policies` (poblada por
    data/generate_dataset.py con su vocabulario granular: "opened_tested",
    "damaged_in_transit"...). El "condition" que triage.py extrae en vivo
    usa el enum de 5 valores y nunca coincidirá literalmente con esos
    arrays para "damaged"/"used" — ningún array de ninguna categoría los
    contiene tal cual. data/generate_dataset.py::classify_case ya trata
    "damaged" y "used" como exentos de esta comprobación por el mismo
    motivo; replicamos ese mismo bypass aquí en vez de inventar uno nuevo.
    """
    if ctx.condition in {"damaged", "used"}:
        return RuleResult("valid")
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
    threshold = get_settings().hitl_threshold_eur
    if ctx.refund_amount > threshold:
        return RuleResult(
            "human_review",
            f"Importe {ctx.refund_amount:.2f}€ supera el umbral de "
            f"{threshold:.2f}€.",
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
    # rule_sensitive_reason excluida a propósito: SENSITIVE_REASONS está
    # vacío porque el reason_category de 6 valores de triage.py no
    # distingue motivos sensibles. Ver docstring del módulo.
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
