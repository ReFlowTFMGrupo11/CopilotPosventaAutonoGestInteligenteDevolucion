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

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from backend.config import get_settings
from backend.services import tool_call_service
from backend.services.observability import score_rag_similarity, score_tool_call

logger = logging.getLogger(__name__)

# Mapeo de tool → server para saber qué cliente usar
_TOOL_SERVER_MAP = {
    "get_order_details": "supabase",
    "get_customer_return_history": "supabase",
    "get_policy_info": "supabase",
    "search_return_policy": "supabase",
    "create_return_record": "supabase",
    "update_return_status": "supabase",
    "get_pending_return_request_id": "supabase",
    "get_latest_return_request": "supabase",
    "generate_shipping_label": "logistics",
    "send_customer_notification": "logistics",
}

# ---------------------------------------------------------------------------
# Clientes MCP individuales (lazy, uno por server)
# ---------------------------------------------------------------------------

_clients: dict[str, MultiServerMCPClient] = {}

# Cache de tools por server: sin esto, call_tool() hacía un round-trip HTTP
# extra a por la lista de tools en CADA llamada (antes de invocar la tool
# real), en cada turno de cada agente. Las tools de un server MCP no
# cambian durante la vida del proceso, así que basta con listarlas una vez.
_tools_cache: dict[str, list[Any]] = {}


async def _get_server_client(server_name: str) -> MultiServerMCPClient:
    """Devuelve el cliente MCP para un server concreto, creándolo si es necesario."""
    if server_name not in _clients:
        settings = get_settings()
        if server_name == "supabase":
            url = settings.mcp_supabase_url
        elif server_name == "logistics":
            url = settings.mcp_logistics_url
        else:
            raise ValueError(f"Server MCP desconocido: {server_name}")

        _clients[server_name] = MultiServerMCPClient(
            {
                server_name: {
                    "transport": "http",
                    "url": url,
                    "timeout": settings.mcp_timeout_seconds,
                    "sse_read_timeout": settings.mcp_sse_read_timeout_seconds,
                },
            }
        )
        logger.info("Cliente MCP creado para server '%s' en %s", server_name, url)

    return _clients[server_name]


async def _get_tools(server_name: str) -> list[Any]:
    """Devuelve las tools de un server, cacheadas tras la primera consulta."""
    if server_name not in _tools_cache:
        client = await _get_server_client(server_name)
        _tools_cache[server_name] = await client.get_tools()
    return _tools_cache[server_name]


async def close_mcp_client() -> None:
    """Cierra todos los clientes MCP y limpia la cache de tools."""
    _clients.clear()
    _tools_cache.clear()


# ---------------------------------------------------------------------------
# Funciones helper para llamar tools por nombre
# ---------------------------------------------------------------------------


def _parse_tool_result(tool_name: str, result: Any) -> Any:
    """Interpreta la respuesta cruda de una tool MCP.

    MCP tool responses may come as raw JSON strings or content blocks.
    Parse them to return a proper Python dict/list.

    Raises:
        RuntimeError: si la respuesta lleva el prefijo de error de MCP
            ("Error executing tool") -- la tool SÍ se invocó, pero falló en
            el lado del server.
    """
    if isinstance(result, str):
        if result.startswith("Error executing tool"):
            raise RuntimeError(f"MCP tool '{tool_name}' failed: {result}")
        try:
            return json.loads(result)
        except (json.JSONDecodeError, ValueError):
            return result
    if isinstance(result, list) and result:
        # Content block list — extract text from first block
        first = result[0]
        text = first.get("text", first) if isinstance(first, dict) else str(first)
        if isinstance(text, str) and text.startswith("Error executing tool"):
            raise RuntimeError(f"MCP tool '{tool_name}' failed: {text}")
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError, TypeError):
            return result
    return result


async def _log_tool_call(
    tool_name: str,
    *,
    success: bool,
    latency_ms: int,
    thread_id: str | None,
    error: str | None,
) -> None:
    """Registra el resultado de una llamada a una tool MCP.

    Tabla propia ``mcp_tool_calls`` (señal garantizada, ver
    ``tool_call_service.py``) + score de LangFuse (canal extra, ver
    ``score_tool_call``). Un fallo aquí NUNCA debe enmascarar el resultado
    real de la tool -- se loguea y se sigue (mismo principio que
    ``usage_tracking.py::_log_usage`` para el coste de LLM).
    """
    try:
        await tool_call_service.log_tool_call(
            tool_name=tool_name,
            success=success,
            latency_ms=latency_ms,
            thread_id=thread_id,
            error_message=error,
        )
    except Exception:
        logger.warning(
            "No se pudo registrar en mcp_tool_calls la llamada a la tool '%s'",
            tool_name,
            exc_info=True,
        )
    score_tool_call(thread_id, tool_name, success=success, error=error)


async def call_tool(tool_name: str, args: dict[str, Any]) -> Any:
    """Llama a una tool MCP por nombre con los argumentos dados.

    Determina automáticamente qué server contiene la tool y solo
    conecta con ese server (no requiere que todos estén levantados).

    Registra éxito/fallo y latencia de la invocación real (no de la
    búsqueda de la tool en cache, que es un error de configuración/wiring
    distinto) en ``mcp_tool_calls`` -- ver ``_log_tool_call``. `thread_id`
    se extrae de forma oportunista de ``args["thread_id"]`` cuando está
    presente (no todos los wrappers de este módulo lo reciben, ver
    docstring de la migración de ``mcp_tool_calls``); sin él, la fila sigue
    siendo útil para la agregación por tool, solo pierde la trazabilidad a
    la sesión.

    Returns:
        El resultado ya parseado a ``dict``/``list`` si la respuesta MCP
        era JSON serializado (caso normal); si no se pudo parsear, se
        devuelve tal cual (str, list de content blocks, etc.).
    """
    server_name = _TOOL_SERVER_MAP.get(tool_name)
    if server_name is None:
        raise ValueError(f"Tool '{tool_name}' no está mapeada a ningún server MCP.")

    tools = await _get_tools(server_name)
    tool = next((t for t in tools if t.name == tool_name), None)
    if tool is None:
        # Cache posiblemente obsoleta (p. ej. el server MCP se reinició con
        # otro set de tools): refrescar una vez antes de rendirse.
        _tools_cache.pop(server_name, None)
        tools = await _get_tools(server_name)
        tool = next((t for t in tools if t.name == tool_name), None)
    if tool is None:
        raise ValueError(f"Tool '{tool_name}' no encontrada en server '{server_name}'.")

    thread_id = args.get("thread_id") or None
    start = time.perf_counter()
    try:
        result = await tool.ainvoke(args)
        parsed = _parse_tool_result(tool_name, result)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        await _log_tool_call(
            tool_name,
            success=False,
            latency_ms=latency_ms,
            thread_id=thread_id,
            error=str(exc),
        )
        raise
    latency_ms = int((time.perf_counter() - start) * 1000)
    await _log_tool_call(
        tool_name,
        success=True,
        latency_ms=latency_ms,
        thread_id=thread_id,
        error=None,
    )
    return parsed


# ---------------------------------------------------------------------------
# Wrappers tipados (misma interfaz que services/)
# ---------------------------------------------------------------------------


async def get_order_details(order_number: str) -> dict:
    """Consulta detalles del pedido via MCP."""
    return await call_tool("get_order_details", {"order_number": order_number})


async def get_customer_return_history(customer_id: str) -> dict:
    """Recupera historial de devoluciones via MCP."""
    return await call_tool("get_customer_return_history", {"customer_id": customer_id})


async def get_policy_info(category: str) -> dict | None:
    """Política estructurada de una categoría via MCP, sin búsqueda vectorial.

    Más barata que ``search_return_policy()`` (sin embedding, sin RPC de
    similitud) — pensada para el pre-check determinista de
    ``evaluator_agent`` (ver docs/defensaTFM/defenderRAG.md §4.2).
    """
    return await call_tool("get_policy_info", {"category": category})


async def search_return_policy(
    query: str, category: str = "", thread_id: str | None = None
) -> dict:
    """Búsqueda RAG de políticas via MCP.

    Además de devolver el resultado, registra un score de LangFuse con la
    mejor similitud coseno obtenida (ver
    ``backend.services.observability.score_rag_similarity``) para poder
    ver de un vistazo, sin abrir cada traza, qué búsquedas RAG no están
    devolviendo nada relevante. `thread_id` viaja también dentro de la
    llamada MCP (no solo se usa aquí en local) porque el propio embedding
    de OpenAI se llama en el proceso del MCP server, no en este -- ver
    ``backend.services.policy_service.search_return_policy``.
    """
    result = await call_tool(
        "search_return_policy",
        {"query": query, "category": category, "thread_id": thread_id or ""},
    )
    score_rag_similarity(
        thread_id, query, category, result.get("semantic_results") or []
    )
    return result


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
    """Crea registro de devolución via MCP."""
    return await call_tool(
        "create_return_record",
        {
            "order_id": order_id,
            "customer_id": customer_id,
            "reason": reason,
            "reason_category": reason_category,
            "refund_amount": refund_amount,
            "items": items,
            "notes": notes,
            "thread_id": thread_id,
        },
    )


async def update_return_status(
    return_id: str,
    status: str,
    resolution: str = "",
    notes: str = "",
    refund_amount: float | None = None,
) -> dict:
    """Actualiza estado de devolución via MCP."""
    return await call_tool(
        "update_return_status",
        {
            "return_id": return_id,
            "status": status,
            "resolution": resolution,
            "notes": notes,
            "refund_amount": refund_amount,
        },
    )


async def get_pending_return_request_id(order_id: str) -> str:
    """Recupera el id de la devolución pendiente/en aprobación via MCP.

    La tool MCP devuelve un dict (``{"return_request_id": ...}``), no un
    string plano -- ver el docstring de la tool en mcp_supabase.py sobre
    por qué (call_tool() solo desenvuelve JSON de forma fiable). Este
    wrapper desenvuelve el dict para que la interfaz siga siendo idéntica a
    ``returns_service.get_pending_return_request_id`` (misma que antes del
    cambio a MCP): quien llama recibe directamente el string.
    """
    result = await call_tool("get_pending_return_request_id", {"order_id": order_id})
    return result.get("return_request_id", "")


async def get_latest_return_request(order_id: str) -> dict:
    """Recupera la devolución más reciente de un pedido via MCP."""
    return await call_tool("get_latest_return_request", {"order_id": order_id})


async def generate_shipping_label(
    order_id: str,
    items: list[dict],
    customer_name: str = "",
    customer_address: str = "",
) -> dict:
    """Genera etiqueta de transporte via MCP."""
    return await call_tool(
        "generate_shipping_label",
        {
            "order_id": order_id,
            "items": items,
            "customer_name": customer_name,
            "customer_address": customer_address,
        },
    )


async def send_customer_notification(
    email: str,
    message: str,
    subject: str = "ReFlow - Actualización de tu devolución",
    attachment_path: str = "",
) -> dict:
    """Envía notificación al cliente via MCP."""
    return await call_tool(
        "send_customer_notification",
        {
            "email": email,
            "message": message,
            "subject": subject,
            "attachment_path": attachment_path,
        },
    )
