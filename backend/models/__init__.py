"""Modelos Pydantic compartidos entre capas (MCP, agentes, API)."""

from backend.models.returns import (
    ItemEligibility,
    OrderItem,
    PolicyEvaluationOutput,
    Product,
    ReturnItem,
    ShippingLabelItem,
    TriageOutput,
)
from backend.models.state import ReturnState

__all__ = [
    "OrderItem",
    "Product",
    "ReturnItem",
    "ShippingLabelItem",
    "TriageOutput",
    "ItemEligibility",
    "PolicyEvaluationOutput",
    "ReturnState",
]
