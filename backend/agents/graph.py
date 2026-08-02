"""
Grafo de devoluciones – Orquestación LangGraph.

Define el ``StateGraph`` que conecta los tres agentes:
  Triaje → Fetch datos → Evaluador → Resolución/Rechazo
con soporte HITL para reembolsos > 100 €.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg_pool import AsyncConnectionPool

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


def route_after_triage(state: ReturnState) -> Literal["fetch_order_data", "__end__"]:
    """Decide si avanzar a consultar datos o terminar el turno.

    Avanza cuando tenemos ``order_id`` y al menos un artículo a devolver.
    Si falta información, el turno termina (END) y el caller re-invoca
    el grafo con el siguiente mensaje del usuario. El checkpointer
    preserva el estado entre turnos.
    """
    order_id = state.get("order_id")
    items = state.get("items_to_return", [])

    if order_id and items:
        return "fetch_order_data"

    # Falta información → terminar turno; el usuario responderá
    return "__end__"


def route_after_fetch(state: ReturnState) -> Literal["evaluator", "__end__"]:
    """Decide si avanzar al evaluador o terminar turno (si hubo error).

    Si el pedido no se encontró, el agente de triaje ya dejó un mensaje
    pidiendo corrección. Terminamos el turno para que el usuario responda.
    """
    if state.get("error"):
        return "__end__"
    return "evaluator"


def route_after_evaluator(state: ReturnState) -> Literal["resolver", "reject"]:
    """Decide si la devolución es elegible o debe rechazarse."""
    if state.get("is_eligible"):
        return "resolver"
    return "reject"


# ── Construcción del grafo ─────────────────────────────────────────────────


async def build_return_graph(checkpointer=None):
    """Construye y compila el grafo de devoluciones.

    Args:
        checkpointer: Checkpointer de LangGraph para persistencia.
            Si es ``None``, se crea un ``AsyncPostgresSaver`` conectado a la
            base de datos de Supabase (variable ``SUPABASE_DB_URL``).

    Returns:
        El grafo compilado, listo para ``ainvoke()`` o ``astream()``.
    """
    if checkpointer is None:
        db_url = os.getenv("SUPABASE_DB_URL")
        if db_url:
            try:
                # Crear pool async con open=False para evitar deprecation warning
                pool = AsyncConnectionPool(db_url, min_size=1, max_size=3, open=False)
                # Abrir explícitamente (establece las conexiones al DB)
                await pool.open()
                checkpointer = AsyncPostgresSaver(pool)
                logger.info("Checkpointer: AsyncPostgresSaver (persistente).")
            except Exception as exc:
                logger.warning(
                    "No se pudo conectar a PostgreSQL (%s). Usando InMemorySaver.", exc
                )
                checkpointer = InMemorySaver()
        else:
            logger.warning("SUPABASE_DB_URL no configurada. Usando InMemorySaver (no persistente).")
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

    # Triaje → (fetch_order_data | END)
    graph.add_conditional_edges("triage", route_after_triage)

    # Fetch datos → (evaluator | END)
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


async def get_return_graph():
    """Devuelve el grafo singleton para desarrollo."""
    global _default_graph
    if _default_graph is None:
        _default_graph = await build_return_graph()
    return _default_graph
