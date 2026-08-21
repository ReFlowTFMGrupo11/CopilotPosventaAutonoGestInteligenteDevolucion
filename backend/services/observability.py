"""
Observabilidad con LangFuse — punto central de instrumentación.

Expone dos helpers:
  - get_langfuse_callback()  → CallbackHandler para inyectar en LangGraph/LangChain.
                               Traza automáticamente cada nodo del grafo (latencia,
                               tokens, prompt, respuesta) sin modificar el código
                               de los agentes.
  - get_langfuse()           → cliente Langfuse para trazas manuales (p.ej. scores
                               en evaluate_rag.py o eventos de negocio custom).

Ambos devuelven None si LANGFUSE_SECRET_KEY no está en el entorno, de modo que
el sistema arranca sin errores aunque LangFuse no esté configurado.

Variables de entorno necesarias (ver .env):
    LANGFUSE_PUBLIC_KEY   pk-lf-...
    LANGFUSE_SECRET_KEY   sk-lf-...
    LANGFUSE_BASE_URL     https://cloud.langfuse.com  (default)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Inicialización lazy (una sola vez por proceso) ─────────────────────────

_langfuse_instance: Optional[Any] = None
_callback_instance: Optional[Any] = None


def _is_configured() -> bool:
    return bool(os.getenv("LANGFUSE_SECRET_KEY") and os.getenv("LANGFUSE_PUBLIC_KEY"))


def get_langfuse() -> Optional[Any]:
    """Devuelve el cliente Langfuse singleton, o None si no está configurado."""
    global _langfuse_instance
    if not _is_configured():
        return None
    if _langfuse_instance is None:
        try:
            from langfuse import Langfuse
            _langfuse_instance = Langfuse(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
                host=os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
            )
            logger.info("LangFuse inicializado → %s", os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"))
        except Exception as exc:
            logger.warning("LangFuse no disponible: %s", exc)
            return None
    return _langfuse_instance


def get_langfuse_callback() -> Optional[Any]:
    """Devuelve el CallbackHandler de LangFuse para inyectar en LangGraph.

    Uso:
        cb = get_langfuse_callback()
        callbacks = [cb] if cb else []
        await graph.ainvoke(state, config={
            "configurable": {"thread_id": thread_id},
            "callbacks": callbacks,
        })
    """
    global _callback_instance
    if not _is_configured():
        return None
    if _callback_instance is None:
        try:
            from langfuse.langchain import CallbackHandler
            _callback_instance = CallbackHandler(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
                host=os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
            )
            logger.info("LangFuse CallbackHandler listo.")
        except Exception as exc:
            logger.warning("LangFuse CallbackHandler no disponible: %s", exc)
            return None
    return _callback_instance


def with_langfuse(config: dict[str, Any], *, thread_id: str | None = None) -> dict[str, Any]:
    """Añade callback+metadata de LangFuse a config de LangGraph si aplica.

    - Si LangFuse no está configurado, devuelve `config` sin cambios.
    - Si hay `thread_id`, lo añade como `langfuse_session_id` para agrupar
      toda la conversación en una misma sesión de LangFuse.
    """
    callback = get_langfuse_callback()
    if callback is None:
        return config

    merged = dict(config)
    merged["callbacks"] = [*merged.get("callbacks", []), callback]
    if thread_id:
        metadata = dict(merged.get("metadata", {}))
        metadata["langfuse_session_id"] = thread_id
        merged["metadata"] = metadata
    return merged


def flush() -> None:
    """Fuerza el envío de eventos pendientes a LangFuse (útil al cerrar la app)."""
    lf = get_langfuse()
    if lf:
        try:
            lf.flush()
        except Exception as exc:
            logger.warning("Error al hacer flush de LangFuse: %s", exc)
