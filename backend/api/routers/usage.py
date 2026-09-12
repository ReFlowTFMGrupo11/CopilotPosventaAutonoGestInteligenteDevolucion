"""Router de coste/uso de LLM: dashboard propio de tokens y latencia por sesión.

Extraído de ``routers/admin.py`` porque su único consumidor real es la
pestaña de Costes del frontend (``frontend/pages/2_Costes.py``), no el panel
de administración (HITL, aprobar/rechazar, listar devoluciones) — cada
página del frontend tiene ahora un router propio 1:1 (ver
docs/defensaTFM/defenderFastAPI.md): ``chat.py`` -> ``Chat.py``,
``admin.py`` -> ``1_Admin.py``, ``usage.py`` -> ``2_Costes.py``.

Prefijo ``/api/admin`` conservado (no ``/api/usage``): sigue siendo
funcionalidad administrativa/interna por naturaleza (expone coste y tokens
por sesión), solo cambia en qué fichero vive el código — la URL pública no
cambia, así que ``frontend/lib/api.py`` no necesita ningún ajuste.
"""

from fastapi import APIRouter

from backend.services import usage_service

router = APIRouter(prefix="/api/admin", tags=["usage"])


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
