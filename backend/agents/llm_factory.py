"""
Factory compartida para construir el LLM de cada nodo del grafo.

Antes de este módulo, triage.py/evaluator.py/resolution.py triplicaban el
mismo patrón (leer env var, quitar el prefijo opcional "openai:", construir
ChatOpenAI). Centralizado aquí para no repetirlo por cuarta vez la próxima
vez que se añada un nodo.

También centraliza dos controles de seguridad que antes no existían:
- ``timeout``: sin él, un ``ainvoke()`` colgado en el proveedor (LLM_TIMEOUT_SECONDS)
  bloquea la tarea asyncio para siempre y ningún ``try/except`` aguas arriba
  lo captura (no lanza excepción, simplemente no vuelve nunca).
- ``max_tokens`` configurable por env var: antes era un valor fijo en código
  (4096) sin forma de ajustarlo sin tocar el fuente.
"""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

DEFAULT_MODEL = "gpt-5-mini"

# Timeout por llamada al LLM (segundos). Cubre conexión + lectura de la
# respuesta completa. Si el proveedor no responde en este plazo, ChatOpenAI
# lanza una excepción capturable en vez de dejar el await colgado para siempre.
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

# Límite de tokens de salida por defecto, ahora ajustable sin tocar código.
# Si un nodo pasa `max_tokens` explícito, esta env var no lo sobreescribe.
_DEFAULT_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096"))


def build_chat_llm(
    env_var: str, *, temperature: float, max_tokens: int | None = None
) -> ChatOpenAI:
    """Construye un ``ChatOpenAI`` leyendo el modelo desde una env var.

    Admite el prefijo opcional ``"openai:"`` (convención de
    ``init_chat_model`` de LangChain) por si se configura así en ``.env``.
    Si ``env_var`` no está definida, usa ``DEFAULT_MODEL``.

    ``temperature`` y ``max_tokens`` también son sobreescribibles por env var,
    añadiendo el sufijo correspondiente a ``env_var`` (p. ej. "RESOLVER_MODEL"
    -> "RESOLVER_MODEL_TEMPERATURE" / "RESOLVER_MODEL_MAX_TOKENS"). Si esas
    env vars no están definidas, se usan los valores pasados como argumento.

    Args:
        env_var: Nombre de la variable de entorno del modelo (p. ej.
            "TRIAGE_MODEL").
        temperature: Temperatura por defecto si no hay env var específica.
        max_tokens: Límite de tokens de salida por defecto si no hay env var
            específica. Si no se especifica, usa ``LLM_MAX_OUTPUT_TOKENS``
            (por defecto 4096).
    """
    model = os.getenv(env_var, DEFAULT_MODEL).removeprefix("openai:")
    default_max_tokens = max_tokens if max_tokens is not None else _DEFAULT_MAX_OUTPUT_TOKENS
    resolved_temperature = float(os.getenv(f"{env_var}_TEMPERATURE", str(temperature)))
    resolved_max_tokens = int(os.getenv(f"{env_var}_MAX_TOKENS", str(default_max_tokens)))
    return ChatOpenAI(
        model=model,
        temperature=resolved_temperature,
        max_tokens=resolved_max_tokens,
        timeout=LLM_TIMEOUT_SECONDS,
    )


def trim_history(messages: list, *, max_messages: int | None = None) -> list:
    """Recorta el historial de conversación a los últimos ``max_messages``.

    Sin esto, ``triage_agent``/``evaluator_agent`` mandaban TODO el historial
    de la conversación al LLM en cada turno: en una conversación larga, el
    prompt (y por tanto el coste y la latencia) crece sin límite. Se
    mantienen los últimos N mensajes, que son los relevantes para decidir
    la respuesta del turno actual.

    Args:
        messages: Historial completo (``state["messages"]``).
        max_messages: Tope de mensajes a conservar. Por defecto,
            ``MAX_HISTORY_MESSAGES`` (20).
    """
    limit = max_messages if max_messages is not None else int(
        os.getenv("MAX_HISTORY_MESSAGES", "20")
    )
    if limit <= 0 or len(messages) <= limit:
        return messages
    return messages[-limit:]
