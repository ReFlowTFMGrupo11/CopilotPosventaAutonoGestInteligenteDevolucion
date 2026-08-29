"""
Estado compartido del grafo de devoluciones.

Define el TypedDict que fluye entre los tres agentes (Triaje, Evaluador, Resolución)
y las aristas condicionales del grafo LangGraph.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class ReturnState(TypedDict, total=False):
    """Estado global del grafo de devoluciones.

    Cada agente lee las claves que necesita y escribe solo las que actualiza.
    ``messages`` usa el reducer ``add_messages`` para acumular el historial
    de la conversación sin sobrescribirlo.
    """

    # ── Historial de conversación ──────────────────────────────────────
    messages: Annotated[list[AnyMessage], add_messages]

    # ── Datos extraídos por el Agente de Triaje ────────────────────────
    order_number: (
        str | None
    )  # número de pedido tal cual lo da el cliente (ej. "ORD-2026-00177")
    order_id: (
        str | None
    )  # UUID interno, resuelto en fetch_order_data a partir de order_number
    customer_id: str | None
    customer_name: str | None
    customer_email: str | None
    reason: str | None
    reason_category: str | None
    items_to_return: list[dict[str, Any]]
    selected_item_ids: list[str] | None
    # True solo cuando el cliente ha confirmado explícitamente el resumen de
    # artículos + motivo + estado que el agente le mostró. Se resetea a False
    # en cuanto items_to_return cambia de contenido (ver triage.py::_items_key).
    items_confirmed: bool

    # ── Datos del pedido (rellenados tras consultar Supabase) ──────────
    order_details: dict[str, Any] | None
    return_history: dict[str, Any] | None

    # ── Resultado del Agente Evaluador ─────────────────────────────────
    # Evaluación independiente por artículo (ver ItemEligibility). Un mismo
    # pedido puede tener artículos elegibles y no elegibles a la vez.
    items_eligibility: list[dict[str, Any]]
    any_eligible: (
        bool | None
    )  # True si AL MENOS UN artículo es elegible (usado para el routing)
    eligibility_reason: (
        str | None
    )  # Resumen agregado, usado por rejection_agent cuando NINGÚN artículo es elegible
    policy_info: dict[str, Any] | None
    refund_amount: float  # Suma de refund_amount de los artículos elegibles únicamente

    # ── Resultado del Agente de Resolución ─────────────────────────────
    needs_admin_approval: bool
    admin_decision: str | None  # "approved" | "rejected" | None
    tracking_number: str | None
    label_path: str | None
    return_request_id: str | None
    resolution: str | None

    # ── Identificador de sesión LangGraph ─────────────────────────────
    thread_id: str | None

    # ── Control de flujo ───────────────────────────────────────────────
    current_agent: str | None
    error: str | None
