"""
Grafo de devoluciones – Orquestación LangGraph.

Define el ``StateGraph`` que conecta los tres agentes:
  Triaje → Fetch datos → Evaluador → Resolución/Rechazo
con soporte HITL para reembolsos > 100 €.
"""

from __future__ import annotations

import logging
import os
# Literal: restringe el tipo devuelto a un conjunto fijo de strings, usado
# aquí para anotar los posibles destinos de cada función de enrutamiento.
from typing import Literal

# InMemorySaver: checkpointer que guarda el estado del grafo en memoria RAM
# (se pierde al reiniciar el proceso) — usado como red de seguridad.
from langgraph.checkpoint.memory import InMemorySaver
# AsyncPostgresSaver: checkpointer que persiste el estado en PostgreSQL,
# permitiendo recuperar conversaciones entre reinicios del servidor.
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
# END/START: nodos especiales que marcan el principio y el fin del grafo.
# StateGraph: clase principal para construir el grafo con un TypedDict de estado.
from langgraph.graph import END, START, StateGraph
# Pool de conexiones asíncronas a PostgreSQL, reutilizado por el checkpointer.
from psycopg_pool import AsyncConnectionPool

# Cada import trae la función de nodo (agente) que luego se registra en el
# grafo más abajo con graph.add_node("nombre", función). El nombre del
# archivo de origen indica qué agente implementa: policy.py = Evaluador,
# resolution.py = Resolución (+ HITL + rechazo), triage.py = Triaje.

# policy_evaluator_agent: nodo del Agente Evaluador de Políticas (RAG +
# reglas de elegibilidad); ver backend/agents/nodes/policy.py.
from backend.agents.nodes.policy import policy_evaluator_agent
# Los tres nodos del Agente de Resolución viven en el mismo archivo porque
# comparten prompts y el umbral HITL_REFUND_THRESHOLD:
#   - resolution_agent: genera etiqueta, registra la devolución y decide
#     si hace falta pausar para aprobación humana (interrupt()).
#   - hitl_admin_node: punto de entrada del grafo al que se llega tras la
#     aprobación/rechazo del administrador.
#   - rejection_agent: redacta el mensaje de rechazo cuando la devolución
#     no es elegible (rama que viene directamente del Evaluador, no de HITL).
from backend.agents.nodes.resolution import (
    hitl_admin_node,
    rejection_agent,
    resolution_agent,
)
# ReturnState: el TypedDict que define el estado compartido entre todos los
# nodos (ver backend/models/state.py, re-exportado aquí para compatibilidad).
from backend.agents.state import ReturnState
# triage_agent: primer nodo del grafo (saluda, extrae order_id/motivo/artículos).
# fetch_order_data: nodo auxiliar que consulta el pedido en Supabase una vez
# triage_agent ya tiene el order_id; ambos viven en triage.py porque el
# segundo depende directamente de los datos que extrae el primero.
from backend.agents.nodes.triage import fetch_order_data, triage_agent

# Logger propio de este módulo: los mensajes se identifican como venidos de
# "backend.agents.graph" (útil para filtrar logs por origen).
logger = logging.getLogger(__name__)


# ── Funciones de enrutamiento (aristas condicionales) ──────────────────────
# Cada función recibe el estado actual y devuelve el NOMBRE del siguiente
# nodo al que saltar; LangGraph las usa como "aristas condicionales".


def route_after_triage(state: ReturnState) -> Literal["fetch_order_data", "__end__"]:
    """Decide si avanzar a consultar datos o terminar el turno.

    Avanza cuando tenemos ``order_id`` y al menos un artículo a devolver.
    Si falta información, el turno termina (END) y el caller re-invoca
    el grafo con el siguiente mensaje del usuario. El checkpointer
    preserva el estado entre turnos.
    """
    order_id = state.get("order_id")
    items = state.get("items_to_return", [])

    # Solo se avanza cuando ya se tienen los dos datos imprescindibles para
    # poder consultar el pedido; si falta cualquiera de los dos, se corta
    # el turno aquí y se espera a que el cliente aporte lo que falta.
    if order_id and items:
        return "fetch_order_data"

    # Falta información → terminar turno; el usuario responderá
    return "__end__"


def route_after_fetch(state: ReturnState) -> Literal["evaluator", "__end__"]:
    """Decide si avanzar al evaluador o terminar turno (si hubo error).

    Si el pedido no se encontró, el agente de triaje ya dejó un mensaje
    pidiendo corrección. Terminamos el turno para que el usuario responda.
    """
    # fetch_order_data (triage.py) escribe "error" en el estado si el
    # order_id no existe o la consulta falló; en ese caso no tiene sentido
    # seguir al evaluador con datos incompletos.
    if state.get("error"):
        return "__end__"
    return "evaluator"


def route_after_evaluator(state: ReturnState) -> Literal["resolver", "reject"]:
    """Decide si la devolución es elegible o debe rechazarse."""
    # is_eligible lo rellena policy_evaluator_agent tras parsear el JSON del LLM.
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
    # Si el llamante no pasa un checkpointer explícito (p. ej. en tests, que
    # suelen pasar InMemorySaver), se intenta montar uno persistente en
    # PostgreSQL; solo si eso falla se recurre a memoria.
    if checkpointer is None:
        db_url = os.getenv("SUPABASE_DB_URL")
        if db_url:
            try:
                # Crear pool async con open=False para evitar deprecation warning
                # open=False: crea el objeto del pool sin abrir aún las
                # conexiones; se abre explícitamente justo después con
                # await pool.open(), que es la forma recomendada en la
                # versión actual de psycopg_pool (evita un warning de
                # apertura implícita en el constructor).
                pool = AsyncConnectionPool(db_url, min_size=1, max_size=3, open=False)
                # Abrir explícitamente (establece las conexiones al DB)
                await pool.open()
                checkpointer = AsyncPostgresSaver(pool)
                logger.info("Checkpointer: AsyncPostgresSaver (persistente).")
            except Exception as exc:
                # Si Postgres no está disponible (credenciales erróneas, DB
                # caída...), se registra el aviso pero el código sigue sin
                # asignar checkpointer aquí (línea comentada abajo), así que
                # más adelante quedaría en None si no se soluciona.
                logger.warning(
                    "No se pudo conectar a PostgreSQL (%s). Usando InMemorySaver.", exc
                )
                #checkpointer = InMemorySaver()
        else:
            # Sin SUPABASE_DB_URL configurada, se usa memoria directamente:
            # funciona para probar el grafo, pero el historial de
            # conversación se pierde si el proceso se reinicia.
            logger.warning("SUPABASE_DB_URL no configurada. Usando InMemorySaver (no persistente).")
            checkpointer = InMemorySaver()

    # Se instancia el grafo indicando qué TypedDict define su estado
    # compartido; LangGraph usa esto para saber qué claves existen y cómo
    # fusionarlas (p. ej. "messages" usa el reducer add_messages).
    graph = StateGraph(ReturnState)

    # ── Nodos ──────────────────────────────────────────────────────────
    # Cada add_node asocia un nombre de nodo (string) con la función
    # async que se ejecuta cuando el grafo llega a ese punto.
    graph.add_node("triage", triage_agent)
    graph.add_node("fetch_order_data", fetch_order_data)
    graph.add_node("evaluator", policy_evaluator_agent)
    graph.add_node("resolver", resolution_agent)
    graph.add_node("reject", rejection_agent)
    graph.add_node("hitl_admin", hitl_admin_node)

    # ── Aristas ────────────────────────────────────────────────────────
    # Entrada → Triaje
    # Toda invocación del grafo empieza siempre por el nodo "triage".
    graph.add_edge(START, "triage")

    # Triaje → (fetch_order_data | END)
    # add_conditional_edges: en vez de ir siempre al mismo nodo siguiente,
    # se llama a la función de enrutamiento para decidir dinámicamente.
    graph.add_conditional_edges("triage", route_after_triage)

    # Fetch datos → (evaluator | END)
    graph.add_conditional_edges("fetch_order_data", route_after_fetch)

    # Evaluador → (resolver | reject)
    graph.add_conditional_edges("evaluator", route_after_evaluator)

    # resolver usa Command() para ir a hitl_admin o __end__
    # reject → fin
    # "resolver" no tiene arista aquí porque decide su propio destino
    # devolviendo un Command(goto=...) desde dentro de resolution_agent.
    graph.add_edge("reject", END)

    # hitl_admin → fin
    graph.add_edge("hitl_admin", END)

    # ── Compilar con checkpointer ──────────────────────────────────────
    # compile(): valida la estructura del grafo (nodos/aristas coherentes)
    # y lo deja listo para ejecutarse; el checkpointer se ata aquí para que
    # cada ainvoke() guarde/recupere el estado automáticamente por thread_id.
    compiled = graph.compile(checkpointer=checkpointer)

    logger.info("Grafo de devoluciones compilado correctamente.")
    return compiled


# ── Instancia por defecto (desarrollo) ─────────────────────────────────────

# Variable de módulo usada como caché del grafo "por defecto", para no
# reconstruirlo (ni reabrir el pool de PostgreSQL) en cada llamada.
_default_graph = None


async def get_return_graph():
    """Devuelve el grafo singleton para desarrollo."""
    global _default_graph
    if _default_graph is None:
        _default_graph = await build_return_graph()
    return _default_graph
