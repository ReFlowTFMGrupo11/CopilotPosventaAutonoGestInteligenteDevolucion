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
    LANGFUSE_BASE_URL     https://cloud.langfuse.com  (default; usar
                          http://localhost:3000 si usas el stack self-hosted
                          de langfuse_infra/, ver su README)
    LANGFUSE_HOST         alias antiguo de LANGFUSE_BASE_URL, se lee como
                          fallback por compatibilidad con el resto de la
                          documentación del repo (langfuse_infra/README.md,
                          tests/qa/scripts/README.md)
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


def _host() -> str:
    """Resuelve el host de LangFuse: LANGFUSE_BASE_URL (nombre actual del SDK)
    con fallback a LANGFUSE_HOST (nombre usado en el resto de la docs del
    repo, p.ej. langfuse_infra/README.md), y por último LangFuse Cloud."""
    return (
        os.getenv("LANGFUSE_BASE_URL")
        or os.getenv("LANGFUSE_HOST")
        or "https://cloud.langfuse.com"
    )


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
                host=_host(),
            )
            logger.info("LangFuse inicializado → %s", _host())
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

    IMPORTANTE (SDK v4, OTel-only): ``CallbackHandler.__init__`` ya NO acepta
    ``secret_key``/``host`` — solo ``public_key`` (y ``trace_context``).
    Internamente llama a ``get_client(public_key=...)``, que busca un
    cliente ``Langfuse`` YA REGISTRADO en un registro global indexado por
    ``public_key`` (``LangfuseResourceManager``). Por eso hay que llamar a
    ``get_langfuse()`` (que sí construye el cliente con las credenciales
    completas) ANTES de crear el CallbackHandler — si no, el handler no
    encuentra ningún cliente autenticado y las trazas no llegan a ningún
    sitio (sin error visible, porque get_client() sin cliente registrado
    devuelve uno "disabled").
    """
    global _callback_instance
    if not _is_configured():
        return None
    if _callback_instance is None:
        # Debe ir ANTES de construir el CallbackHandler: registra el
        # cliente autenticado que get_client() (llamado internamente por
        # CallbackHandler) necesita encontrar.
        if get_langfuse() is None:
            return None
        try:
            from langfuse.langchain import CallbackHandler
            _callback_instance = CallbackHandler(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
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
