"""Modelos Pydantic compartidos entre capas (MCP, agentes, API)."""

from backend.models.returns import OrderItem, Product, ReturnItem, ShippingLabelItem, TriageOutput
from backend.models.state import ReturnState

__all__ = ["OrderItem", "Product", "ReturnItem", "ShippingLabelItem", "TriageOutput", "ReturnState"]
