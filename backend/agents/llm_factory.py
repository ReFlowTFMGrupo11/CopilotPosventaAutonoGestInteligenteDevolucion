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

from langchain_openai import ChatOpenAI

from backend.agents.infra.openai_adapter import OpenAIChatAdapter
from backend.agents.ports import LLMPort
from backend.config import get_settings

DEFAULT_MODEL = "gpt-5-mini"


def build_chat_llm(
    env_var: str, *, temperature: float, max_tokens: int | None = None
) -> LLMPort:
    """Construye un ``ChatOpenAI`` leyendo el modelo desde ``Settings``.

    Admite el prefijo opcional ``"openai:"`` (convención de
    ``init_chat_model`` de LangChain) por si se configura así en ``.env``.
    Si el campo correspondiente no está en ``.env``, usa ``DEFAULT_MODEL``.

    ``temperature`` y ``max_tokens`` también son sobreescribibles por env var,
    añadiendo el sufijo correspondiente a ``env_var`` (p. ej. "RESOLVER_MODEL"
    -> "RESOLVER_MODEL_TEMPERATURE" / "RESOLVER_MODEL_MAX_TOKENS", mapeados a
    los campos ``resolver_model_temperature``/``resolver_model_max_tokens`` de
    ``Settings``). Si esas env vars no están definidas, se usan los valores
    pasados como argumento.

    Args:
        env_var: Nombre del campo de modelo en ``Settings``, en mayúsculas
            (p. ej. "TRIAGE_MODEL" -> ``settings.triage_model``).
        temperature: Temperatura por defecto si no hay env var específica.
        max_tokens: Límite de tokens de salida por defecto si no hay env var
            específica. Si no se especifica, usa
            ``settings.llm_max_output_tokens`` (por defecto 4096).
    """
    settings = get_settings()
    field = env_var.lower()
    model = getattr(settings, field, DEFAULT_MODEL).removeprefix("openai:")
    default_max_tokens = (
        max_tokens if max_tokens is not None else settings.llm_max_output_tokens
    )
    resolved_temperature = getattr(settings, f"{field}_temperature", None)
    resolved_max_tokens = getattr(settings, f"{field}_max_tokens", None)
    return OpenAIChatAdapter(
        ChatOpenAI(
            model=model,
            temperature=(
                resolved_temperature
                if resolved_temperature is not None
                else temperature
            ),
            max_tokens=(
                resolved_max_tokens
                if resolved_max_tokens is not None
                else default_max_tokens
            ),
            timeout=settings.llm_timeout_seconds,
        )
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
            ``settings.max_history_messages`` (20).
    """
    limit = (
        max_messages
        if max_messages is not None
        else get_settings().max_history_messages
    )
    if limit <= 0 or len(messages) <= limit:
        return messages
    return messages[-limit:]
