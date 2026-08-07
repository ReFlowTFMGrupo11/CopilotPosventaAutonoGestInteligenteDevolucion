"""Modelos Pydantic compartidos entre capas (MCP, agentes, API)."""

# Re-exporta los modelos de dominio (pedidos, artículos, salida del triaje)...
from backend.models.returns import OrderItem, Product, ReturnItem, ShippingLabelItem, TriageOutput
# ...y el estado del grafo, para que ambos se puedan importar con
# "from backend.models import X" sin saber en qué submódulo viven realmente.
from backend.models.state import ReturnState

# __all__: fija explícitamente qué nombres exporta este paquete al hacer
# "from backend.models import *" (y sirve de documentación del API público).
__all__ = ["OrderItem", "Product", "ReturnItem", "ShippingLabelItem", "TriageOutput", "ReturnState"]
