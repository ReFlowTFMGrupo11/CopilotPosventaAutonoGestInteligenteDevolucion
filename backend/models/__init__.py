"""Modelos Pydantic compartidos entre capas (MCP, agentes, API)."""

from backend.models.returns import ReturnItem, ShippingLabelItem

__all__ = ["ReturnItem", "ShippingLabelItem"]
