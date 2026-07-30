"""
Servicio de acceso a datos Supabase.

Contiene toda la lógica de consultas y mutaciones sobre PostgreSQL/Supabase.
Consumido por: agentes, MCP server, API REST.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import openai
from supabase import AsyncClient, create_async_client

from backend.db.supabase_client import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cliente Supabase (singleton perezoso)
# ---------------------------------------------------------------------------

_client: Optional[AsyncClient] = None


async def _get_client() -> AsyncClient:
    """Devuelve el cliente Supabase, creándolo si es la primera vez."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = await create_async_client(
            supabase_url=settings.supabase_url,
            supabase_key=settings.supabase_service_key,
        )
    return _client


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------


async def get_order_details(order_id: str) -> dict:
    """Consulta detalles del pedido, cliente y productos comprados.

    Args:
        order_id: UUID del pedido.

    Returns:
        Dict con claves "order" e "items".
    """
    client = await _get_client()

    order_resp = (
        await client.table("orders")
        .select("*, customer:customers(id, email, full_name)")
        .eq("id", order_id)
        .single()
        .execute()
    )

    items_resp = (
        await client.table("order_items")
        .select("*, product:products(name, sku, category, price, weight_kg)")
        .eq("order_id", order_id)
        .execute()
    )

    return {
        "order": order_resp.data,
        "items": items_resp.data,
    }


# ---------------------------------------------------------------------------
# Historial de devoluciones
# ---------------------------------------------------------------------------


async def get_customer_return_history(customer_id: str) -> dict:
    """Recupera el historial de devoluciones del cliente.

    Args:
        customer_id: UUID del cliente.

    Returns:
        Dict con estadísticas y lista de devoluciones.
    """
    client = await _get_client()

    returns_resp = (
        await client.table("return_requests")
        .select(
            "id, order_id, status, reason, reason_category, "
            "resolution, refund_amount, created_at, resolved_at"
        )
        .eq("customer_id", customer_id)
        .order("created_at", desc=True)
        .execute()
    )

    total_returns = len(returns_resp.data)
    approved = sum(1 for r in returns_resp.data if r["status"] == "approved")
    rejected = sum(1 for r in returns_resp.data if r["status"] == "rejected")

    return {
        "customer_id": customer_id,
        "total_returns": total_returns,
        "approved": approved,
        "rejected": rejected,
        "returns": returns_resp.data,
    }


# ---------------------------------------------------------------------------
# Búsqueda RAG de políticas
# ---------------------------------------------------------------------------


async def search_return_policy(query: str, category: str = "") -> dict:
    """Búsqueda semántica RAG sobre políticas de devolución usando pgvector.

    Args:
        query: Texto de consulta en lenguaje natural.
        category: Categoría opcional para filtrar políticas.

    Returns:
        Dict con resultados semánticos y política estructurada.
    """
    client = await _get_client()

    openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    embedding_resp = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=query,
    )
    query_embedding = embedding_resp.data[0].embedding

    rpc_params = {
        "query_embedding": query_embedding,
        "match_threshold": 0.7,
        "match_count": 5,
    }
    results = await client.rpc("match_policy_embeddings", rpc_params).execute()

    policy_info = None
    if category:
        policy_resp = (
            await client.table("return_policies")
            .select("*")
            .eq("category", category)
            .eq("active", True)
            .single()
            .execute()
        )
        policy_info = policy_resp.data

    return {
        "query": query,
        "category": category,
        "semantic_results": results.data,
        "policy_info": policy_info,
    }


# ---------------------------------------------------------------------------
# Crear devolución
# ---------------------------------------------------------------------------


async def create_return_record(
    order_id: str,
    customer_id: str,
    reason: str,
    reason_category: str,
    refund_amount: float,
    items: list[dict],
    notes: str = "",
) -> dict:
    """Inserta una solicitud de devolución y sus items en Supabase.

    Args:
        order_id: UUID del pedido.
        customer_id: UUID del cliente.
        reason: Motivo de la devolución.
        reason_category: Categoría del motivo.
        refund_amount: Monto del reembolso.
        items: Lista de items [{"order_item_id": "...", "quantity": 1, "condition": "..."}].
        notes: Notas adicionales.

    Returns:
        Dict con la solicitud creada y cantidad de items.
    """
    client = await _get_client()

    return_data = {
        "order_id": order_id,
        "customer_id": customer_id,
        "status": "pending",
        "reason": reason,
        "reason_category": reason_category,
        "refund_amount": refund_amount,
        "notes": notes,
    }

    return_resp = await client.table("return_requests").insert(return_data).execute()
    return_request = return_resp.data[0]
    return_id = return_request["id"]

    return_items_data = [
        {
            "return_request_id": return_id,
            "order_item_id": item["order_item_id"],
            "quantity": item["quantity"],
            "condition": item.get("condition", "unknown"),
        }
        for item in items
    ]

    await client.table("return_items").insert(return_items_data).execute()

    return {
        "return_request": return_request,
        "items_created": len(return_items_data),
    }


# ---------------------------------------------------------------------------
# Actualizar estado de devolución
# ---------------------------------------------------------------------------


async def update_return_status(
    return_id: str,
    status: str,
    resolution: str = "",
    notes: str = "",
) -> dict:
    """Actualiza el estado de una devolución.

    Args:
        return_id: UUID de la solicitud de devolución.
        status: Nuevo estado.
        resolution: Resolución aplicada.
        notes: Notas del administrador.

    Returns:
        Dict con la devolución actualizada.
    """
    client = await _get_client()

    update_data: dict = {"status": status}
    if resolution:
        update_data["resolution"] = resolution
    if notes:
        update_data["notes"] = notes
    if status in ("approved", "rejected", "completed"):
        update_data["resolved_at"] = "now()"

    resp = (
        await client.table("return_requests")
        .update(update_data)
        .eq("id", return_id)
        .execute()
    )

    return {"updated_return": resp.data[0] if resp.data else None}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def calculate_days_since_delivery(order_details: dict[str, Any]) -> int:
    """Calcula los días transcurridos desde la entrega del pedido.

    Args:
        order_details: Dict con la clave "order" que contiene "delivered_at" o "created_at".

    Returns:
        Número de días desde la entrega. 9999 si no hay fecha disponible.
    """
    delivered_at_str = order_details.get("order", {}).get("delivered_at")
    if not delivered_at_str:
        delivered_at_str = order_details.get("order", {}).get("created_at", "")

    if not delivered_at_str:
        return 9999

    delivered_at = datetime.fromisoformat(delivered_at_str.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (now - delivered_at).days
