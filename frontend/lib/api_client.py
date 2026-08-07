"""
frontend/lib/api_client.py
=============================
Cliente HTTP fino hacia el backend de FastAPI (backend/main.py), usado por
las páginas de Streamlit (frontend/pages/*.py). Vive en un módulo aparte,
SIN `import streamlit`, para poder testearlo con mocks de httpx sin
arrastrar Streamlit, y para poder reutilizarlo desde cualquier otro cliente
futuro sin duplicar la lógica de parseo de las respuestas.

Es deliberadamente fino: no contiene lógica de negocio, solo construye
peticiones HTTP contra los endpoints de backend/main.py y parsea las
respuestas a estructuras Python simples, dejando toda la presentación a
las páginas de Streamlit que lo llaman.
"""

import json
from dataclasses import dataclass
from typing import Iterator, Optional

import httpx


@dataclass
class ChatEvent:
    """Espejo en Python puro de backend/schemas.py::ChatStreamEvent (evita que el frontend dependa de FastAPI/Pydantic)."""

    type: str
    content: str
    agent: Optional[str] = None
    order_id: Optional[str] = None
    is_eligible: Optional[bool] = None
    tracking_number: Optional[str] = None
    label_path: Optional[str] = None
    resolution: Optional[str] = None


def parse_sse_line(line: str) -> Optional[ChatEvent]:
    """
    Parsea una línea del formato Server-Sent Events ('data: {...json...}')
    a un ChatEvent, o None si la línea no trae un evento (líneas en blanco
    que separan eventos, etc.). Extraída como función libre para poder
    testearla con simples strings, sin necesidad de httpx ni de un servidor real.
    """
    if not line or not line.startswith("data:"):
        return None
    raw = line[len("data:"):].strip()
    if not raw:
        return None
    payload = json.loads(raw)
    return ChatEvent(**payload)


class ReflowApiClient:
    """
    Cliente hacia la API de ReFlow. `base_url` y `timeout` son inyectables
    (no hardcodeados) para poder apuntar a un backend distinto en tests o
    en otros entornos sin tocar código. `transport` es opcional y solo se
    usa en tests: un `httpx.MockTransport` permite simular las respuestas
    del backend sin red real ni un servidor FastAPI levantado.
    """

    def __init__(self, base_url: str, timeout: float = 90.0, transport: Optional[httpx.BaseTransport] = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    def _client(self, timeout: Optional[float] = None) -> httpx.Client:
        return httpx.Client(timeout=timeout if timeout is not None else self.timeout, transport=self.transport)

    def stream_chat(self, message: str, thread_id: str) -> Iterator[ChatEvent]:
        """
        Envía un turno de chat a POST /api/chat/stream y va cediendo cada
        evento SSE a medida que llega, para que la página de Streamlit
        pueda pintar el razonamiento de los agentes en tiempo real.
        """
        payload = {"message": message, "thread_id": thread_id}
        with self._client() as client:
            with client.stream("POST", f"{self.base_url}/api/chat/stream", json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    event = parse_sse_line(line)
                    if event is not None:
                        yield event

    def list_pending(self) -> list[dict]:
        """GET /api/admin/pending: devoluciones a la espera de revisión humana (HITL)."""
        with self._client() as client:
            response = client.get(f"{self.base_url}/api/admin/pending")
            response.raise_for_status()
            return response.json()

    def approve(self, thread_id: str, approved: bool) -> dict:
        """POST /api/admin/approve/{thread_id}: aprueba o rechaza una devolución pausada por HITL."""
        with self._client() as client:
            response = client.post(
                f"{self.base_url}/api/admin/approve/{thread_id}",
                json={"approved": approved},
            )
            response.raise_for_status()
            return response.json()

    def health(self) -> bool:
        """True si el backend responde; se usa para avisar claramente en Streamlit si FastAPI no está levantado."""
        try:
            with self._client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except httpx.HTTPError:
            return False
