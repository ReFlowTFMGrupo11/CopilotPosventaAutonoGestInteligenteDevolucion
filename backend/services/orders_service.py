"""
Servicio de pedidos: consulta de detalles de pedido y cálculo de días desde
la entrega. Contiene la lógica que antes vivía dentro de las funciones
`@mcp.tool()` de backend/mcp/mcp_supabase.py.

Porqué esta capa existe (ver doc/AUDITORIA_RAMAS.md, punto 6): antes, la lógica de
negocio (qué tablas de Supabase consultar) estaba mezclada con el código de
transporte MCP (decoradores @mcp.tool(), formato de argumentos que espera un LLM).
Eso impedía reutilizar, por ejemplo, "consultar un pedido" desde un futuro endpoint
FastAPI sin arrastrar el protocolo MCP. Con esta capa, mcp_supabase.py pasa a ser
un wrapper fino que solo traduce `@mcp.tool()` -> llamada a estas funciones;
cualquier otro consumidor (FastAPI, un script, un test) puede importar directamente
desde aquí sin tocar MCP.

Extraído de supabase_service.py (ver docs/REMAINING_TASKS.md #3): ese fichero
mezclaba pedidos, devoluciones y políticas/RAG bajo un nombre de tecnología,
no de dominio de negocio — mismo criterio ya aplicado a los routers de la
API (routers/orders.py se dividió en admin.py/usage.py, ver
docs/defensaTFM/defenderFastAPI.md).
"""

from datetime import datetime, timezone

from backend.db.supabase_client import get_supabase_client

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def calculate_days_since_delivery(order_details: dict) -> int:
    """Calcula los días transcurridos desde la entrega del pedido.

    Usa `delivered_at` si existe, sino `created_at` como fallback.
    Devuelve 9999 si no hay ninguna fecha disponible.

    Vive aquí (dominio pedidos) aunque también lo use el Agente Evaluador
    (backend/agents/nodes/evaluator.py) para reglas de devolución: opera
    exclusivamente sobre `order_details`, sin ningún dato específico de
    devoluciones.
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

    order_resp = (
        await client.table("orders")
        .select("*, customer:customers(id, email, full_name)")
        .eq("order_number", order_number)
        .single()
        .execute()
    )

    items_resp = (
        await client.table("order_items")
        .select("*, product:products(name, sku, category, price, weight_kg)")
        .eq("order_id", order_resp.data["id"])
        .execute()
    )

    return {
        "order": order_resp.data,
        "items": items_resp.data,
    }
