"""
Cliente MCP para conectar los agentes con los MCP servers via protocolo.

Expone las tools de ambos servers (Supabase y Logística) como funciones
async que internamente se comunican por SSE con los MCP servers.

Cada server se conecta de forma independiente y bajo demanda (lazy),
de modo que si uno no está disponible no bloquea al otro.

Requiere que los MCP servers estén levantados:
  - python -m backend.mcp.mcp_supabase  (puerto 8001)
  - python -m backend.mcp.mcp_logistics  (puerto 8002)
"""

# __future__ annotations: permite anotaciones de tipo modernas evaluadas de
# forma perezosa (no en tiempo de importación).
from __future__ import annotations

import os
import logging
from typing import Any

# MultiServerMCPClient: cliente de la librería langchain-mcp-adapters capaz
# de hablar con uno o varios servidores MCP y exponer sus tools como
# objetos invocables desde LangChain/LangGraph.
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuración de URLs (por defecto: local)
# ---------------------------------------------------------------------------

# os.getenv con valor por defecto: en desarrollo local apunta a localhost;
# en otro entorno (Docker, producción) se puede sobreescribir por variable
# de entorno sin tocar código.
MCP_SUPABASE_URL = os.getenv("MCP_SUPABASE_URL", "http://localhost:8001/mcp")
MCP_LOGISTICS_URL = os.getenv("MCP_LOGISTICS_URL", "http://localhost:8002/mcp")

# Mapeo de tool → server para saber qué cliente usar
# Diccionario estático: dado el nombre de una tool, indica a qué servidor
# MCP pertenece, para no tener que preguntarle a ambos servidores por turno.
_TOOL_SERVER_MAP = {
    "get_order_details": "supabase",
    "get_customer_return_history": "supabase",
    "search_return_policy": "supabase",
    "create_return_record": "supabase",
    "update_return_status": "supabase",
    "generate_shipping_label": "logistics",
    "send_customer_notification": "logistics",
}

# ---------------------------------------------------------------------------
# Clientes MCP individuales (lazy, uno por server)
# ---------------------------------------------------------------------------

# Caché a nivel de módulo: una vez creado el cliente de un server, se
# reutiliza en todas las llamadas siguientes dentro del mismo proceso.
_clients: dict[str, MultiServerMCPClient] = {}


async def _get_server_client(server_name: str) -> MultiServerMCPClient:
    """Devuelve el cliente MCP para un server concreto, creándolo si es necesario."""
    # Solo se crea la conexión la primera vez que se pide ese server en
    # concreto ("supabase" o "logistics"); las siguientes veces se reutiliza.
    if server_name not in _clients:
        if server_name == "supabase":
            url = MCP_SUPABASE_URL
        elif server_name == "logistics":
            url = MCP_LOGISTICS_URL
        else:
            # Protección ante errores de programación: un nombre de server
            # que no sea "supabase" ni "logistics" no debería llegar nunca aquí.
            raise ValueError(f"Server MCP desconocido: {server_name}")

        # MultiServerMCPClient admite varios servers en un solo diccionario,
        # pero aquí se instancia uno por server para poder fallar de forma
        # independiente si uno de los dos no está disponible.
        _clients[server_name] = MultiServerMCPClient({
            server_name: {
                "transport": "http",
                "url": url,
            },
        })
        logger.info("Cliente MCP creado para server '%s' en %s", server_name, url)

    return _clients[server_name]


async def close_mcp_client() -> None:
    """Cierra todos los clientes MCP."""
    # No cierra conexiones de red explícitamente: simplemente vacía la
    # caché, de forma que la próxima llamada recree los clientes desde cero.
    _clients.clear()


# ---------------------------------------------------------------------------
# Funciones helper para llamar tools por nombre
# ---------------------------------------------------------------------------


async def call_tool(tool_name: str, args: dict[str, Any]) -> Any:
    """Llama a una tool MCP por nombre con los argumentos dados.

    Determina automáticamente qué server contiene la tool y solo
    conecta con ese server (no requiere que todos estén levantados).
    """
    # Busca en el mapeo estático a qué servidor pertenece esta tool.
    server_name = _TOOL_SERVER_MAP.get(tool_name)
    if server_name is None:
        raise ValueError(f"Tool '{tool_name}' no está mapeada a ningún server MCP.")

    client = await _get_server_client(server_name)
    # get_tools(): pide al servidor MCP la lista de tools que expone (con
    # su schema); se vuelve a pedir en cada llamada por simplicidad.
    tools = await client.get_tools()

    # Busca, dentro de la lista de tools del server, la que coincide por nombre.
    tool = next((t for t in tools if t.name == tool_name), None)
    if tool is None:
        raise ValueError(f"Tool '{tool_name}' no encontrada en server '{server_name}'.")

    # ainvoke(): ejecuta la tool remota de forma asíncrona con los argumentos dados.
    result = await tool.ainvoke(args)
    return result


# ---------------------------------------------------------------------------
# Wrappers tipados (misma interfaz que services/)
# ---------------------------------------------------------------------------
# A partir de aquí, cada función es un atajo de conveniencia sobre call_tool():
# en vez de que cada nodo del grafo escriba call_tool("nombre", {...}) con el
# diccionario de argumentos a mano, se les da una firma Python normal y
# tipada, más fácil de leer y con autocompletado en el editor.


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
