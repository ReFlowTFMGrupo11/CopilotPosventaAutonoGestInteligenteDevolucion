"""
MCP Server: Supabase (Datos y Políticas)

Tools:
- get_order_details: Consulta detalles del pedido.
- get_customer_return_history: Historial de devoluciones del cliente.
- search_return_policy: Búsqueda semántica RAG sobre políticas.
- create_return_record: Crea registro de devolución.
- update_return_status: Actualiza estado de devolución.
"""

# os: se usa para leer la API key de OpenAI desde el entorno dentro de
# search_return_policy.
import os
# Optional: anotación de tipos para indicar que _client puede ser None hasta
# que se inicializa de forma perezosa (lazy).
from typing import Optional

# FastMCP: clase del SDK oficial "mcp" (paquete PyPI "mcp", serie 1.x).
# Expone el decorador @mcp.tool() y el método .run() para servir las
# herramientas por stdio, sse (obsoleto) o streamable-http.
# Nota: se usa la serie 1.x (no la 2.x, donde esta clase pasó a llamarse
# MCPServer en mcp.server.mcpserver) porque "langchain-mcp-adapters" —el
# puente que usa el agente LangChain para consumir estas tools— todavía no
# soporta el SDK mcp 2.x (ver requirements.txt).
from mcp.server.fastmcp import FastMCP
# create_async_client / AsyncClient: cliente asíncrono oficial de Supabase.
from supabase import create_async_client, AsyncClient

# get_settings: devuelve (cacheada) la configuración con la URL y la
# service_role key de Supabase leídas del .env.
from backend.db.supabase_client import get_settings

# Instancia del servidor MCP; el nombre "supabase-data-policies" es el
# identificador que verán los clientes MCP al listar servidores/tools.
mcp = FastMCP("supabase-data-policies", host="0.0.0.0", port=8001)

# ---------------------------------------------------------------------------
# Helper: get Supabase client
# ---------------------------------------------------------------------------

# Cliente Supabase compartido entre todas las tools de este proceso.
# Empieza en None y se crea la primera vez que se necesita (patrón singleton
# perezoso) para no abrir una conexión hasta que realmente haga falta.
_client: Optional[AsyncClient] = None


async def _get_client() -> AsyncClient:
    # "global" es necesario porque vamos a reasignar la variable del módulo,
    # no crear una variable local nueva.
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


# @mcp.tool() registra esta función como una herramienta MCP invocable por
# los agentes; el SDK genera el JSON Schema de entrada a partir de los type
# hints (order_id: str) y usa el docstring como descripción de la tool.
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
    # Consulta la tabla "orders" trayendo todas sus columnas (*) más un
    # join embebido a "customers" (alias "customer") con solo esos 3 campos.
    # .eq("id", order_id) filtra por el pedido solicitado.
    # .single() espera exactamente una fila y la devuelve como objeto (no lista).
    order_resp = await client.table("orders").select(
        "*, customer:customers(id, email, full_name)"
    ).eq("id", order_id).single().execute()

    # Get order items with product details
    # Trae todas las líneas de "order_items" de ese pedido, con un join
    # embebido a "products" para incluir nombre, sku, categoría, precio y peso.
    items_resp = await client.table("order_items").select(
        "*, product:products(name, sku, category, price, weight_kg)"
    ).eq("order_id", order_id).execute()

    # Combina cabecera del pedido e items en un único dict de respuesta.
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

    # Selecciona las columnas relevantes de "return_requests" para ese
    # cliente, ordenadas por fecha de creación descendente (más recientes primero).
    returns_resp = await client.table("return_requests").select(
        "id, order_id, status, reason, reason_category, resolution, refund_amount, created_at, resolved_at"
    ).eq("customer_id", customer_id).order("created_at", desc=True).execute()

    # Número total de devoluciones encontradas.
    total_returns = len(returns_resp.data)
    # Cuenta cuántas tienen estado "approved" (generator expression + sum).
    approved = sum(1 for r in returns_resp.data if r["status"] == "approved")
    # Cuenta cuántas tienen estado "rejected".
    rejected = sum(1 for r in returns_resp.data if r["status"] == "rejected")

    # Devuelve tanto las métricas agregadas como el listado detallado, para
    # que el agente pueda razonar sobre patrones de abuso.
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
    # Import local (dentro de la función) para no cargar el SDK de OpenAI si
    # esta tool en concreto nunca llega a invocarse.
    import openai

    client = await _get_client()

    # Generate embedding for the query
    # Crea un cliente OpenAI síncrono usando la API key del entorno.
    openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    # Convierte el texto de búsqueda en un vector de embedding con el modelo
    # "text-embedding-3-small" (el mismo espacio vectorial usado al indexar
    # las políticas en pgvector).
    embedding_resp = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=query,
    )
    # Extrae el vector de embedding de la respuesta (una sola entrada en "data").
    query_embedding = embedding_resp.data[0].embedding

    # Call the match_policy_embeddings function via RPC
    # Parámetros de la función SQL "match_policy_embeddings": el vector de
    # consulta, el umbral mínimo de similitud coseno y el nº máximo de
    # resultados a devolver.
    rpc_params = {
        "query_embedding": query_embedding,
        "match_threshold": 0.7,
        "match_count": 5,
    }
    # Invoca esa función remota (RPC) en Postgres, que hace la búsqueda
    # vectorial (pgvector) sobre los embeddings ya almacenados.
    results = await client.rpc("match_policy_embeddings", rpc_params).execute()

    # If category filter is provided, also get the specific policy
    # Si se pasó una categoría, además de la búsqueda semántica se recupera
    # la política activa exacta de esa categoría (búsqueda estructurada,
    # complementaria a la semántica).
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
    # Construye la fila a insertar en "return_requests"; toda devolución
    # nueva arranca siempre en estado "pending" (pendiente de revisión).
    return_data = {
        "order_id": order_id,
        "customer_id": customer_id,
        "status": "pending",
        "reason": reason,
        "reason_category": reason_category,
        "refund_amount": refund_amount,
        "notes": notes,
    }

    # Inserta la cabecera de la devolución y recupera la fila creada
    # (incluye el "id" autogenerado por la base de datos).
    return_resp = await client.table("return_requests").insert(return_data).execute()
    return_request = return_resp.data[0]
    return_id = return_request["id"]

    # Create return items
    # Construye una fila por cada item a devolver, enlazándola al
    # return_request recién creado mediante return_request_id.
    # item.get("condition", "unknown") usa "unknown" si el llamante no
    # especifica el estado físico del artículo devuelto.
    return_items_data = [
        {
            "return_request_id": return_id,
            "order_item_id": item["order_item_id"],
            "quantity": item["quantity"],
            "condition": item.get("condition", "unknown"),
        }
        for item in items
    ]

    # Inserta todas las líneas de devolución en una sola llamada (batch insert).
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

    # Construye el dict de campos a actualizar; status siempre se manda,
    # resolution/notes solo si el llamante los proporcionó (evita
    # sobrescribir con cadenas vacías valores ya guardados).
    update_data: dict = {"status": status}
    if resolution:
        update_data["resolution"] = resolution
    if notes:
        update_data["notes"] = notes
    # Si el nuevo estado es uno "final", se marca resolved_at con la fecha
    # actual del servidor de base de datos (función SQL now()).
    if status in ("approved", "rejected", "completed"):
        update_data["resolved_at"] = "now()"

    # Aplica el UPDATE sobre la fila con ese id y devuelve la fila actualizada.
    resp = await client.table("return_requests").update(update_data).eq(
        "id", return_id
    ).execute()

    # resp.data puede venir vacío si el id no existía; en ese caso se
    # devuelve None en vez de indexar una lista vacía.
    return {"updated_return": resp.data[0] if resp.data else None}


# ---------------------------------------------------------------------------
# Run server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Arranca el servidor MCP con transporte Streamable HTTP (el sustituto
    # oficial de HTTP+SSE, que quedó deprecado en la revisión de spec
    # 2025-03-26 y llegó a su end-of-life el 1 de abril de 2026). Host y
    # puerto se fijan en el constructor de FastMCP (línea 36); aquí solo se
    # elige el transporte. Queda accesible en http://0.0.0.0:8001/mcp.
    mcp.run(transport="streamable-http")
