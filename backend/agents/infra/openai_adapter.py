"""
Adaptador concreto de infraestructura: ``OpenAIChatAdapter``.

Envuelve ``langchain_openai.ChatOpenAI`` para satisfacer el puerto abstracto
``LLMPort`` definido en ``backend.agents.ports``.

Solo este fichero (y ``llm_factory.py``) conocen LangChain/OpenAI. El resto del
dominio (nodos, usage_tracking) depende únicamente de ``LLMPort``, por lo que
cambiar de proveedor (Anthropic, Azure, un mock…) no requiere tocar ningún nodo.

Cumple el contrato de ``LLMPort`` por tipado estructural: no es necesario
declarar herencia ni ``implements`` — Python lo reconoce automáticamente
al verificar que los tres miembros requeridos están presentes.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI


class OpenAIChatAdapter:
    """Adaptador que envuelve ``ChatOpenAI`` satisfaciendo ``LLMPort``.

    Args:
        llm: Instancia de ``ChatOpenAI`` construida por ``llm_factory.build_chat_llm()``.
    """

    def __init__(self, llm: ChatOpenAI) -> None:
        self._llm = llm

    @property
    def model_name(self) -> str:
        """Delega al nombre de modelo de la instancia LangChain subyacente."""
        return self._llm.model_name

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        """Delega la llamada al LLM de chat."""
        return await self._llm.ainvoke(messages)

    def with_structured_output(
        self, schema: type, *, include_raw: bool = False
    ) -> Any:
        """Delega la construcción del chain de salida estructurada."""
        return self._llm.with_structured_output(schema, include_raw=include_raw)
