"""Integración de Langfuse (tracing de LLM) para el grafo de agentes.

Langfuse es opcional: si LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY no están
configuradas, o el paquete 'langfuse' no está instalado, with_langfuse()
devuelve el config tal cual y el resto de la app sigue funcionando igual.

Ver README.md de esta carpeta para levantar Langfuse con Docker y obtener
las claves.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_handler = None
_checked = False


def get_langfuse_handler():
    """Crea (una sola vez) y devuelve el CallbackHandler de Langfuse.

    Devuelve None si no está configurado o el paquete no está instalado.
    """
    global _handler, _checked
    if _checked:
        return _handler
    _checked = True

    if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
        logger.info(
            "Langfuse no configurado (faltan LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY); "
            "tracing desactivado."
        )
        return None

    try:
        try:
            from langfuse.langchain import CallbackHandler  # SDK >= 3.x
        except ImportError:
            from langfuse.callback import CallbackHandler  # SDK 2.x
        _handler = CallbackHandler()
        logger.info(
            "Langfuse tracing activado (host=%s).",
            os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    except ImportError:
        logger.warning(
            "Paquete 'langfuse' no instalado; tracing desactivado. "
            "Instala con: pip install -r requirements.txt"
        )
        _handler = None

    return _handler


def with_langfuse(config: dict, *, thread_id: str | None = None) -> dict:
    """Añade el callback de Langfuse a un config de LangGraph, si está disponible.

    Si se pasa thread_id, las trazas de esa conversación quedan agrupadas
    como una misma "session" en el panel de Langfuse.
    """
    handler = get_langfuse_handler()
    if handler is None:
        return config

    config = dict(config)
    config["callbacks"] = [*config.get("callbacks", []), handler]
    if thread_id:
        metadata = dict(config.get("metadata", {}))
        metadata["langfuse_session_id"] = thread_id
        config["metadata"] = metadata
    return config
