"""
Puertos (interfaces abstractas) del dominio para servicios LLM de chat.

Siguiendo el patrón Puerto/Adaptador (Clean Architecture):
  - El DOMINIO define aquí QUÉ necesita (forma del enchufe).
  - La INFRAESTRUCTURA (backend/agents/infra/openai_adapter.py) provee
    el CÓMO a través de adaptadores concretos.

Los puertos usan ``typing.Protocol`` (tipado estructural de Python): cualquier
clase que implemente los métodos requeridos satisface el puerto
automáticamente, sin herencia explícita. Así, tanto ``OpenAIChatAdapter``
como un ``MockLLM`` de test son válidos como ``LLMPort`` sin declararlo.
"""

from __future__ import annotations

from typing import Any, Protocol

from langchain_core.messages import AIMessage, BaseMessage


class StructuredOutputRunnable(Protocol):
    """Interfaz del objeto que devuelve ``LLMPort.with_structured_output()``.

    El dominio solo necesita saber que puede llamar a ``ainvoke()`` sobre él;
    no le importa si por dentro es un chain de LangChain u otra cosa.
    """

    async def ainvoke(self, messages: list[BaseMessage]) -> Any: ...


class LLMPort(Protocol):
    """Puerto abstracto para servicios de chat LLM.

    Cualquier adaptador (OpenAI, Anthropic, mock de tests…) que implemente
    estos tres miembros satisface este contrato por tipado estructural, sin
    necesidad de declarar herencia ni ``implements``.

    Uso típico en nodos y wrappers::

        async def invoke_tracked(llm: LLMPort, ...) -> AIMessage:
            result = await llm.ainvoke(messages)
            model = llm.model_name   # para registrar uso
            ...
    """

    @property
    def model_name(self) -> str:
        """Nombre del modelo tal y como lo devuelve el proveedor."""
        ...

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        """Invoca el LLM con el historial de mensajes y devuelve la respuesta."""
        ...

    def with_structured_output(
        self, schema: type, *, include_raw: bool = False
    ) -> StructuredOutputRunnable:
        """Devuelve un runnable que produce salida estructurada según ``schema``."""
        ...
