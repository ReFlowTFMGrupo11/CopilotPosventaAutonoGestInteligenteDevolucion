"""
Servicio de acceso a datos: pedidos, historial de devoluciones, políticas (RAG) y
mutaciones sobre las devoluciones. Contiene toda la lógica que antes vivía dentro de
las funciones `@mcp.tool()` de backend/mcp/mcp_supabase.py.

Porqué esta capa existe (ver doc/AUDITORIA_RAMAS.md, punto 6): antes, la lógica de
negocio (qué tablas de Supabase consultar, cómo calcular el historial) estaba mezclada
con el código de transporte MCP (decoradores @mcp.tool(), formato de argumentos que
espera un LLM). Eso impedía reutilizar, por ejemplo, "consultar un pedido" desde un
futuro endpoint FastAPI sin arrastrar el protocolo MCP. Con esta capa, mcp_supabase.py
pasa a ser un wrapper fino que solo traduce `@mcp.tool()` -> llamada a estas funciones;
cualquier otro consumidor (FastAPI, un script, un test) puede importar directamente
desde aquí sin tocar MCP.

A diferencia de las tools MCP (ver ReturnItem en mcp_supabase.py), estas funciones no
usan modelos Pydantic para `items`: ese tipado solo hace falta en la frontera MCP,
donde un LLM con tools + response_format en modo "strict" necesita un JSON Schema
fijo (ver README.md, "Correcciones de robustez recientes"). Aquí, sin LLM de por
medio, un `list[dict]` normal es más simple y no tiene ese problema.
"""

import os
from datetime import datetime, timezone

from backend.db.supabase_client import get_supabase_client


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def calculate_days_since_delivery(order_details: dict) -> int:
    """Calcula los días transcurridos desde la entrega del pedido.

    Usa `delivered_at` si existe, sino `created_at` como fallback.
    Devuelve 9999 si no hay ninguna fecha disponible.
    """
    order = order_details.get("order", {})
    date_str = order.get("delivered_at") or order.get("created_at")
    if not date_str:
        return 9999

    # Parsear la fecha (soporta tanto +00:00 como Z)
    date_str = date_str.replace("Z", "+00:00")
    try:
        delivered = datetime.fromisoformat(date_str)
    except ValueError:
        return 9999

    now = datetime.now(timezone.utc)
    return (now - delivered).days


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------


async def get_order_details(order_number: str) -> dict:
    """Consulta en PostgreSQL los detalles del pedido, fechas y productos comprados.

    Se busca por el número de pedido (el dato que tiene el cliente), no por el
    UUID interno: ese se devuelve dentro de "order"/"id" para uso interno del grafo.

    Args:
        order_number: Número de pedido tal como lo tiene el cliente (ej. "ORD-2026-00177").
    """
    client = await get_supabase_client()

    order_resp = await client.table("orders").select(
        "*, customer:customers(id, email, full_name)"
    ).eq("order_number", order_number).single().execute()

    items_resp = await client.table("order_items").select(
        "*, product:products(name, sku, category, price, weight_kg)"
    ).eq("order_id", order_resp.data["id"]).execute()

    return {
        "order": order_resp.data,
        "items": items_resp.data,
    }


# ---------------------------------------------------------------------------
# Historial de devoluciones
# ---------------------------------------------------------------------------


async def get_customer_return_history(customer_id: str) -> dict:
    """Recupera el historial de devoluciones del cliente para detectar posibles abusos.

    Args:
        customer_id: UUID del cliente.
    """
    client = await get_supabase_client()

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
# Búsqueda RAG de políticas
# ---------------------------------------------------------------------------


async def search_return_policy(query: str, category: str = "") -> dict:
    """Realiza una búsqueda semántica RAG usando pgvector sobre la normativa de la tienda.

    Args:
        query: Texto de consulta para buscar en las políticas.
        category: Categoría opcional para filtrar políticas (e.g., "electronics").
    """
    # Import local para no cargar el SDK de OpenAI si esta función no se invoca.
    import openai

    client = await get_supabase_client()

    openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    # Debe ser el mismo modelo de embedding usado al indexar las políticas.
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
    """Inserta una solicitud de devolución en la tabla devoluciones de Supabase.

    Args:
        order_id: UUID del pedido.
        customer_id: UUID del cliente.
        reason: Motivo de la devolución.
        reason_category: Categoría del motivo (e.g., "defective", "wrong_item").
        refund_amount: Monto del reembolso.
        items: Lista de items a devolver, cada uno con "order_item_id", "quantity"
            y opcionalmente "condition".
        notes: Notas adicionales opcionales.
    """
    client = await get_supabase_client()

    # Toda devolución nueva arranca en estado "pending".
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
    """Actualiza el estado de la devolución desde el panel de control manual.

    Args:
        return_id: UUID de la solicitud de devolución.
        status: Nuevo estado ("approved", "rejected", "processing", "completed").
        resolution: Resolución aplicada (e.g., "full_refund", "partial_refund", "replacement").
        notes: Notas adicionales del administrador.
    """
    client = await get_supabase_client()

    # resolution/notes solo se envían si el llamante los proporcionó, para no
    # sobrescribir con cadenas vacías valores ya guardados.
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
