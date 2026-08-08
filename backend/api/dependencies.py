"""Dependencias compartidas para los routers de FastAPI."""

from backend.agents.graph import get_return_graph


async def get_graph():
    """Devuelve el grafo LangGraph compilado (singleton)."""
    return await get_return_graph()
