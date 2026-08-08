"""Schemas de request/response para la API."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Chat ───────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """Mensaje del usuario al sistema de chat."""

    thread_id: str = Field(description="UUID de la sesión de chat.")
    message: str = Field(description="Mensaje del usuario.")


class ChatResponse(BaseModel):
    """Respuesta del sistema al usuario."""

    thread_id: str
    response: str = Field(description="Respuesta del agente.")
    current_agent: Optional[str] = None
    order_id: Optional[str] = None
    is_eligible: Optional[bool] = None
    resolution: Optional[str] = None


class ChatStreamEvent(BaseModel):
    """Evento SSE emitido durante el streaming de un turno de chat.

    - agent_step: un nodo del grafo completó su ejecución.
    - final: respuesta definitiva del agente.
    - awaiting_admin: el grafo se pausó por HITL (reembolso >100€).
    - error: falló la ejecución del grafo.
    """

    type: Literal["agent_step", "final", "awaiting_admin", "error"]
    content: str
    agent: Optional[str] = None
    order_id: Optional[str] = None
    is_eligible: Optional[bool] = None
    tracking_number: Optional[str] = None
    label_path: Optional[str] = None
    resolution: Optional[str] = None


class NewChatResponse(BaseModel):
    """Respuesta al crear una nueva sesión."""

    thread_id: str


# ── Admin / HITL ───────────────────────────────────────────────────────────


class AdminDecisionRequest(BaseModel):
    """Decisión del administrador sobre una devolución pendiente."""

    reason: str = Field(default="", description="Motivo opcional de la decisión.")


class PendingReturn(BaseModel):
    """Devolución pendiente de aprobación."""

    thread_id: str
    order_id: Optional[str] = None
    customer_name: Optional[str] = None
    refund_amount: Optional[float] = None
    reason: Optional[str] = None


class ReturnSummary(BaseModel):
    """Resumen de una devolución."""

    id: str
    order_id: str
    customer_id: str
    status: str
    reason: Optional[str] = None
    reason_category: Optional[str] = None
    refund_amount: Optional[float] = None
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None


# ── Orders ─────────────────────────────────────────────────────────────────


class OrderDetailResponse(BaseModel):
    """Detalle de un pedido."""

    order: dict
    items: list


class ReturnHistoryResponse(BaseModel):
    """Historial de devoluciones de un cliente."""

    customer_id: str
    total_returns: int
    approved: int
    rejected: int
    returns: list
