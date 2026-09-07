"""Router admin: panel de gestión y HITL (Human-in-the-Loop)."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from langgraph.types import Command

from backend.api.dependencies import get_graph
from backend.api.schemas import AdminDecisionRequest
from backend.config import get_settings
from backend.services import observability, supabase_service, usage_service

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
    """Admin aprueba una devolución pendiente. Reanuda el grafo.

    Returns:
        Dict con `thread_id`, `resolution` y `tracking_number` (la
        etiqueta de envío ya generada tras la aprobación).
    """
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
        raise HTTPException(
            status_code=504, detail="El grafo tardó demasiado en reanudarse."
        )
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
    """Admin rechaza una devolución pendiente. Reanuda el grafo.

    Returns:
        Dict con `thread_id` y `resolution`.
    """
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
        raise HTTPException(
            status_code=504, detail="El grafo tardó demasiado en reanudarse."
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
    data = await supabase_service.list_returns(status=status, limit=limit)
    return {"returns": data, "count": len(data)}


@router.get("/returns/{return_id}")
async def get_return_detail(return_id: str):
    """Detalle de una devolución específica."""
    data = await supabase_service.get_return_detail(return_id)
    if not data:
        raise HTTPException(status_code=404, detail="Devolución no encontrada.")
    return data


@router.get("/usage/sessions")
async def list_usage_sessions(limit: int = 100):
    """Coste (tokens) y latencia agregados por sesión, con cliente/pedido asociados.

    Ver backend/agents/usage_tracking.py para de dónde sale cada fila.
    """
    sessions = await usage_service.get_usage_by_session(limit=limit)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/usage/sessions/{thread_id}")
async def get_usage_session_detail(thread_id: str):
    """Detalle petición a petición (tokens/latencia) de una sesión concreta."""
    requests = await usage_service.get_usage_detail(thread_id)
    return {"thread_id": thread_id, "requests": requests, "count": len(requests)}


@router.get("/observability")
async def get_observability_links():
    """Enlaces al dashboard de LangFuse para monitorizar gasto por sesión/cliente.

    Complementa el dashboard propio (usage/sessions arriba): LangFuse ya
    trackea tokens/coste por `langfuse_session_id` y `langfuse_user_id`
    (ver with_langfuse en backend/services/observability.py), así que este
    endpoint enlaza a su dashboard en vez de reimplementar esa agregación.
    """
    return observability.langfuse_links()
