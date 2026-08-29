"""Router admin: panel de gestión y HITL (Human-in-the-Loop)."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from langgraph.types import Command

from backend.api.dependencies import get_graph
from backend.api.schemas import AdminDecisionRequest
from backend.config import get_settings
from backend.services import observability, supabase_service

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Mismo Settings (fuente única) que backend/api/routers/chat.py: antes,
# GRAPH_RECURSION_LIMIT/GRAPH_TURN_TIMEOUT_SECONDS se definían por
# duplicado en cada router con el mismo default — cambiar uno sin el otro
# los desincronizaba sin ningún aviso. Sin timeout/límite, un `ainvoke` de
# reanudación colgado (LLM/MCP/BD sin responder) dejaba la petición del
# admin esperando para siempre, sin ninguna excepción capturable.
_settings = get_settings()
GRAPH_RECURSION_LIMIT = _settings.graph_recursion_limit
GRAPH_TURN_TIMEOUT_SECONDS = _settings.graph_turn_timeout_seconds


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


@router.get("/observability")
async def get_observability_links():
    """Enlaces al dashboard de LangFuse para monitorizar gasto por sesión/cliente.

    No hay contador de coste propio (ver nota de alcance de la PR de
    controles de terminación): LangFuse ya trackea tokens/coste por
    `langfuse_session_id` y `langfuse_user_id` (ver with_langfuse en
    backend/services/observability.py), así que el panel solo enlaza a su
    dashboard en vez de reimplementar la agregación.
    """
    return observability.langfuse_links()
