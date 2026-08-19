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
        # Pass category as filter so the vector search only returns chunks from
        # the relevant policy document (+ marco general). Without this, a query
        # for "alimentacion" could return high-similarity chunks from "mascotas"
        # or "drogueria_salud" (all hygiene-sensitive categories share similar text).
        # NULL = search all chunks (backwards-compatible default in the SQL function).
        "filter_category": category if category else None,
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
    thread_id: str = "",
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

    # ── Guard: evitar devoluciones duplicadas para el mismo pedido ──────
    # - Bloquear si ya hay una devolución ACTIVA del pedido.
    # - Bloquear si alguno de los order_item_id ya fue devuelto antes
    #   (approved/completed o también activo).
    active_statuses = {"pending", "pending_approval", "processing"}
    historical_statuses = active_statuses | {"approved", "completed"}

    existing = await (
        client.table("return_requests")
        .select("id, status, return_items(order_item_id)")
        .eq("order_id", order_id)
        .in_("status", list(historical_statuses))
        .execute()
    )

    active_returns = [
        row for row in (existing.data or [])
        if row.get("status") in active_statuses
    ]
    if active_returns:
        raise ValueError(
            f"Ya existe una devolución activa para el pedido {order_id} "
            f"(id={active_returns[0]['id']}, status={active_returns[0]['status']})."
        )

    requested_item_ids = {
        item.get("order_item_id")
        for item in items
        if item.get("order_item_id")
    }
    previously_returned_item_ids = {
        ret_item.get("order_item_id")
        for row in (existing.data or [])
        for ret_item in (row.get("return_items") or [])
        if ret_item.get("order_item_id")
    }

    duplicated_item_ids = requested_item_ids & previously_returned_item_ids
    if duplicated_item_ids:
        duplicated_str = ", ".join(sorted(duplicated_item_ids))
        raise ValueError(
            "Ya existe una devolución previa para el/los artículo(s): "
            f"{duplicated_str}."
        )

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
    if thread_id:
        return_data["thread_id"] = thread_id

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


# ---------------------------------------------------------------------------
# Consultas admin (panel HITL y dashboard)
# ---------------------------------------------------------------------------


def _flatten_order_number(row: dict) -> dict:
    """Extrae `orders.order_number` del embed de PostgREST a un campo plano.

    El cliente de Supabase devuelve el join como `row["orders"]["order_number"]`;
    el frontend quiere un `order_number` de primer nivel, junto al `order_id`
    (UUID interno), para poder mostrarlo y usarlo en el buscador de pedidos.
    """
    order = row.pop("orders", None) or {}
    row["order_number"] = order.get("order_number")
    return row


def _flatten_product_names(row: dict) -> dict:
    """Extrae los nombres de producto del embed anidado return_items→order_items→products.

    Un return puede incluir varios artículos (pedidos mixtos, ver
    qa_manual_testing_seed_pedidos_mixtos.sql); se unen los nombres con ", "
    en un único campo `product_names` de primer nivel para la tabla del panel
    admin.
    """
    items = row.pop("return_items", None) or []
    names = [
        product.get("name")
        for item in items
        for product in [(item.get("order_items") or {}).get("product") or {}]
        if product.get("name")
    ]
    row["product_names"] = ", ".join(names) if names else None
    return row


def _flatten_admin_row(row: dict) -> dict:
    return _flatten_product_names(_flatten_order_number(row))


async def list_pending_approvals() -> list[dict]:
    """Devuelve devoluciones con status pending_approval (HITL)."""
    client = await get_supabase_client()
    resp = await client.table("return_requests").select(
        "id, thread_id, order_id, customer_id, reason, reason_category, refund_amount, "
        "created_at, orders(order_number), return_items(order_items(product:products(name)))"
    ).eq("status", "pending_approval").order("created_at", desc=True).execute()
    return [_flatten_admin_row(row) for row in (resp.data or [])]


async def list_returns(status: str | None = None, limit: int = 50) -> list[dict]:
    """Lista devoluciones con filtro opcional por estado."""
    client = await get_supabase_client()
    query = client.table("return_requests").select(
        "id, order_id, customer_id, status, reason, reason_category, refund_amount, "
        "created_at, resolved_at, orders(order_number), "
        "return_items(order_items(product:products(name)))"
    ).order("created_at", desc=True).limit(limit)

    if status:
        query = query.eq("status", status)

    resp = await query.execute()
    return [_flatten_admin_row(row) for row in (resp.data or [])]


async def get_return_detail(return_id: str) -> dict | None:
    """Detalle de una devolución específica con sus items."""
    client = await get_supabase_client()
    resp = await client.table("return_requests").select(
        "*, return_items(id, order_item_id, quantity, condition)"
    ).eq("id", return_id).single().execute()
    return resp.data


async def get_return_stats() -> dict:
    """KPIs generales del sistema de devoluciones."""
    client = await get_supabase_client()
    resp = await client.table("return_requests").select("status").execute()
    returns = resp.data or []

    total = len(returns)
    approved = sum(1 for r in returns if r["status"] == "approved")
    rejected = sum(1 for r in returns if r["status"] == "rejected")
    pending = sum(1 for r in returns if r["status"] in ("pending", "pending_approval"))

    return {
        "total_returns": total,
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "approval_rate": round(approved / total * 100, 1) if total > 0 else 0,
    }
