"""Router admin: panel de gestión y HITL (Human-in-the-Loop)."""

from fastapi import APIRouter, HTTPException
from langgraph.types import Command

from backend.api.dependencies import get_graph
from backend.api.schemas import AdminDecisionRequest
from backend.services import supabase_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/pending")
async def list_pending_returns():
    """Lista devoluciones pendientes de aprobación humana (HITL >100€).

    Busca threads con estado de grafo pausado en el nodo resolver.
    """
    # En una implementación completa, consultaríamos los checkpoints
    # del grafo buscando threads interrumpidos. Por ahora, consultamos
    # la tabla return_requests con status 'pending_approval'.
    from backend.db.supabase_client import get_supabase_client

    client = await get_supabase_client()
    resp = await client.table("return_requests").select(
        "id, order_id, customer_id, reason, reason_category, refund_amount, created_at"
    ).eq("status", "pending_approval").order("created_at", desc=True).execute()

    return {"pending": resp.data}


@router.post("/{thread_id}/approve")
async def approve_return(thread_id: str, body: AdminDecisionRequest = AdminDecisionRequest()):
    """Admin aprueba una devolución pendiente. Reanuda el grafo."""
    graph = await get_graph()

    try:
        result = await graph.ainvoke(
            Command(resume={"approved": True, "reason": body.reason}),
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error reanudando el grafo: {exc}")

    return {
        "thread_id": thread_id,
        "resolution": result.get("resolution"),
        "tracking_number": result.get("tracking_number"),
    }


@router.post("/{thread_id}/reject")
async def reject_return(thread_id: str, body: AdminDecisionRequest = AdminDecisionRequest()):
    """Admin rechaza una devolución pendiente. Reanuda el grafo."""
    graph = await get_graph()

    try:
        result = await graph.ainvoke(
            Command(resume={"approved": False, "reason": body.reason}),
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error reanudando el grafo: {exc}")

    return {
        "thread_id": thread_id,
        "resolution": result.get("resolution"),
    }


@router.get("/returns")
async def list_returns(status: str = None, limit: int = 50):
    """Lista devoluciones con filtro opcional por estado."""
    from backend.db.supabase_client import get_supabase_client

    client = await get_supabase_client()
    query = client.table("return_requests").select(
        "id, order_id, customer_id, status, reason, reason_category, refund_amount, created_at, resolved_at"
    ).order("created_at", desc=True).limit(limit)

    if status:
        query = query.eq("status", status)

    resp = await query.execute()
    return {"returns": resp.data, "count": len(resp.data)}


@router.get("/returns/{return_id}")
async def get_return_detail(return_id: str):
    """Detalle de una devolución específica."""
    from backend.db.supabase_client import get_supabase_client

    client = await get_supabase_client()
    resp = await client.table("return_requests").select(
        "*, return_items(id, order_item_id, quantity, condition)"
    ).eq("id", return_id).single().execute()

    if not resp.data:
        raise HTTPException(status_code=404, detail="Devolución no encontrada.")

    return resp.data
