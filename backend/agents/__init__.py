"""
Sistema multi-agente de devoluciones basado en LangGraph.

Expone el grafo compilado y las funciones auxiliares para interactuar
con él desde la capa de API (FastAPI, CLI, tests, etc.).
"""

from backend.agents.graph import build_return_graph, get_return_graph
from backend.agents.state import ReturnState

__all__ = [
    "ReturnState",
    "build_return_graph",
    "get_return_graph",
]
