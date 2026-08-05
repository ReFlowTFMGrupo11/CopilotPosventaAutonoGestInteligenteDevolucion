"""Modelos Pydantic compartidos entre capas (MCP, agentes, API)."""

from backend.models.returns import ReturnItem, ShippingLabelItem, TriageOutput

__all__ = ["ReturnItem", "ShippingLabelItem", "TriageOutput"]
