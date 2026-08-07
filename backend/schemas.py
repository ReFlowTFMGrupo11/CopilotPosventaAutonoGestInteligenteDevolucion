"""
backend/schemas.py
=====================
Modelos Pydantic del contrato HTTP entre el backend FastAPI y el frontend
Streamlit. Viven aparte de backend/models/ (que son los modelos de DOMINIO
compartidos con los agentes/MCP) porque estos son específicamente la forma
de las peticiones y eventos SSE de la API web, no del grafo de LangGraph.
"""

from typing import Literal, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Cuerpo de POST /api/chat/stream: un turno de chat de un thread concreto."""

    message: str
    thread_id: str


class ChatStreamEvent(BaseModel):
    """
    Un evento del streaming SSE de un turno de chat. `type` determina qué
    otros campos son relevantes:
      - "agent_step": el grafo acaba de completar un nodo (`agent`).
      - "final": el turno terminó con una respuesta para el cliente.
      - "awaiting_admin": el grafo se pausó (interrupt()) por HITL; el
        cliente recibe un mensaje de espera, no la respuesta definitiva.
      - "error": algo falló al procesar el turno.
    """

    type: Literal["agent_step", "final", "awaiting_admin", "error"]
    content: str
    agent: Optional[str] = None
    order_id: Optional[str] = None
    is_eligible: Optional[bool] = None
    tracking_number: Optional[str] = None
    label_path: Optional[str] = None
    resolution: Optional[str] = None


class PendingApprovalOut(BaseModel):
    """Una devolución pausada por HITL, tal como la ve el panel de administración."""

    thread_id: str
    order_id: Optional[str] = None
    customer_id: Optional[str] = None
    refund_amount: Optional[float] = None
    reason: Optional[str] = None
    message: Optional[str] = None


class ApproveRequest(BaseModel):
    """Cuerpo de POST /api/admin/approve/{thread_id}: decisión del administrador."""

    approved: bool


class ApproveResponse(BaseModel):
    """Resultado de aplicar la decisión del administrador y reanudar el grafo."""

    thread_id: str
    status: str
    content: str
