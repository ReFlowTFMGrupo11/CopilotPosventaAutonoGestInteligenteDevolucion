"""
MCP Server: Supabase (Datos y Políticas)

Tools:
- get_order_details: Consulta detalles del pedido.
- get_customer_return_history: Historial de devoluciones del cliente.
- search_return_policy: Búsqueda semántica RAG sobre políticas.
- create_return_record: Crea registro de devolución.
- update_return_status: Actualiza estado de devolución.
"""

import os
from typing import Optional

from fastmcp import FastMCP
from supabase import create_async_client, AsyncClient

from backend.db.supabase_client import get_settings

mcp = FastMCP("supabase-data-policies")

# ---------------------------------------------------------------------------
# Helper: get Supabase client
# ---------------------------------------------------------------------------

_client: Optional[AsyncClient] = None


async def _get_client() -> AsyncClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = await create_async_client(
            supabase_url=settings.supabase_url,
            supabase_key=settings.supabase_service_key,
        )
    return _client


# ---------------------------------------------------------------------------
# Tool 1: get_order_details
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_order_details(order_id: str) -> dict:
    """
    Consulta en PostgreSQL los detalles del pedido, fechas y productos comprados.
    Usado por Agentes 1 y 2.

    Args:
        order_id: UUID del pedido a consultar.
    """
    client = await _get_client()

    # Get order info
    order_resp = await client.table("orders").select(
        "*, customer:customers(id, email, full_name)"
    ).eq("id", order_id).single().execute()

    # Get order items with product details
    items_resp = await client.table("order_items").select(
        "*, product:products(name, sku, category, price, weight_kg)"
    ).eq("order_id", order_id).execute()

    return {
        "order": order_resp.data,
        "items": items_resp.data,
    }


# ---------------------------------------------------------------------------
# Tool 2: get_customer_return_history
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_customer_return_history(customer_id: str) -> dict:
    """
    Recupera el historial de devoluciones del cliente para detectar posibles abusos.
    Usado por Agente 2.

    Args:
        customer_id: UUID del cliente.
    """
    client = await _get_client()

    returns_resp = await client.table("return_requests").select(
        "id, order_id, status, reason, reason_category, resolution, refund_amount, created_at, resolved_at"
    ).eq("customer_id", customer_id).order("created_at", desc=True).execute()

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
# Tool 3: search_return_policy
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_return_policy(query: str, category: str = "") -> dict:
    """
    Realiza una búsqueda semántica RAG usando pgvector sobre la normativa de la tienda.
    Usado por Agente 2.

    Args:
        query: Texto de consulta para buscar en las políticas.
        category: Categoría opcional para filtrar políticas (e.g., "electronics").
    """
    import openai

    client = await _get_client()

    # Generate embedding for the query
    openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    embedding_resp = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=query,
    )
    query_embedding = embedding_resp.data[0].embedding

    # Call the match_policy_embeddings function via RPC
    rpc_params = {
        "query_embedding": query_embedding,
        "match_threshold": 0.7,
        "match_count": 5,
    }
    results = await client.rpc("match_policy_embeddings", rpc_params).execute()

    # If category filter is provided, also get the specific policy
    policy_info = None
    if category:
        policy_resp = await client.table("return_policies").select("*").eq(
            "category", category
        ).eq("active", True).single().execute()
        policy_info = policy_resp.data

    return {
        "query": query,
        "category": category,
        "semantic_results": results.data,
        "policy_info": policy_info,
    }


# ---------------------------------------------------------------------------
# Tool 4: create_return_record
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_return_record(
    order_id: str,
    customer_id: str,
    reason: str,
    reason_category: str,
    refund_amount: float,
    items: list[dict],
    notes: str = "",
) -> dict:
    """
    Inserta una solicitud de devolución en la tabla devoluciones de Supabase.
    Usado por Agente 3.

    Args:
        order_id: UUID del pedido.
        customer_id: UUID del cliente.
        reason: Motivo de la devolución.
        reason_category: Categoría del motivo (e.g., "defective", "wrong_item").
        refund_amount: Monto del reembolso.
        items: Lista de items a devolver [{"order_item_id": "...", "quantity": 1, "condition": "unopened"}].
        notes: Notas adicionales opcionales.
    """
    client = await _get_client()

    # Create return request
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

    # Create return items
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
# Tool 5: update_return_status
# ---------------------------------------------------------------------------


@mcp.tool()
async def update_return_status(
    return_id: str,
    status: str,
    resolution: str = "",
    notes: str = "",
) -> dict:
    """
    Actualiza el estado de la devolución desde el panel de control manual.
    Usado por Admin / HITL (Human-In-The-Loop).

    Args:
        return_id: UUID de la solicitud de devolución.
        status: Nuevo estado ("approved", "rejected", "processing", "completed").
        resolution: Resolución aplicada (e.g., "full_refund", "partial_refund", "replacement").
        notes: Notas adicionales del administrador.
    """
    client = await _get_client()

    update_data: dict = {"status": status}
    if resolution:
        update_data["resolution"] = resolution
    if notes:
        update_data["notes"] = notes
    if status in ("approved", "rejected", "completed"):
        update_data["resolved_at"] = "now()"

    resp = await client.table("return_requests").update(update_data).eq(
        "id", return_id
    ).execute()

    return {"updated_return": resp.data[0] if resp.data else None}


# ---------------------------------------------------------------------------
# Run server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8001)
