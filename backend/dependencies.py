"""
backend/dependencies.py
==========================
Providers de FastAPI `Depends()`. El grafo de LangGraph ya es un singleton
perezoso a nivel de módulo (backend.agents.graph.get_return_graph()); aquí
solo se envuelve en un provider para poder inyectarlo en las rutas y
sustituirlo en tests con `app.dependency_overrides[...]`.

`pending_admin` es el registro (en memoria, por proceso) de conversaciones
pausadas por `interrupt()` a la espera de que un administrador las apruebe
o rechace: `{thread_id: payload_del_interrupt}`. Vive en `app.state` (no en
una tabla de Supabase) porque, en este proyecto, `create_return_record` solo
se llama DESPUÉS de resolver el HITL (ver backend/agents/nodes/resolution.py),
así que no hay ninguna fila en `return_requests` que consultar mientras el
grafo está pausado — la única fuente de verdad de "qué está pendiente" es el
propio checkpointer de LangGraph. Este diccionario es solo una caché de
lectura rápida para el panel de administración: es el estado del grafo
(vía `graph.aget_state()`), no este dict, quien decide de verdad si un
`thread_id` sigue pausado.
"""

from fastapi import Request

from backend.agents.graph import get_return_graph


async def get_graph(request: Request):
    """Devuelve el grafo compilado (singleton), cacheado también en app.state para tests."""
    if getattr(request.app.state, "graph", None) is None:
        request.app.state.graph = await get_return_graph()
    return request.app.state.graph


def get_pending_store(request: Request) -> dict:
    """Devuelve (creándolo si hace falta) el dict de devoluciones pendientes de HITL."""
    if not hasattr(request.app.state, "pending_admin"):
        request.app.state.pending_admin = {}
    return request.app.state.pending_admin
