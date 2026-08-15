"""Dependencias compartidas para los routers de FastAPI.

Usan `Request.app.state` para cachear el grafo, lo que permite
sustituirlo en tests con `app.dependency_overrides`.
"""

from fastapi import Request

from backend.agents.graph import get_return_graph


async def get_graph(request: Request):
    """Devuelve el grafo compilado (singleton cacheado en app.state)."""
    if getattr(request.app.state, "graph", None) is None:
        request.app.state.graph = await get_return_graph()
    return request.app.state.graph
