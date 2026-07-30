"""
MCP Server: Supabase (Datos y Políticas)

Wrapper fino sobre backend.services.supabase_service.
Expone las funciones como herramientas MCP via Streamable HTTP.
"""

from mcp.server.fastmcp import FastMCP

from backend.services.supabase_service import (
    create_return_record as _create_return_record,
    get_customer_return_history as _get_customer_return_history,
    get_order_details as _get_order_details,
    search_return_policy as _search_return_policy,
    update_return_status as _update_return_status,
)

mcp = FastMCP("supabase-data-policies", host="0.0.0.0", port=8001)


@mcp.tool()
async def get_order_details(order_id: str) -> dict:
    """Consulta en PostgreSQL los detalles del pedido, fechas y productos comprados.

    Args:
        order_id: UUID del pedido a consultar.
    """
    return await _get_order_details(order_id)


@mcp.tool()
async def get_customer_return_history(customer_id: str) -> dict:
    """Recupera el historial de devoluciones del cliente para detectar posibles abusos.

    Args:
        customer_id: UUID del cliente.
    """
    return await _get_customer_return_history(customer_id)


@mcp.tool()
async def search_return_policy(query: str, category: str = "") -> dict:
    """Realiza una búsqueda semántica RAG usando pgvector sobre la normativa de la tienda.

    Args:
        query: Texto de consulta para buscar en las políticas.
        category: Categoría opcional para filtrar políticas.
    """
    return await _search_return_policy(query, category)


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
    """Inserta una solicitud de devolución en la tabla devoluciones de Supabase.

    Args:
        order_id: UUID del pedido.
        customer_id: UUID del cliente.
        reason: Motivo de la devolución.
        reason_category: Categoría del motivo.
        refund_amount: Monto del reembolso.
        items: Lista de items a devolver.
        notes: Notas adicionales opcionales.
    """
    return await _create_return_record(
        order_id=order_id,
        customer_id=customer_id,
        reason=reason,
        reason_category=reason_category,
        refund_amount=refund_amount,
        items=items,
        notes=notes,
    )


@mcp.tool()
async def update_return_status(
    return_id: str,
    status: str,
    resolution: str = "",
    notes: str = "",
) -> dict:
    """Actualiza el estado de la devolución desde el panel de control manual.

    Args:
        return_id: UUID de la solicitud de devolución.
        status: Nuevo estado.
        resolution: Resolución aplicada.
        notes: Notas adicionales del administrador.
    """
    return await _update_return_status(
        return_id=return_id,
        status=status,
        resolution=resolution,
        notes=notes,
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
