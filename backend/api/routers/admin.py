"""Router admin: panel de gestión y HITL (Human-in-the-Loop)."""

import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException
from langgraph.types import Command

from backend.api.dependencies import get_graph
from backend.api.schemas import AdminDecisionRequest
from backend.services import supabase_service

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Mismo tope que backend/api/routers/chat.py: sin esto, un `ainvoke` de
# reanudación colgado (LLM/MCP/BD sin responder) dejaba la petición del
# admin esperando para siempre, sin ninguna excepción capturable.
GRAPH_RECURSION_LIMIT = int(os.getenv("GRAPH_RECURSION_LIMIT", "25"))
GRAPH_TURN_TIMEOUT_SECONDS = float(os.getenv("GRAPH_TURN_TIMEOUT_SECONDS", "60"))


@router.get("/pending")
async def list_pending_returns():
    """Lista devoluciones pendientes de aprobación humana (HITL >100€)."""
    data = await supabase_service.list_pending_approvals()
    return {"pending": data, "count": len(data)}


@router.post("/{thread_id}/approve")
async def approve_return(
    thread_id: str,
    body: AdminDecisionRequest = AdminDecisionRequest(),
    graph=Depends(get_graph),
):
    """Admin aprueba una devolución pendiente. Reanuda el grafo."""
    try:
        result = await asyncio.wait_for(
            graph.ainvoke(
                Command(resume={"approved": True, "reason": body.reason}),
                config={
                    "configurable": {"thread_id": thread_id},
                    "recursion_limit": GRAPH_RECURSION_LIMIT,
                },
            ),
            timeout=GRAPH_TURN_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="El grafo tardó demasiado en reanudarse.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error reanudando el grafo: {exc}")

    return {
        "thread_id": thread_id,
        "resolution": result.get("resolution"),
        "tracking_number": result.get("tracking_number"),
    }


@router.post("/{thread_id}/reject")
async def reject_return(
    thread_id: str,
    body: AdminDecisionRequest = AdminDecisionRequest(),
    graph=Depends(get_graph),
):
    """Admin rechaza una devolución pendiente. Reanuda el grafo."""
    try:
        result = await asyncio.wait_for(
            graph.ainvoke(
                Command(resume={"approved": False, "reason": body.reason}),
                config={
                    "configurable": {"thread_id": thread_id},
                    "recursion_limit": GRAPH_RECURSION_LIMIT,
                },
            ),
            timeout=GRAPH_TURN_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="El grafo tardó demasiado en reanudarse.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error reanudando el grafo: {exc}")

    return {
        "thread_id": thread_id,
        "resolution": result.get("resolution"),
    }


@router.get("/returns")
async def list_returns(status: str = None, limit: int = 50):
    """Lista devoluciones con filtro opcional por estado."""
    data = await supabase_service.list_returns(status=status, limit=limit)
    return {"returns": data, "count": len(data)}


@router.get("/returns/{return_id}")
async def get_return_detail(return_id: str):
    """Detalle de una devolución específica."""
    data = await supabase_service.get_return_detail(return_id)
    if not data:
        raise HTTPException(status_code=404, detail="Devolución no encontrada.")
    return data
