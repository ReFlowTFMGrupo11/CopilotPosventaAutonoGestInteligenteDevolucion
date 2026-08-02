"""
Registro de sesiones de chat para analítica/métricas.

Escribe en las tablas ``chat_sessions`` y ``chat_messages`` de Supabase
para tener trazabilidad de las conversaciones: duración, mensajes,
estado final y cliente asociado.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from backend.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


async def start_session(thread_id: str, customer_id: Optional[str] = None) -> str:
    """Registra el inicio de una sesión de chat.

    Args:
        thread_id: UUID del thread (mismo que usa el checkpointer).
        customer_id: UUID del cliente, si se conoce al inicio.

    Returns:
        El ID de la sesión creada.
    """
    client = await get_supabase_client()
    row = {
        "id": thread_id,
        "status": "active",
        "metadata": {"source": "demo_chat"},
    }
    if customer_id:
        row["customer_id"] = customer_id

    result = await client.table("chat_sessions").insert(row).execute()
    logger.info("Sesión de chat iniciada: %s", thread_id)
    return thread_id


async def record_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
) -> None:
    """Registra un mensaje en la sesión.

    Args:
        session_id: UUID de la sesión (thread_id).
        role: 'user', 'assistant' o 'system'.
        content: Texto del mensaje.
        metadata: Datos extra (agente actual, order_id, etc.).
    """
    client = await get_supabase_client()
    row = {
        "session_id": session_id,
        "role": role,
        "content": content,
        "metadata": metadata or {},
    }
    await client.table("chat_messages").insert(row).execute()


async def end_session(
    session_id: str,
    status: str = "completed",
    customer_id: Optional[str] = None,
) -> None:
    """Marca la sesión como finalizada.

    Args:
        session_id: UUID de la sesión.
        status: Estado final ('completed', 'abandoned', 'escalated').
        customer_id: UUID del cliente, si se descubrió durante la sesión.
    """
    client = await get_supabase_client()
    updates: dict = {
        "status": status,
        "ended_at": datetime.now(timezone.utc).isoformat(),
    }
    if customer_id:
        updates["customer_id"] = customer_id

    await client.table("chat_sessions").update(updates).eq("id", session_id).execute()
    logger.info("Sesión %s cerrada con estado: %s", session_id, status)
