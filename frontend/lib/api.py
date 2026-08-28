"""Cliente HTTP para la API de ReFlow (backend FastAPI en backend/api).

Cada función mapea 1:1 con un endpoint del backend. Sin abstracciones
extra: si un endpoint cambia, se cambia aquí y ya está.
"""

import json
from typing import Iterator

import httpx
from dotenv import load_dotenv

# override=True: en máquinas con conda activado automáticamente, conda ya deja
# SSL_CERT_FILE puesto (a veces con una ruta rota) antes de que arranque Python;
# sin override, load_dotenv() no lo sustituiría por el valor bueno de .env.
load_dotenv(override=True)

API_BASE = "http://localhost:8000"


def health() -> bool:
    """True si el backend responde a /health."""
    try:
        return httpx.get(f"{API_BASE}/health", timeout=3).status_code == 200
    except httpx.RequestError:
        return False


def new_chat() -> str:
    """Crea una sesión de chat y devuelve su thread_id."""
    r = httpx.post(f"{API_BASE}/api/chat/new", timeout=10)
    r.raise_for_status()
    return r.json()["thread_id"]


def stream_chat(
    thread_id: str,
    message: str,
    selected_item_ids: list[str] | None = None,
) -> Iterator[dict]:
    """Envía un mensaje y cede (yield) cada evento SSE tal como llega."""
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
                    line[len("data:"):].strip()
                    for line in raw.splitlines()
                    if line.startswith("data:")
                )
                if data:
                    yield json.loads(data)


def stats() -> dict:
    r = httpx.get(f"{API_BASE}/api/stats", timeout=10)
    r.raise_for_status()
    return r.json()


def pending_returns() -> list[dict]:
    r = httpx.get(f"{API_BASE}/api/admin/pending", timeout=10)
    r.raise_for_status()
    return r.json().get("pending", [])


def list_returns(status: str = "") -> list[dict]:
    params = {"status": status} if status else {}
    r = httpx.get(f"{API_BASE}/api/admin/returns", params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("returns", [])


def approve(thread_id: str, reason: str = "") -> dict:
    r = httpx.post(f"{API_BASE}/api/admin/{thread_id}/approve", json={"reason": reason}, timeout=30)
    r.raise_for_status()
    return r.json()


def reject(thread_id: str, reason: str = "") -> dict:
    r = httpx.post(f"{API_BASE}/api/admin/{thread_id}/reject", json={"reason": reason}, timeout=30)
    r.raise_for_status()
    return r.json()


def get_order(order_id: str) -> dict:
    r = httpx.get(f"{API_BASE}/api/orders/{order_id}", timeout=10)
    r.raise_for_status()
    return r.json()


def chat_state(thread_id: str) -> dict:
    r = httpx.get(f"{API_BASE}/api/chat/{thread_id}/state", timeout=10)
    r.raise_for_status()
    return r.json()


def usage_sessions(limit: int = 100) -> list[dict]:
    r = httpx.get(f"{API_BASE}/api/admin/usage/sessions", params={"limit": limit}, timeout=10)
    r.raise_for_status()
    return r.json().get("sessions", [])


def usage_session_detail(thread_id: str) -> list[dict]:
    r = httpx.get(f"{API_BASE}/api/admin/usage/sessions/{thread_id}", timeout=10)
    r.raise_for_status()
    return r.json().get("requests", [])


def observability_links() -> dict:
    r = httpx.get(f"{API_BASE}/api/admin/observability", timeout=10)
    r.raise_for_status()
    return r.json()
