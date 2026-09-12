"""
Configuración centralizada: un único punto de lectura para todas las
variables de entorno del backend, vía ``pydantic-settings``.

Antes de este módulo, cada archivo leía sus propias env vars con
``os.getenv(...)`` sueltos por el código (``llm_factory.py``, ``chat.py``,
``admin.py``, ``mcp_client.py``, ``observability.py``, ``orders_service.py``/``returns_service.py``/``policy_service.py``,
``graph.py``...). Esto producía dos tipos de bugs reales en este repo:

1. Duplicación silenciosa: ``GRAPH_RECURSION_LIMIT``/``GRAPH_TURN_TIMEOUT_SECONDS``
   estaban definidos de forma independiente, con el mismo default, en
   ``chat.py`` Y en ``admin.py`` — cambiar uno sin el otro los desincroniza
   sin que nada avise.
2. Variables documentadas en ``.env.example`` que en realidad no leía nadie:
   ``HITL_THRESHOLD_EUR`` estaba documentada como configurable, pero el
   umbral vivía hardcodeado (``HITL_REFUND_THRESHOLD = 100.0``) por
   duplicado en ``policy_rules.py`` Y en ``resolution.py``. Cambiar la env
   var no tenía ningún efecto.

Todos los campos tienen default seguro (ninguno es obligatorio): a
diferencia de la configuración de Supabase (ver ``backend/db/supabase_client.py``,
que sí falla rápido si faltan credenciales reales), ninguno de los valores
de aquí bloquea el arranque del proceso si no está en ``.env`` — así,
importar este módulo nunca puede romper un test o un script que no
necesite ese valor concreto.

Uso:
    from backend.config import get_settings
    settings = get_settings()  # cacheado: una sola instancia por proceso
    settings.llm_timeout_seconds
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Todas las variables de entorno del backend, tipadas y con default.

    Los nombres de los campos coinciden exactamente (en mayúsculas) con los
    nombres de env var ya documentados en ``.env.example`` — ``pydantic-settings``
    hace ese mapeo automáticamente (``triage_model`` → ``TRIAGE_MODEL``).
    """

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # ── Entorno ──────────────────────────────────────────────────────────
    # Usado por build_return_graph() (backend/agents/graph.py) para decidir
    # si un fallo al conectar con el checkpointer persistente (Postgres) debe
    # frenar el arranque (production) o degradar a InMemorySaver con un aviso
    # (development/staging/cualquier otro valor). "development" por defecto
    # para no romper tests/scripts locales que no fijan esta variable.
    environment: str = "development"

    # ── Supabase ─────────────────────────────────────────────────────────
    # Opcionales aquí (a diferencia de antes): la validación "falla rápido
    # si faltan" vive en get_supabase_client(), que es el único sitio que de
    # verdad las necesita — así una app que solo usa LLM/MCP (sin BD) no se
    # ve forzada a configurar Supabase solo por importar Settings.
    supabase_url: str | None = None
    supabase_service_key: SecretStr | None = None
    supabase_db_url: str | None = None

    # ── OpenAI ───────────────────────────────────────────────────────────
    # Solo hace falta explícitamente para el cliente de embeddings en
    # policy_service.py (search_return_policy). Los LLM de chat
    # (ChatOpenAI en llm_factory.py) siguen leyendo OPENAI_API_KEY
    # directamente del entorno del proceso vía el SDK de OpenAI, como hasta
    # ahora — sin cambios ahí.
    openai_api_key: SecretStr | None = None

    # ── LLM (compartido por los nodos triage/evaluator/resolver) ────────
    llm_timeout_seconds: float = 60.0
    llm_max_output_tokens: int = 4096
    max_history_messages: int = 20

    # ── Modelo por nodo (override opcional; default = DEFAULT_MODEL) ────
    triage_model: str = "gpt-5-mini"
    triage_model_temperature: float | None = None
    triage_model_max_tokens: int | None = None

    evaluator_model: str = "gpt-5-mini"
    evaluator_model_temperature: float | None = None
    evaluator_model_max_tokens: int | None = None

    resolver_model: str = "gpt-5-mini"
    resolver_model_temperature: float | None = None
    resolver_model_max_tokens: int | None = None

    # ── MCP servers ──────────────────────────────────────────────────────
    mcp_supabase_url: str = "http://localhost:8001/mcp"
    mcp_logistics_url: str = "http://localhost:8002/mcp"
    mcp_timeout_seconds: float = 30.0
    mcp_sse_read_timeout_seconds: float = 60.0

    # ── Grafo / control de turno ─────────────────────────────────────────
    graph_recursion_limit: int = 25
    graph_turn_timeout_seconds: float = 60.0
    max_conversation_turns: int = 40

    # ── HITL ─────────────────────────────────────────────────────────────
    hitl_threshold_eur: float = 100.0

    # ── RAG (búsqueda semántica de políticas) ────────────────────────────
    # 0.7 dejaba search_return_policy() devolviendo 0 chunks en el uso real
    # (comprobado contra la BD real, no solo mocks): con text-embedding-3-small,
    # ninguna query realista de motivo+categoría del cliente supera ~0.5-0.55
    # de similitud coseno contra el corpus de políticas (registro conversacional
    # vs. registro normativo del documento). 0.5 se elige con evidencia amplia
    # (16 categorías × 2 motivos = 32 ejecuciones reales contra la BD, ver
    # docs/defensaTFM/defenderRAG.md §4.1): en NINGUNA de las 32 pruebas
    # devuelve 0 chunks, y la media es 4.97/5 chunks recuperados -- a
    # diferencia de un intento anterior de bajar este valor a 0.35 (revertido
    # por estar basado en solo 4 categorías, ver git log de este fichero),
    # que no tenía evidencia suficiente para fijar un valor de producción.
    # Sobreescribible vía RAG_MATCH_THRESHOLD si el corpus de políticas
    # cambia sustancialmente.
    rag_match_threshold: float = 0.5

    # ── Langfuse (observabilidad, opcional) ─────────────────────────────
    langfuse_secret_key: SecretStr | None = None
    langfuse_public_key: str | None = None
    langfuse_base_url: str | None = None
    langfuse_host: str | None = None
    langfuse_project_id: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Devuelve la instancia de ``Settings`` para este proceso (cacheada).

    ``@lru_cache`` garantiza una sola lectura/parseo de ``.env`` por
    proceso, sin importar cuántas veces se llame. En tests, si hace falta
    forzar una relectura (p. ej. tras mutar variables de entorno), usar
    ``get_settings.cache_clear()``.
    """
    return Settings()
