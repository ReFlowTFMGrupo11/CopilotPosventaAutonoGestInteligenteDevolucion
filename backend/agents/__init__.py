"""
Sistema multi-agente de devoluciones basado en LangGraph.

Expone el grafo compilado y las funciones auxiliares para interactuar
con él desde la capa de API (FastAPI, CLI, tests, etc.).
"""

# build_return_graph: construye y compila el grafo desde cero cada vez que se llama.
# get_return_graph: devuelve un grafo singleton (lo crea solo la primera vez).
from backend.agents.graph import build_return_graph, get_return_graph
from backend.agents.state import ReturnState

# Fija qué símbolos son "públicos" al importar el paquete backend.agents.
__all__ = [
    "ReturnState",
    "build_return_graph",
    "get_return_graph",
]
