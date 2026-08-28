"""
Instrumentación de coste (tokens) y latencia por llamada a LLM.

Contexto: la nota de alcance de la PR de controles de terminación dejaba
fuera a propósito un contador de coste acumulado por sesión, por requerir
tocar state.py, un tracker nuevo y parsear ``usage_metadata`` de cada
respuesta. Este módulo es justo eso, aislado en dos wrappers finos
alrededor de ``ainvoke()`` que cada nodo (triage/evaluator/resolution) usa
en el punto exacto donde ya llamaba al LLM, sin cambiar su lógica de
negocio. Cada llamada se registra como una fila en ``llm_usage`` (ver
supabase/migrations/014_create_llm_usage.sql), consultable por sesión en
backend/services/usage_service.py y visible en frontend/pages/2_Costes.py.

Un fallo al registrar el uso (BD caída, etc.) se loguea pero JAMÁS rompe el
turno del cliente: es solo observabilidad, no debe convertirse en un punto
de fallo del flujo de devoluciones.
"""

from __future__ import annotations

import logging
import time
from typing import TypeVar

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from backend.services import usage_service

logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def _usage_from_message(message: AIMessage | None) -> tuple[int, int, int]:
    """Extrae (input_tokens, output_tokens, total_tokens) de un AIMessage.

    ``usage_metadata`` puede venir ausente (proveedor sin soporte, mensaje
    None por error de parseo, etc.); en ese caso se registra la latencia
    igualmente y los tokens quedan a 0 en vez de romper el registro.
    """
    usage = getattr(message, "usage_metadata", None) if message else None
    if not usage:
        return 0, 0, 0
    return (
        usage.get("input_tokens") or 0,
        usage.get("output_tokens") or 0,
        usage.get("total_tokens") or 0,
    )


async def _log_usage(
    *,
    node: str,
    model: str,
    thread_id: str | None,
    customer_id: str | None,
    order_id: str | None,
    latency_ms: int,
    tokens: tuple[int, int, int],
) -> None:
    if not thread_id:
        # Sin thread_id no hay sesión a la que atribuir el gasto (p. ej.
        # scripts/tests que invocan un nodo suelto sin pasar por el grafo).
        return
    input_tokens, output_tokens, total_tokens = tokens
    try:
        await usage_service.log_llm_usage(
            thread_id=thread_id,
            customer_id=customer_id or None,
            order_id=order_id or None,
            node=node,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )
    except Exception:
        logger.warning(
            "No se pudo registrar el uso de LLM del nodo '%s' (thread_id=%s)",
            node, thread_id, exc_info=True,
        )


async def invoke_tracked(
    llm: ChatOpenAI,
    messages: list,
    *,
    node: str,
    thread_id: str | None,
    customer_id: str | None = None,
    order_id: str | None = None,
) -> AIMessage:
    """Equivalente a ``llm.ainvoke(messages)`` que además registra tokens/latencia."""
    start = time.perf_counter()
    result: AIMessage = await llm.ainvoke(messages)
    latency_ms = int((time.perf_counter() - start) * 1000)
    await _log_usage(
        node=node,
        model=llm.model_name,
        thread_id=thread_id,
        customer_id=customer_id,
        order_id=order_id,
        latency_ms=latency_ms,
        tokens=_usage_from_message(result),
    )
    return result


async def invoke_structured_tracked(
    llm: ChatOpenAI,
    schema: type[SchemaT],
    messages: list,
    *,
    node: str,
    thread_id: str | None,
    customer_id: str | None = None,
    order_id: str | None = None,
) -> SchemaT | None:
    """Equivalente a ``llm.with_structured_output(schema).ainvoke(messages)``.

    Usa ``include_raw=True``: por defecto ``with_structured_output`` solo
    devuelve el objeto Pydantic parseado y descarta el ``AIMessage`` crudo,
    que es donde vive ``usage_metadata``. Devuelve ``None`` si el parseo
    falla (mismo contrato que antes tenían triage_agent/evaluator_agent).
    """
    start = time.perf_counter()
    raw_result = await llm.with_structured_output(schema, include_raw=True).ainvoke(messages)
    latency_ms = int((time.perf_counter() - start) * 1000)
    await _log_usage(
        node=node,
        model=llm.model_name,
        thread_id=thread_id,
        customer_id=customer_id,
        order_id=order_id,
        latency_ms=latency_ms,
        tokens=_usage_from_message(raw_result.get("raw")),
    )
    if raw_result.get("parsing_error"):
        logger.warning(
            "Structured output de '%s' con error de parseo: %s",
            node, raw_result["parsing_error"],
        )
        return None
    return raw_result.get("parsed")
