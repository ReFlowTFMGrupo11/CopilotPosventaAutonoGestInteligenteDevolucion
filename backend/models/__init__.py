"""Modelos Pydantic compartidos entre capas (MCP, agentes, API)."""

from backend.models.returns import ReturnItem, ShippingLabelItem, TriageOutput
from backend.models.state import ReturnState

__all__ = ["ReturnItem", "ShippingLabelItem", "TriageOutput", "ReturnState"]
