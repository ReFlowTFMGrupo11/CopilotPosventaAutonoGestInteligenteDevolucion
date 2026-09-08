"""
Grafo de devoluciones – Orquestación LangGraph.

Define el ``StateGraph`` que conecta los tres agentes:
  Triaje → Fetch datos → Evaluador → Resolución/Rechazo
con soporte HITL para reembolsos > 100 €.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 FRONTERA  DETERMINISTA  vs  LLM  en este módulo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 TODO el enrutamiento del grafo es 100% DETERMINISTA.
 El LLM nunca decide qué nodo se ejecuta a continuación.

 Guards deterministas (funciones route_*):

   route_after_triage:
     → fetch_order_data  si hay order_number (pedido identificado).
     → __end__           si falta order_number (esperar al cliente).

   route_after_fetch  (Guard B principal del flujo):
     → evaluator   si y solo si:
                     - No hay error de pedido.
                     - items_to_return tiene al menos 1 ítem con condition válida
                       (no vacía, no "unknown")  ← _has_valid_items_to_return
                     - Hay reason + reason_category informados.
                       ← _has_reason_data
     → __end__     en cualquier otro caso (pedir más datos al cliente).

   route_after_evaluator:
     → resolver    si is_eligible=True o needs_admin_approval=True.
     → reject      si la política lo rechaza claramente.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg_pool import AsyncConnectionPool

from backend.config import get_settings

if sys.platform == "win32":
    # psycopg en modo async no soporta el ProactorEventLoop (el por defecto en
    # asyncio en Windows desde Python 3.8); necesita SelectorEventLoop. Sin esto,
    # AsyncConnectionPool falla al conectar aunque las credenciales sean correctas.
    #
    # OJO: esto solo tiene efecto si el loop de asyncio se crea DESPUÉS de
    # importar este módulo. Sirviendo la API con `uvicorn backend.api.main:app`
    # (sin --reload) NO basta: uvicorn crea su loop en Server.run() antes de
    # importar la app, así que esta policy llega tarde y AsyncConnectionPool
    # tarda 30s reintentando antes de caer a InMemorySaver. Para la API,
    # arrancar con `python -m backend.api.run` (ver ese módulo para el
    # porqué) en vez de invocar uvicorn directamente.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from backend.agents.nodes.evaluator import evaluator_agent
from backend.agents.nodes.resolution import (
    rejection_agent,
    resolution_agent,
)
from backend.agents.state import ReturnState
from backend.agents.nodes.triage import fetch_order_data, triage_agent
from backend.services import observability

logger = logging.getLogger(__name__)

# ── Estado del checkpointer (para /health y /api/admin/observability) ──────
#
# build_return_graph() puede degradar en silencio a InMemorySaver si Postgres
# no está disponible o SUPABASE_DB_URL no está configurada. Antes, la única
# señal de esa degradación era un logger.warning en consola — invisible fuera
# de los logs del proceso, y grave porque el checkpointer sostiene el estado
# multi-turno y las pausas HITL (interrupt()). Este módulo guarda el último
# resultado para que main.py/admin.py puedan exponerlo.
_checkpointer_status: dict[str, Any] = {
    "backend": None,
    "persistent": None,
    "error": None,
}


def get_checkpointer_status() -> dict[str, Any]:
    """Último estado conocido del checkpointer (ver `_checkpointer_status`).

    Devuelve valores ``None`` si todavía no se ha llamado a
    ``build_return_graph()`` en este proceso.
    """
    return dict(_checkpointer_status)


# ── Funciones de enrutamiento (aristas condicionales) ──────────────────────


def _has_valid_items_to_return(state: ReturnState) -> bool:
    """True si hay al menos un item y todos tienen condition válida."""
    items_to_return = state.get("items_to_return") or []
    if not items_to_return:
        return False

    for item in items_to_return:
        condition = (item.get("condition") or "").strip().lower()
        if not condition or condition == "unknown":
            return False
    return True


def _has_reason_data(state: ReturnState) -> bool:
    """True si hay motivo y categoría de motivo informados."""
    reason = (state.get("reason") or "").strip()
    reason_category = (state.get("reason_category") or "").strip()
    return bool(reason and reason_category)


def _items_confirmed(state: ReturnState) -> bool:
    """True si el cliente ya confirmó explícitamente el estado inferido.

    Red de seguridad frente a la interpretación semántica (no basada en
    keywords) de ``condition`` en triage.py: no se avanza al Evaluador con
    una condición que el LLM dedujo pero el cliente no ha ratificado.
    """
    return bool(state.get("items_confirmed"))


def route_after_triage(state: ReturnState) -> Literal["fetch_order_data", "__end__"]:
    """Decide si avanzar a consultar datos o terminar el turno.

    Avanza en cuanto tenemos ``order_number``: primero para mostrarle al
    cliente los artículos del pedido (``order_details`` aún vacío), y de
    nuevo una vez que ya sabe qué artículo devolver (``items_to_return``
    relleno) para evaluar la devolución. Si solo tenemos el pedido pero
    todavía no el artículo, el turno termina (END) a la espera de que el
    cliente responda; el checkpointer preserva el estado entre turnos.
    """
    order_number = state.get("order_number")
    if not order_number:
        return "__end__"
    if not state.get("order_details") or state.get("items_to_return"):
        return "fetch_order_data"
    return "__end__"


def route_after_fetch(state: ReturnState) -> Literal["evaluator", "__end__"]:
    """Decide si avanzar al evaluador o terminar turno.

    Termina el turno si hubo un error (pedido no encontrado) o si todavía
    no sabemos qué artículo quiere devolver el cliente (fetch_order_data ya
    ha dejado el mensaje preguntándolo).
    """
    if state.get("error"):
        return "__end__"
    if not _has_valid_items_to_return(state):
        return "__end__"
    if not _has_reason_data(state):
        return "__end__"
    if not _items_confirmed(state):
        return "__end__"
    return "evaluator"


def route_after_evaluator(state: ReturnState) -> Literal["resolver", "reject"]:
    """Decide si al menos un artículo es elegible o si hay que rechazar todo.

    Un pedido con elegibilidad mixta (algunos artículos sí, otros no) avanza
    a ``resolver``, que se encarga de procesar solo los elegibles y explicar
    al cliente por qué los demás no proceden. También avanza si el Evaluador
    marcó ``needs_admin_approval`` (reservado para una futura comprobación
    determinista adicional; hoy ``evaluator_agent`` no lo fija, así
    que se comporta como ``False``). Solo se rechaza el turno completo
    cuando NINGÚN artículo es elegible.
    """
    if state.get("any_eligible") or state.get("needs_admin_approval"):
        return "resolver"
    return "reject"


# ── Construcción del grafo ─────────────────────────────────────────────────


def _fail_or_degrade(message: str, *, error: str, is_production: bool) -> None:
    """Decide qué hacer cuando el checkpointer persistente no está disponible.

    - En production: RIESGO REAL, no solo un warning de consola. El
      checkpointer sostiene el estado multi-turno Y las pausas HITL
      (interrupt() en resolution.py) — perderlo en producción significa que
      un reinicio del proceso borra conversaciones a medias y aprobaciones
      de reembolso pendientes sin ningún aviso al admin. Por eso aquí se
      frena el arranque con una excepción explícita en vez de degradar en
      silencio (mismo criterio "fail-open solo si es seguro" que
      observability.py aplica a LangFuse — pero el checkpointer NO es
      opcional como LangFuse, es el sustento del propio flujo de negocio).
    - Fuera de production (development/staging/tests): se mantiene el
      comportamiento anterior (degradar a InMemorySaver con un warning),
      para no romper el flujo local sin Postgres levantado.

    En ambos casos se registra el estado en `_checkpointer_status` (para
    `/health` y `/api/admin/observability`) y, si LangFuse está configurado,
    un evento `level="ERROR"` — antes este módulo no emitía ningún evento de
    error hacia LangFuse, solo hacia el log de consola.
    """
    _checkpointer_status.update(backend="memory", persistent=False, error=error)
    lf = observability.get_langfuse()
    if lf is not None:
        try:
            lf.create_event(
                name="checkpointer_degraded",
                level="ERROR",
                metadata={"error": error, "environment": get_settings().environment},
            )
        except Exception as exc:  # observabilidad nunca debe tirar abajo el arranque
            logger.warning(
                "No se pudo registrar checkpointer_degraded en LangFuse: %s", exc
            )

    if is_production:
        raise RuntimeError(
            f"{message} Checkpointer persistente requerido en production "
            "(ENVIRONMENT=production) — no se degrada a InMemorySaver. "
            "Configura SUPABASE_DB_URL o revisa la conectividad a Postgres."
        )
    logger.warning("%s Usando InMemorySaver (no persistente).", message)


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
        settings = get_settings()
        is_production = settings.environment == "production"
        db_url = settings.supabase_db_url
        if db_url:
            try:
                # autocommit=True y prepare_threshold=0: mismo patrón que usa
                # AsyncPostgresSaver.from_conn_string() internamente. Sin autocommit,
                # checkpointer.setup() falla porque ejecuta CREATE INDEX CONCURRENTLY,
                # que Postgres no permite dentro de un bloque de transacción.
                pool = AsyncConnectionPool(
                    db_url,
                    min_size=1,
                    max_size=3,
                    open=False,
                    kwargs={"autocommit": True, "prepare_threshold": 0},
                )
                # Abrir explícitamente (establece las conexiones al DB)
                await pool.open()
                checkpointer = AsyncPostgresSaver(pool)
                await checkpointer.setup()
                logger.info("Checkpointer: AsyncPostgresSaver (persistente).")
                _checkpointer_status.update(
                    backend="postgres", persistent=True, error=None
                )
            except Exception as exc:
                _fail_or_degrade(
                    f"No se pudo conectar a PostgreSQL ({exc}).",
                    error=str(exc),
                    is_production=is_production,
                )
                checkpointer = InMemorySaver()
        else:
            _fail_or_degrade(
                "SUPABASE_DB_URL no configurada.",
                error="SUPABASE_DB_URL no configurada.",
                is_production=is_production,
            )
            checkpointer = InMemorySaver()

    graph = StateGraph(ReturnState)

    # ── Nodos ──────────────────────────────────────────────────────────
    graph.add_node("triage", triage_agent)
    graph.add_node("fetch_order_data", fetch_order_data)
    graph.add_node("evaluator", evaluator_agent)
    graph.add_node("resolver", resolution_agent)
    graph.add_node("reject", rejection_agent)

    # ── Aristas ────────────────────────────────────────────────────────
    # Entrada → Triaje
    graph.add_edge(START, "triage")

    # Triaje → (fetch_order_data | END)
    graph.add_conditional_edges("triage", route_after_triage)

    # Fetch datos → (evaluator | END)
    graph.add_conditional_edges("fetch_order_data", route_after_fetch)

    # Evaluador → (resolver | reject)
    graph.add_conditional_edges("evaluator", route_after_evaluator)

    # resolver usa Command(goto="__end__") siempre: el HITL (interrupt() +
    # Command(resume=...)) se resuelve dentro del propio nodo "resolver", no
    # saltando a otro nodo — no hay arista distinta que declarar aquí.
    # reject → fin
    graph.add_edge("reject", END)

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
