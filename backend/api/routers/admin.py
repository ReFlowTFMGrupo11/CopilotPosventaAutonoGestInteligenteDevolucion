"""Router admin: panel de gestión, HITL (Human-in-the-Loop) y consultas usadas
por el panel de administración del frontend (``frontend/pages/1_Admin.py``).

Dos ``APIRouter`` en este mismo fichero, no uno: ``router`` (prefijo
``/api/admin``) para las acciones propias de administración, y
``public_router`` (prefijo ``/api``, sin cambiar sus rutas históricas) para
``get_order``/``get_customer_history``/``get_stats`` — movidos aquí desde el
extinto ``routers/orders.py`` porque el ÚNICO consumidor real de esos tres
endpoints es el panel de admin (búsqueda de pedido + KPIs superiores en
``1_Admin.py``), nunca el chat de cliente. Mantener las URLs (``/api/orders/...``,
``/api/stats``) intactas evita tocar tests, `README.md` y `frontend/lib/api.py`
que ya las referencian; lo que cambia es solo en qué fichero vive el código,
no el contrato HTTP. Ver docs/defensaTFM/defenderFastAPI.md.

Los endpoints de coste (``/usage/sessions*``) NO están aquí — viven en
``routers/usage.py``, porque su único consumidor es la pestaña de Costes
(``2_Costes.py``), no el panel de admin.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from langgraph.types import Command

from backend.agents.graph import get_checkpointer_status
from backend.api.dependencies import get_graph
from backend.api.schemas import (
    AdminDecisionRequest,
    OrderDetailResponse,
    ReturnHistoryResponse,
)
from backend.config import get_settings
from backend.services import observability, orders_service, returns_service

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Prefijo "/api" (no "/api/admin"): mismas URLs que tenía routers/orders.py,
# ver docstring del módulo.
public_router = APIRouter(prefix="/api", tags=["orders"])

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
    data = await returns_service.list_pending_approvals()
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
    data = await returns_service.list_returns(status=status, limit=limit)
    return {"returns": data, "count": len(data)}


@router.get("/returns/{return_id}")
async def get_return_detail(return_id: str):
    """Detalle de una devolución específica."""
    data = await returns_service.get_return_detail(return_id)
    if not data:
        raise HTTPException(status_code=404, detail="Devolución no encontrada.")
    return data


@router.get("/observability")
async def get_observability_links():
    """Enlaces al dashboard de LangFuse + estado del checkpointer del grafo.

    Los enlaces de LangFuse complementan el dashboard propio de coste
    (``routers/usage.py::list_usage_sessions``): LangFuse ya trackea
    tokens/coste por `langfuse_session_id` y `langfuse_user_id` (ver
    with_langfuse en backend/services/observability.py), así que este
    endpoint enlaza a su dashboard en vez de reimplementar esa agregación.

    `checkpointer` (ver backend/agents/graph.py) se incluye aquí, no solo en
    `/health`, para que el panel de admin pueda mostrar un aviso visible si
    el grafo está corriendo sobre InMemorySaver — antes esa degradación solo
    se veía en los logs de consola del proceso.
    """
    return {
        **observability.get_langfuse_links(),
        "checkpointer": get_checkpointer_status(),
    }


# ── Endpoints movidos desde el extinto routers/orders.py (ver docstring del
#    módulo) — mismas URLs, mismo comportamiento, solo cambia el fichero ──


@public_router.get("/orders/{order_id}", response_model=OrderDetailResponse)
async def get_order(order_id: str):
    """Detalle de un pedido (productos, cliente, fechas)."""
    try:
        result = await orders_service.get_order_details(order_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Pedido no encontrado: {exc}")
    return result


@public_router.get(
    "/customers/{customer_id}/history", response_model=ReturnHistoryResponse
)
async def get_customer_history(customer_id: str):
    """Historial de devoluciones de un cliente."""
    try:
        result = await returns_service.get_customer_return_history(customer_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Cliente no encontrado: {exc}")
    return result


@public_router.get("/stats")
async def get_stats():
    """KPIs generales del sistema de devoluciones."""
    return await returns_service.get_return_stats()
