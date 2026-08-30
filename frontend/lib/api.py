"""Cliente HTTP para la API de ReFlow (backend FastAPI en backend/api).

Cada función mapea 1:1 con un endpoint del backend. Sin abstracciones
extra: si un endpoint cambia, se cambia aquí y ya está.
"""

import json
import os
from typing import Iterator

import httpx
from dotenv import load_dotenv

# override=True: en máquinas con conda activado automáticamente, conda ya deja
# SSL_CERT_FILE puesto (a veces con una ruta rota) antes de que arranque Python;
# sin override, load_dotenv() no lo sustituiría por el valor bueno de .env.
load_dotenv(override=True)

# Configurable vía env var (default = localhost, para no romper el flujo de
# desarrollo local con start_all_mac.sh/start_all.sh). Necesario para
# contenedores: en Docker/ECS "localhost" dentro del contenedor del frontend
# NO es el backend (son procesos/tasks distintos) — hay que apuntar a la URL
# real del servicio backend (DNS interno de ECS Service Connect, o la URL
# pública del ALB). Ver docs/deployment_aws_ecs_fargate.md.
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")


def health() -> bool:
    """True si el backend responde a GET /health."""
    try:
        return httpx.get(f"{API_BASE}/health", timeout=3).status_code == 200
    except httpx.RequestError:
        return False


def new_chat() -> str:
    """Llama a POST /api/chat/new para abrir una sesión de conversación nueva.

    Returns:
        El ``thread_id`` (str) generado para esta sesión.
    """
    r = httpx.post(f"{API_BASE}/api/chat/new", timeout=10)
    r.raise_for_status()
    return r.json()["thread_id"]


def stream_chat(
    thread_id: str,
    message: str,
    selected_item_ids: list[str] | None = None,
) -> Iterator[dict]:
    """Llama a POST /api/chat/stream y cede (yield) cada evento SSE tal como llega.

    Args:
        thread_id: Sesión de chat sobre la que se envía el mensaje.
        message: Texto del mensaje del usuario.
        selected_item_ids: Ids de los artículos del pedido seleccionados
            para devolver, si el usuario ya los ha elegido.

    Returns:
        Iterador de eventos (dict con al menos ``type`` y ``content``,
        p. ej. ``agent_step``, ``final``, ``awaiting_admin`` o ``error``).
    """
    with httpx.stream(
        "POST",
        f"{API_BASE}/api/chat/stream",
        json={
            "thread_id": thread_id,
            "message": message,
            "selected_item_ids": selected_item_ids,
        },
        timeout=120,
    ) as response:
        response.raise_for_status()
        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                raw, buffer = buffer.split("\n\n", 1)
                data = "".join(
                    line[len("data:") :].strip()
                    for line in raw.splitlines()
                    if line.startswith("data:")
                )
                if data:
                    yield json.loads(data)


def stats() -> dict:
    """Llama a GET /api/stats para obtener los KPIs generales de devoluciones.

    Returns:
        Dict con totales/tasa de aprobación (``total_returns``, ``approved``,
        ``rejected``, ``pending``, ``approval_rate``).
    """
    r = httpx.get(f"{API_BASE}/api/stats", timeout=10)
    r.raise_for_status()
    return r.json()


def pending_returns() -> list[dict]:
    """Llama a GET /api/admin/pending para listar devoluciones a la espera de aprobación HITL.

    Returns:
        Lista de devoluciones pendientes (dict por fila).
    """
    r = httpx.get(f"{API_BASE}/api/admin/pending", timeout=10)
    r.raise_for_status()
    return r.json().get("pending", [])


def list_returns(status: str = "") -> list[dict]:
    """Llama a GET /api/admin/returns para listar devoluciones, opcionalmente filtradas.

    Args:
        status: Estado por el que filtrar (``approved``, ``rejected``,
            ``pending_approval``). Vacío para no filtrar.

    Returns:
        Lista de devoluciones que cumplen el filtro (dict por fila).
    """
    params = {"status": status} if status else {}
    r = httpx.get(f"{API_BASE}/api/admin/returns", params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("returns", [])


def approve(
    thread_id: str, reason: str = "", override_refund_amount: float | None = None
) -> dict:
    """Llama a POST /api/admin/{thread_id}/approve para aprobar una devolución pendiente y reanudar el grafo.

    Args:
        thread_id: Sesión de chat cuya devolución se aprueba.
        reason: Motivo opcional que registra el administrador.
        override_refund_amount: Decisión "Edit" del HITL -- importe
            corregido en vez del calculado por el Evaluador. ``None``
            (por defecto) aprueba sin editar el importe.

    Returns:
        Dict con el resultado tras reanudar el grafo (``thread_id``,
        ``resolution``, ``tracking_number``, ``refund_amount``).
    """
    r = httpx.post(
        f"{API_BASE}/api/admin/{thread_id}/approve",
        json={"reason": reason, "override_refund_amount": override_refund_amount},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def reject(thread_id: str, reason: str = "") -> dict:
    """Llama a POST /api/admin/{thread_id}/reject para rechazar una devolución pendiente y reanudar el grafo.

    Args:
        thread_id: Sesión de chat cuya devolución se rechaza.
        reason: Motivo opcional que registra el administrador.

    Returns:
        Dict con el resultado tras reanudar el grafo (``thread_id``,
        ``resolution``).
    """
    r = httpx.post(
        f"{API_BASE}/api/admin/{thread_id}/reject", json={"reason": reason}, timeout=30
    )
    r.raise_for_status()
    return r.json()


def get_order(order_id: str) -> dict:
    """Llama a GET /api/orders/{order_id} para obtener el detalle de un pedido.

    Args:
        order_id: Identificador del pedido a consultar.

    Returns:
        Dict con los datos del pedido (productos, cliente, fechas).
    """
    r = httpx.get(f"{API_BASE}/api/orders/{order_id}", timeout=10)
    r.raise_for_status()
    return r.json()


def chat_state(thread_id: str) -> dict:
    """Llama a GET /api/chat/{thread_id}/state para leer el estado actual del grafo.

    Args:
        thread_id: Sesión de chat cuyo estado se consulta.

    Returns:
        Dict con el estado del grafo (agente actual, pedido, elegibilidad,
        resolución, artículos del pedido y si falta selección del cliente).
    """
    r = httpx.get(f"{API_BASE}/api/chat/{thread_id}/state", timeout=10)
    r.raise_for_status()
    return r.json()


def usage_sessions(limit: int = 100) -> list[dict]:
    """Llama a GET /api/admin/usage/sessions para listar el coste/latencia agregado por sesión.

    Args:
        limit: Número máximo de sesiones a devolver.

    Returns:
        Lista de sesiones con tokens, coste estimado y latencia agregados.
    """
    r = httpx.get(
        f"{API_BASE}/api/admin/usage/sessions", params={"limit": limit}, timeout=10
    )
    r.raise_for_status()
    return r.json().get("sessions", [])


def usage_session_detail(thread_id: str) -> list[dict]:
    """Llama a GET /api/admin/usage/sessions/{thread_id} para el detalle petición a petición.

    Args:
        thread_id: Sesión de chat de la que se quiere el detalle de uso.

    Returns:
        Lista de peticiones al LLM (nodo, modelo, tokens, coste, latencia).
    """
    r = httpx.get(f"{API_BASE}/api/admin/usage/sessions/{thread_id}", timeout=10)
    r.raise_for_status()
    return r.json().get("requests", [])


def usage_trends(since=None, until=None) -> list[dict]:
    """Llama a GET /api/admin/usage/trends para la serie temporal de
    coste/tokens/latencia por nodo (gráficas de tendencia de 2_Costes.py).

    Args:
        since: fecha mínima (``datetime.date`` o str "YYYY-MM-DD"), o None
            para no filtrar por fecha de inicio.
        until: fecha máxima (inclusive), o None para no filtrar por fecha
            de fin.

    Returns:
        Lista de puntos, uno por (fecha, nodo): date, node, requests,
        total_tokens, cost_eur, cost_complete, avg_latency_ms.
    """
    params = {}
    if since is not None:
        params["since"] = str(since)
    if until is not None:
        params["until"] = str(until)
    r = httpx.get(f"{API_BASE}/api/admin/usage/trends", params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("points", [])


def observability_links() -> dict:
    """Llama a GET /api/admin/observability: enlaces a LangFuse, estado del
    checkpointer y error rate por tool MCP.

    Returns:
        Dict con si LangFuse está configurado y, si lo está, las URLs a
        las vistas de sesiones/usuarios; `checkpointer` con su estado; y
        `tool_error_rates` (lista agregada por tool, ver
        tool_call_service.get_tool_call_error_rates).
    """
    r = httpx.get(f"{API_BASE}/api/admin/observability", timeout=10)
    r.raise_for_status()
    return r.json()
