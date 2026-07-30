"""
Cliente MCP para conectar los agentes con los MCP servers via protocolo.

Expone las tools de ambos servers (Supabase y Logística) como funciones
async que internamente se comunican por HTTP con los MCP servers.

Requiere que los MCP servers estén levantados:
  - python -m backend.mcp.mcp_supabase  (puerto 8001)
  - python -m backend.mcp.mcp_logistics  (puerto 8002)
"""

from __future__ import annotations

import os
import logging
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuración de URLs (por defecto: local)
# ---------------------------------------------------------------------------

MCP_SUPABASE_URL = os.getenv("MCP_SUPABASE_URL", "http://localhost:8001/mcp")
MCP_LOGISTICS_URL = os.getenv("MCP_LOGISTICS_URL", "http://localhost:8002/mcp")


# ---------------------------------------------------------------------------
# Cliente MCP singleton
# ---------------------------------------------------------------------------

_client: MultiServerMCPClient | None = None


async def get_mcp_client() -> MultiServerMCPClient:
    """Devuelve el cliente MCP, creándolo si es la primera vez."""
    global _client
    if _client is None:
        _client = MultiServerMCPClient({
            "supabase": {"url": MCP_SUPABASE_URL},
            "logistics": {"url": MCP_LOGISTICS_URL},
        })
        await _client.__aenter__()
    return _client


async def close_mcp_client() -> None:
    """Cierra la conexión con los MCP servers."""
    global _client
    if _client is not None:
        await _client.__aexit__(None, None, None)
        _client = None


# ---------------------------------------------------------------------------
# Funciones helper para llamar tools por nombre
# ---------------------------------------------------------------------------


async def call_tool(tool_name: str, args: dict[str, Any]) -> Any:
    """Llama a una tool MCP por nombre con los argumentos dados.

    Args:
        tool_name: Nombre de la tool registrada en el MCP server.
        args: Diccionario de argumentos para la tool.

    Returns:
        El resultado de la tool.
    """
    client = await get_mcp_client()
    tools = client.get_tools()

    tool = next((t for t in tools if t.name == tool_name), None)
    if tool is None:
        raise ValueError(f"Tool '{tool_name}' no encontrada en los MCP servers.")

    result = await tool.ainvoke(args)
    return result


# ---------------------------------------------------------------------------
# Wrappers tipados (misma interfaz que services/)
# ---------------------------------------------------------------------------


async def get_order_details(order_id: str) -> dict:
    """Consulta detalles del pedido via MCP."""
    return await call_tool("get_order_details", {"order_id": order_id})


async def get_customer_return_history(customer_id: str) -> dict:
    """Recupera historial de devoluciones via MCP."""
    return await call_tool("get_customer_return_history", {"customer_id": customer_id})


async def search_return_policy(query: str, category: str = "") -> dict:
    """Búsqueda RAG de políticas via MCP."""
    return await call_tool("search_return_policy", {"query": query, "category": category})


async def create_return_record(
    order_id: str,
    customer_id: str,
    reason: str,
    reason_category: str,
    refund_amount: float,
    items: list[dict],
    notes: str = "",
) -> dict:
    """Crea registro de devolución via MCP."""
    return await call_tool("create_return_record", {
        "order_id": order_id,
        "customer_id": customer_id,
        "reason": reason,
        "reason_category": reason_category,
        "refund_amount": refund_amount,
        "items": items,
        "notes": notes,
    })


async def update_return_status(
    return_id: str,
    status: str,
    resolution: str = "",
    notes: str = "",
) -> dict:
    """Actualiza estado de devolución via MCP."""
    return await call_tool("update_return_status", {
        "return_id": return_id,
        "status": status,
        "resolution": resolution,
        "notes": notes,
    })


async def generate_shipping_label(
    order_id: str,
    items: list[dict],
    customer_name: str = "",
    customer_address: str = "",
) -> dict:
    """Genera etiqueta de transporte via MCP."""
    return await call_tool("generate_shipping_label", {
        "order_id": order_id,
        "items": items,
        "customer_name": customer_name,
        "customer_address": customer_address,
    })


async def send_customer_notification(
    email: str,
    message: str,
    subject: str = "ReFlow - Actualización de tu devolución",
    attachment_path: str = "",
) -> dict:
    """Envía notificación al cliente via MCP."""
    return await call_tool("send_customer_notification", {
        "email": email,
        "message": message,
        "subject": subject,
        "attachment_path": attachment_path,
    })
