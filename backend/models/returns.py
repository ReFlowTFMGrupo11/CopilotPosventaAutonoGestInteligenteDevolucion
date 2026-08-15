"""Modelos de dominio para devoluciones y logística.

Estos modelos se comparten entre:
- backend/mcp/ (tools MCP que el LLM invoca en modo strict)
- backend/agents/nodes/ (structured output del triaje)
- Futuros endpoints FastAPI

Centralizarlos aquí evita duplicación y garantiza un único schema.
"""

from typing import Optional

from pydantic import BaseModel, Field


# ── Modelos de catálogo / pedido ───────────────────────────────────────────


class Product(BaseModel):
    """Producto del catálogo, tal como lo devuelve Supabase (join en order_items)."""

    name: Optional[str] = Field(default=None, description="Nombre del producto.")
    sku: Optional[str] = Field(default=None, description="SKU único.")
    category: Optional[str] = Field(default=None, description="Categoría (electronics, moda, etc.).")
    price: Optional[float] = Field(default=None, description="Precio unitario en euros.")
    weight_kg: Optional[float] = Field(default=None, description="Peso en kg.")


class OrderItem(BaseModel):
    """Línea de un pedido (order_item + producto embebido)."""

    id: Optional[str] = Field(default=None, description="UUID del order_item.")
    order_id: Optional[str] = Field(default=None, description="UUID del pedido.")
    quantity: Optional[int] = Field(default=None, description="Unidades compradas.")
    unit_price: Optional[float] = Field(default=None, description="Precio unitario.")
    total_price: Optional[float] = Field(default=None, description="Precio total de la línea.")
    product: Optional[Product] = Field(default=None, description="Producto asociado.")


# ── Modelos de devolución ──────────────────────────────────────────────────


class ReturnItem(BaseModel):
    """Artículo incluido en una solicitud de devolución.

    Usado tanto por las tools MCP (donde el LLM en modo strict necesita
    un JSON Schema fijo) como por el structured output del agente de triaje.
    """

    order_item_id: str = Field(
        description=(
            "UUID del order_item a devolver. Se identifica por el nombre del producto "
            "que menciona el cliente, cruzándolo con los artículos del pedido ya "
            "consultado; no se le pide este UUID al cliente."
        )
    )
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


class ItemEligibility(BaseModel):
    """Resultado de evaluación de elegibilidad para UN artículo del pedido.

    Cada artículo de ``items_to_return`` se evalúa contra la política de SU
    PROPIA categoría, de forma independiente de los demás artículos del
    mismo pedido.
    """

    order_item_id: str = Field(description="UUID del order_item evaluado.")
    is_eligible: bool = Field(description="Si este artículo concreto es elegible para devolución.")
    eligibility_reason: str = Field(
        description="Explicación de la decisión para este artículo (criterio de política aplicado)."
    )
    refund_amount: float = Field(
        default=0.0, description="Importe a reembolsar por este artículo (0 si no es elegible)."
    )
    policy_category: str = Field(
        default="", description="Categoría de política aplicada a este artículo."
    )


class PolicyEvaluationOutput(BaseModel):
    """Salida estructurada del Agente Evaluador de Políticas.

    Contiene una evaluación independiente por cada artículo en
    ``items_to_return``, permitiendo que un mismo pedido tenga artículos
    elegibles y no elegibles simultáneamente.
    """

    items: list[ItemEligibility] = Field(
        description="Evaluación de elegibilidad de cada artículo solicitado, uno a uno."
    )


class TriageOutput(BaseModel):
    """Salida estructurada del agente de triaje."""

    response_to_customer: str = Field(
        description="Respuesta empática a mostrar al cliente en este turno."
    )
    order_number: Optional[str] = Field(
        default=None,
        description=(
            "Número de pedido tal como lo tiene el cliente en su email de confirmación "
            "(ej. 'ORD-2026-00177'). None si el cliente aún no lo ha proporcionado."
        ),
    )
    reason: Optional[str] = Field(
        default=None,
        description="Motivo de la devolución en palabras del cliente.",
    )
    reason_category: Optional[str] = Field(
        default=None,
        description="Categoría: defective, wrong_item, not_as_described, no_longer_needed, arrived_late, other.",
    )
    items_to_return: Optional[list[ReturnItem]] = Field(
        default=None,
        description="Lista de artículos a devolver. None si aún no se conocen.",
    )
