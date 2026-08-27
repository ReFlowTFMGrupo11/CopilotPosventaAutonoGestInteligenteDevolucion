"""
Factory compartida para construir el LLM de cada nodo del grafo.

Antes de este módulo, triage.py/evaluator.py/resolution.py triplicaban el
mismo patrón (leer env var, quitar el prefijo opcional "openai:", construir
ChatOpenAI). Centralizado aquí para no repetirlo por cuarta vez la próxima
vez que se añada un nodo.
"""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

DEFAULT_MODEL = "gpt-5-nano"


def build_chat_llm(env_var: str, *, temperature: float, max_tokens: int = 4096) -> ChatOpenAI:
    """Construye un ``ChatOpenAI`` leyendo el modelo desde una env var.

    Admite el prefijo opcional ``"openai:"`` (convención de
    ``init_chat_model`` de LangChain) por si se configura así en ``.env``.
    Si ``env_var`` no está definida, usa ``DEFAULT_MODEL``.

    Args:
        env_var: Nombre de la variable de entorno (p. ej. "TRIAGE_MODEL").
        temperature: Temperatura del modelo.
        max_tokens: Límite de tokens de salida.
    """
    model = os.getenv(env_var, DEFAULT_MODEL).removeprefix("openai:")
    return ChatOpenAI(model=model, temperature=temperature, max_tokens=max_tokens)
