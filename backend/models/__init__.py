"""Modelos Pydantic compartidos entre capas (MCP, agentes, API).

ReturnState no se re-exporta desde aquí: necesita langchain_core y langgraph,
ausentes en la imagen Docker de los MCP servers. Los agentes la importan
directamente desde backend.models.state para no arrastrar esa dependencia
a la imagen MCP.
"""

from backend.models.returns import (
    ItemEligibility,
    OrderItem,
    PolicyEvaluationOutput,
    Product,
    ReturnItem,
    ShippingLabelItem,
    TriageOutput,
)

__all__ = [
    "OrderItem",
    "Product",
    "ReturnItem",
    "ShippingLabelItem",
    "TriageOutput",
    "ItemEligibility",
    "PolicyEvaluationOutput",
]
