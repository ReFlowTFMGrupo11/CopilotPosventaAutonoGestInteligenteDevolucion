"""
Grafo de devoluciones – Orquestación LangGraph.

Define el ``StateGraph`` que conecta los tres agentes:
  Triaje → Fetch datos → Evaluador → Resolución/Rechazo
con soporte HITL para reembolsos > 100 €.
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from backend.agents.policy_agent import policy_evaluator_agent
from backend.agents.resolution_agent import (
    hitl_admin_node,
    rejection_agent,
    resolution_agent,
)
from backend.agents.state import ReturnState
from backend.agents.triage_agent import fetch_order_data, triage_agent

logger = logging.getLogger(__name__)


# ── Funciones de enrutamiento (aristas condicionales) ──────────────────────


def route_after_triage(state: ReturnState) -> Literal["fetch_order_data", "triage"]:
    """Decide si avanzar a consultar datos o seguir conversando.

    Avanza cuando tenemos ``order_id`` y al menos un artículo a devolver.
    """
    order_id = state.get("order_id")
    items = state.get("items_to_return", [])

    if order_id and items:
        return "fetch_order_data"

    # Falta información → volver a conversar con el usuario
    return "triage"


def route_after_fetch(state: ReturnState) -> Literal["evaluator", "triage"]:
    """Decide si avanzar al evaluador o volver al triaje (si hubo error)."""
    if state.get("error"):
        return "triage"
    return "evaluator"


def route_after_evaluator(state: ReturnState) -> Literal["resolver", "reject"]:
    """Decide si la devolución es elegible o debe rechazarse."""
    if state.get("is_eligible"):
        return "resolver"
    return "reject"


# ── Construcción del grafo ─────────────────────────────────────────────────


def build_return_graph(checkpointer=None):
    """Construye y compila el grafo de devoluciones.

    Args:
        checkpointer: Checkpointer de LangGraph para persistencia.
            Si es ``None``, se usa ``InMemorySaver`` (solo para desarrollo).

    Returns:
        El grafo compilado, listo para ``invoke()`` o ``stream_events()``.
    """
    if checkpointer is None:
        checkpointer = InMemorySaver()

    graph = StateGraph(ReturnState)

    # ── Nodos ──────────────────────────────────────────────────────────
    graph.add_node("triage", triage_agent)
    graph.add_node("fetch_order_data", fetch_order_data)
    graph.add_node("evaluator", policy_evaluator_agent)
    graph.add_node("resolver", resolution_agent)
    graph.add_node("reject", rejection_agent)
    graph.add_node("hitl_admin", hitl_admin_node)

    # ── Aristas ────────────────────────────────────────────────────────
    # Entrada → Triaje
    graph.add_edge(START, "triage")

    # Triaje → (fetch_order_data | triage)
    graph.add_conditional_edges("triage", route_after_triage)

    # Fetch datos → (evaluator | triage)
    graph.add_conditional_edges("fetch_order_data", route_after_fetch)

    # Evaluador → (resolver | reject)
    graph.add_conditional_edges("evaluator", route_after_evaluator)

    # resolver usa Command() para ir a hitl_admin o __end__
    # reject → fin
    graph.add_edge("reject", END)

    # hitl_admin → fin
    graph.add_edge("hitl_admin", END)

    # ── Compilar con checkpointer ──────────────────────────────────────
    compiled = graph.compile(checkpointer=checkpointer)

    logger.info("Grafo de devoluciones compilado correctamente.")
    return compiled


# ── Instancia por defecto (desarrollo) ─────────────────────────────────────

_default_graph = None


def get_return_graph():
    """Devuelve el grafo singleton para desarrollo."""
    global _default_graph
    if _default_graph is None:
        _default_graph = build_return_graph()
    return _default_graph
