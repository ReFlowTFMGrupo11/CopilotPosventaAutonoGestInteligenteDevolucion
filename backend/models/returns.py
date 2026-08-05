"""Modelos de dominio para devoluciones y logística.

Estos modelos se comparten entre:
- backend/mcp/ (tools MCP que el LLM invoca en modo strict)
- backend/agents/nodes/ (structured output del triaje)
- Futuros endpoints FastAPI

Centralizarlos aquí evita duplicación y garantiza un único schema.
"""

from pydantic import BaseModel, Field


class ReturnItem(BaseModel):
    """Artículo incluido en una solicitud de devolución.

    Usado tanto por las tools MCP (donde el LLM en modo strict necesita
    un JSON Schema fijo) como por el structured output del agente de triaje.
    """

    order_item_id: str = Field(description="UUID del order_item a devolver.")
    quantity: int = Field(default=1, description="Unidades a devolver.")
    condition: str = Field(
        default="unknown",
        description="Estado del artículo: unopened, defective, damaged, used, wrong_item.",
    )


class ShippingLabelItem(BaseModel):
    """Artículo mostrado en la etiqueta de transporte generada.

    Usado por la tool MCP generate_shipping_label y por el agente de resolución.
    """

    name: str = Field(default="Item", description="Nombre del producto.")
    quantity: int = Field(default=1, description="Unidades del producto.")
