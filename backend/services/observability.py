"""
Observabilidad con LangFuse — punto central de instrumentación.

Expone estos helpers:
  - get_langfuse_callback()  → CallbackHandler para inyectar en LangGraph/LangChain.
                               Traza automáticamente cada nodo del grafo (latencia,
                               tokens, prompt, respuesta) sin modificar el código
                               de los agentes.
  - get_langfuse()           → cliente Langfuse para trazas manuales (p.ej. scores
                               en evaluate_rag.py o eventos de negocio custom).
  - with_langfuse()          → añade thread_id/customer_id como
                               langfuse_session_id/langfuse_user_id, para que
                               LangFuse agregue coste (tokens) por sesión y
                               por cliente sin necesidad de un contador propio.
  - langfuse_links()         → URLs del dashboard para el panel de admin
                               (ver frontend/pages/1_Admin.py).

Todos devuelven None/deshabilitado si LANGFUSE_SECRET_KEY no está en el
entorno, de modo que el sistema arranca sin errores aunque LangFuse no esté
configurado.

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
    LANGFUSE_PROJECT_ID   opcional. LangFuse (cloud y self-hosted) no tiene
                          una ruta /sessions a nivel de host que redirija
                          sola al proyecto — da 404 sin el id (ver
                          langfuse_links()). Por eso, si no se fija esta
                          variable, langfuse_links() lo resuelve solo
                          llamando a la API de LangFuse con las credenciales
                          configuradas (GET /api/public/projects); fíjala
                          solo si esa llamada falla o hay varios proyectos
                          bajo las mismas keys.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from backend.config import get_settings

logger = logging.getLogger(__name__)

# ── Inicialización lazy (una sola vez por proceso) ─────────────────────────

_langfuse_instance: Optional[Any] = None
_callback_instance: Optional[Any] = None
_project_id: Optional[str] = None


def _is_configured() -> bool:
    settings = get_settings()
    return bool(settings.langfuse_secret_key and settings.langfuse_public_key)


def _host() -> str:
    """Resuelve el host de LangFuse: LANGFUSE_BASE_URL (nombre actual del SDK)
    con fallback a LANGFUSE_HOST (nombre usado en el resto de la docs del
    repo, p.ej. langfuse_infra/README.md), y por último LangFuse Cloud."""
    settings = get_settings()
    return settings.langfuse_base_url or settings.langfuse_host or "https://cloud.langfuse.com"


def get_langfuse() -> Optional[Any]:
    """Devuelve el cliente Langfuse singleton, o None si no está configurado."""
    global _langfuse_instance
    if not _is_configured():
        return None
    if _langfuse_instance is None:
        try:
            from langfuse import Langfuse
            settings = get_settings()
            _langfuse_instance = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key.get_secret_value(),
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
                public_key=get_settings().langfuse_public_key,
            )
            logger.info("LangFuse CallbackHandler listo.")
        except Exception as exc:
            logger.warning("LangFuse CallbackHandler no disponible: %s", exc)
            return None
    return _callback_instance


def with_langfuse(
    config: dict[str, Any],
    *,
    thread_id: str | None = None,
    customer_id: str | None = None,
) -> dict[str, Any]:
    """Añade callback+metadata de LangFuse a config de LangGraph si aplica.

    - Si LangFuse no está configurado, devuelve `config` sin cambios.
    - Si hay `thread_id`, lo añade como `langfuse_session_id` para agrupar
      toda la conversación en una misma sesión de LangFuse (y así ver coste
      acumulado por sesión en su dashboard, sin tracking propio).
    - Si hay `customer_id` (solo se conoce a partir de que el cliente da su
      order_number, ver fetch_order_data en triage.py), lo añade como
      `langfuse_user_id` para poder agregar coste por cliente en LangFuse.
      Los turnos anteriores a conocer el order_number quedan sin este tag.
    """
    callback = get_langfuse_callback()
    if callback is None:
        return config

    merged = dict(config)
    merged["callbacks"] = [*merged.get("callbacks", []), callback]
    if thread_id or customer_id:
        metadata = dict(merged.get("metadata", {}))
        if thread_id:
            metadata["langfuse_session_id"] = thread_id
        if customer_id:
            metadata["langfuse_user_id"] = customer_id
        merged["metadata"] = metadata
    return merged


def _resolve_project_id() -> Optional[str]:
    """Resuelve el project_id de LangFuse asociado a las API keys configuradas.

    LangFuse exige /project/{id}/... en la URL para sus vistas (Sessions,
    Users): no hay un /sessions a nivel de host que redirija solo, da 404
    (visto en local con el stack self-hosted de langfuse_infra/). En vez de
    exigir configurar `LANGFUSE_PROJECT_ID` a mano, se pide una vez a la API
    pública de LangFuse (unas API keys casi siempre pertenecen a un único
    proyecto) y se cachea en memoria del proceso.
    """
    global _project_id
    if _project_id:
        return _project_id
    if override := get_settings().langfuse_project_id:
        _project_id = override
        return _project_id

    lf = get_langfuse()
    if lf is None:
        return None
    try:
        projects = lf.api.projects.get()
        if projects.data:
            _project_id = projects.data[0].id
    except Exception as exc:
        logger.warning("No se pudo resolver el project_id de LangFuse: %s", exc)
        return None
    return _project_id


def langfuse_links() -> dict[str, Any]:
    """URLs del dashboard de LangFuse para monitorizar gasto por sesión/cliente.

    Si no se puede resolver el project_id (ver `_resolve_project_id`),
    `sessions_url`/`users_url` vienen a None y el caller debe enlazar a
    `host` a secas para que el usuario navegue manualmente.
    """
    if not _is_configured():
        return {"configured": False}

    host = _host()
    project_id = _resolve_project_id()
    if not project_id:
        return {"configured": True, "host": host, "sessions_url": None, "users_url": None}

    base = f"{host}/project/{project_id}"
    return {
        "configured": True,
        "host": host,
        "sessions_url": f"{base}/sessions",
        "users_url": f"{base}/users",
    }


def flush() -> None:
    """Fuerza el envío de eventos pendientes a LangFuse (útil al cerrar la app)."""
    lf = get_langfuse()
    if lf:
        try:
            lf.flush()
        except Exception as exc:
            logger.warning("Error al hacer flush de LangFuse: %s", exc)
