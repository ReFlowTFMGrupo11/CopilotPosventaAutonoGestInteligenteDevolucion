"""
MCP Server: Supabase (Datos y Políticas)

Wrapper fino sobre backend/services/{orders,returns,policy}_service.py: cada
tool solo traduce argumentos y delega en la función de servicio equivalente.
Toda la lógica real (consultas a Supabase, RAG con pgvector) vive en
services/, no aquí — ver docs/REMAINING_TASKS.md #3 (por qué se dividió en 3
módulos por dominio, no uno solo) y doc/AUDITORIA_RAMAS.md punto 6 (por qué
existe esta capa de servicios en absoluto).

Tools:
- get_order_details: Consulta detalles del pedido. (orders_service)
- get_customer_return_history: Historial de devoluciones del cliente. (returns_service)
- get_policy_info: Política estructurada de una categoría (sin RAG narrativo). (policy_service)
- search_return_policy: Búsqueda semántica RAG sobre políticas. (policy_service)
- create_return_record: Crea registro de devolución. (returns_service)
- update_return_status: Actualiza estado de devolución. (returns_service)
- get_pending_return_request_id: Recupera el id de una devolución pendiente
  tras un duplicado en HITL (resume tras interrupt()). (returns_service)
- get_latest_return_request: Recupera la devolución más reciente de un
  pedido tras un duplicado en auto-aprobación. (returns_service)
"""

# Se usa la serie 1.x del SDK "mcp" (no la 2.x, donde esta clase pasó a
# llamarse MCPServer) porque "langchain-mcp-adapters" todavía no soporta
# mcp 2.x (ver requirements.txt).
from mcp.server.fastmcp import FastMCP
from backend.models import ReturnItem

from backend.services import orders_service, policy_service, returns_service

# Nota: ya no hace falta load_dotenv() aquí. search_return_policy (en
# policy_service.py) leía antes OPENAI_API_KEY con os.getenv() suelto, que
# solo ve variables de entorno reales del proceso, no el fichero .env — por
# eso este server (lanzado standalone, sin pasar por main.py) necesitaba
# cargarlo a mano o "Missing credentials" al llamar a la API de embeddings.
# Ahora ese valor viene de Settings (backend/config.py, pydantic-settings),
# que lee el .env directamente sin depender de load_dotenv().

mcp = FastMCP("supabase-data-policies", host="0.0.0.0", port=8001)


# ---------------------------------------------------------------------------
# Tool 1: get_order_details
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_order_details(order_number: str) -> dict:
    """
    Consulta en PostgreSQL los detalles del pedido, fechas y productos comprados.
    Usado por Agentes 1 y 2.

    Args:
        order_number: Número de pedido tal como lo tiene el cliente (ej. "ORD-2026-00177").
    """
    return await orders_service.get_order_details(order_number)


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
    return await returns_service.get_customer_return_history(customer_id)


# ---------------------------------------------------------------------------
# Tool 3: get_policy_info
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_policy_info(category: str) -> dict:
    """
    Consulta la política estructurada de una categoría (plazo, condiciones
    admitidas, recargo de reposición) SIN búsqueda vectorial ni llamada a
    embeddings — más barata que search_return_policy. Usado por Agente 2
    para el veto legal/determinista antes de decidir si hace falta la
    búsqueda RAG narrativa.

    Args:
        category: Categoría de producto (ej. "electronica_informatica").
    """
    return await policy_service.get_policy_info(category)


# ---------------------------------------------------------------------------
# Tool 4: search_return_policy
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_return_policy(
    query: str, category: str = "", thread_id: str = ""
) -> dict:
    """
    Realiza una búsqueda semántica RAG usando pgvector sobre la normativa de la tienda.
    Usado por Agente 2.

    Args:
        query: Texto de consulta para buscar en las políticas.
        category: Categoría opcional para filtrar políticas (e.g., "electronics").
        thread_id: id de conversación, solo para trazabilidad en LangFuse.
    """
    return await policy_service.search_return_policy(query, category, thread_id)


# ---------------------------------------------------------------------------
# Tool 5: create_return_record
# ---------------------------------------------------------------------------


# ReturnItem importado de backend.models


@mcp.tool()
async def create_return_record(
    order_id: str,
    customer_id: str,
    reason: str,
    reason_category: str,
    refund_amount: float,
    items: list[ReturnItem],
    notes: str = "",
    thread_id: str = "",
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
        items: Lista de items a devolver (ver ReturnItem).
        notes: Notas adicionales opcionales.
    """
    # El tipado con ReturnItem es solo de esta tool (frontera MCP/LLM);
    # returns_service.create_return_record espera dicts normales.
    return await returns_service.create_return_record(
        order_id=order_id,
        customer_id=customer_id,
        reason=reason,
        reason_category=reason_category,
        refund_amount=refund_amount,
        items=[item.model_dump() for item in items],
        notes=notes,
        thread_id=thread_id,
    )


# ---------------------------------------------------------------------------
# Tool 6: update_return_status
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
    return await returns_service.update_return_status(
        return_id=return_id,
        status=status,
        resolution=resolution,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Tool 7: get_pending_return_request_id
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_pending_return_request_id(order_id: str) -> dict:
    """
    Recupera el id de la devolución pendiente/en aprobación de un pedido.
    Usado por el Agente de Resolución tras un duplicado al reanudar un HITL
    (resume tras interrupt()): el registro ya se creó en el intento
    anterior, así que se recupera su id en vez de crear uno nuevo.

    Devuelve un dict (no un string plano) para que la respuesta viaje como
    JSON por el protocolo MCP: call_tool() en mcp_client.py solo desenvuelve
    de forma fiable contenido JSON (dict/list); un string plano sin comillas
    (p. ej. un UUID, o "" si no hay ninguna pendiente) no es JSON válido y
    haría que call_tool() lo tratase como "texto no-JSON inesperado" en vez
    de como el resultado normal de la tool.

    Args:
        order_id: UUID del pedido.

    Returns:
        Dict con "return_request_id" (cadena vacía si no hay ninguna
        devolución pendiente para ese pedido).
    """
    return_request_id = await returns_service.get_pending_return_request_id(order_id)
    return {"return_request_id": return_request_id}


# ---------------------------------------------------------------------------
# Tool 8: get_latest_return_request
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_latest_return_request(order_id: str) -> dict:
    """
    Recupera la devolución más reciente de un pedido (id y status). Usado
    por el Agente de Resolución tras un duplicado en auto-aprobación, para
    informar al cliente del estado de la devolución que ya existe.

    Args:
        order_id: UUID del pedido.
    """
    return await returns_service.get_latest_return_request(order_id)


# ---------------------------------------------------------------------------
# Arranque del servidor
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # streamable-http es el sustituto oficial de HTTP+SSE, deprecado en la
    # revisión de spec 2025-03-26. Accesible en http://0.0.0.0:8001/mcp.
    mcp.run(transport="streamable-http")
