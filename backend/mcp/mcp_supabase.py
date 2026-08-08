"""
MCP Server: Supabase (Datos y Políticas)

Wrapper fino sobre backend/services/supabase_service.py: cada tool solo traduce
argumentos y delega en la función de servicio equivalente. Toda la lógica real
(consultas a Supabase, RAG con pgvector) vive en services/, no aquí — ver el
docstring de supabase_service.py y doc/AUDITORIA_RAMAS.md (punto 6) para el porqué
de esta separación.

Tools:
- get_order_details: Consulta detalles del pedido.
- get_customer_return_history: Historial de devoluciones del cliente.
- search_return_policy: Búsqueda semántica RAG sobre políticas.
- create_return_record: Crea registro de devolución.
- update_return_status: Actualiza estado de devolución.
"""

# load_dotenv: search_return_policy (en supabase_service.py) lee OPENAI_API_KEY con
# os.getenv(), que solo ve variables de entorno reales del proceso, no el fichero
# .env (a diferencia de SupabaseSettings, que lo lee directamente vía
# pydantic-settings). Sin esto, el servidor arranca y get_order_details funciona,
# pero search_return_policy falla con "Missing credentials" en cuanto necesita
# llamar a la API de embeddings de OpenAI.
from dotenv import load_dotenv
# Se usa la serie 1.x del SDK "mcp" (no la 2.x, donde esta clase pasó a
# llamarse MCPServer) porque "langchain-mcp-adapters" todavía no soporta
# mcp 2.x (ver requirements.txt).
from mcp.server.fastmcp import FastMCP
from backend.models import ReturnItem

from backend.services import supabase_service

load_dotenv(override=True)

mcp = FastMCP("supabase-data-policies", host="0.0.0.0", port=8001)


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
    return await supabase_service.get_order_details(order_id)


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
    return await supabase_service.get_customer_return_history(customer_id)


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
    return await supabase_service.search_return_policy(query, category)


# ---------------------------------------------------------------------------
# Tool 4: create_return_record
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
    # supabase_service.create_return_record espera dicts normales.
    return await supabase_service.create_return_record(
        order_id=order_id,
        customer_id=customer_id,
        reason=reason,
        reason_category=reason_category,
        refund_amount=refund_amount,
        items=[item.model_dump() for item in items],
        notes=notes,
    )


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
    return await supabase_service.update_return_status(
        return_id=return_id,
        status=status,
        resolution=resolution,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Arranque del servidor
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # streamable-http es el sustituto oficial de HTTP+SSE, deprecado en la
    # revisión de spec 2025-03-26. Accesible en http://0.0.0.0:8001/mcp.
    mcp.run(transport="streamable-http")
