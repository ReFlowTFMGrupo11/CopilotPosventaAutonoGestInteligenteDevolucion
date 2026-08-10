"""Router de consultas: pedidos, historial, KPIs (sin LLM, directo a services)."""

from fastapi import APIRouter, HTTPException

from backend.api.schemas import OrderDetailResponse, ReturnHistoryResponse
from backend.services import supabase_service

router = APIRouter(prefix="/api", tags=["orders"])


@router.get("/orders/{order_id}", response_model=OrderDetailResponse)
async def get_order(order_id: str):
    """Detalle de un pedido (productos, cliente, fechas)."""
    try:
        result = await supabase_service.get_order_details(order_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Pedido no encontrado: {exc}")
    return result


@router.get("/customers/{customer_id}/history", response_model=ReturnHistoryResponse)
async def get_customer_history(customer_id: str):
    """Historial de devoluciones de un cliente."""
    try:
        result = await supabase_service.get_customer_return_history(customer_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Cliente no encontrado: {exc}")
    return result


@router.get("/stats")
async def get_stats():
    """KPIs generales del sistema de devoluciones."""
    return await supabase_service.get_return_stats()
