"""
Acceso a datos de uso de LLM (tabla ``llm_usage``): coste en tokens y
latencia por petición, agregable por sesión/cliente/pedido para el panel
de administración (ver frontend/pages/2_Costes.py).

Quién escribe aquí: backend/agents/usage_tracking.py, desde cada nodo que
llama al LLM (triage/evaluator/resolution). Un fallo al escribir NUNCA debe
romper el turno del cliente — ese guard vive en usage_tracking.py, no aquí.
"""

from __future__ import annotations

from backend.db.supabase_client import get_supabase_client
from backend.services import pricing


async def log_llm_usage(
    *,
    thread_id: str,
    node: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    latency_ms: int,
    customer_id: str | None = None,
    order_id: str | None = None,
) -> None:
    """Inserta una fila de uso para una llamada individual al LLM."""
    client = await get_supabase_client()
    await client.table("llm_usage").insert(
        {
            "thread_id": thread_id,
            "customer_id": customer_id,
            "order_id": order_id,
            "node": node,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
        }
    ).execute()


async def get_usage_by_session(limit: int = 100) -> list[dict]:
    """Agrega el uso por sesión (thread_id): tokens totales, nº de peticiones
    y latencia media/máxima, con el cliente y pedido asociados (el último
    conocido en esa sesión, ya que puede haber filas sin ellos en los
    primeros turnos de triaje).

    Se agrega en Python en vez de una vista SQL: el volumen esperado (uso
    interno de un panel admin) no lo justifica y evita otra migración.

    Args:
        limit: Número máximo de sesiones a devolver (las más recientes
            primero). Se agregan hasta 2000 filas de `llm_usage` antes de
            aplicar este límite sobre las sesiones ya agrupadas.

    Returns:
        Lista de dicts, uno por sesión, con tokens/coste/latencia
        agregados y `cost_complete=False` si algún modelo de la sesión no
        tiene precio configurado (ver pricing.py).
    """
    client = await get_supabase_client()
    resp = await (
        client.table("llm_usage")
        .select(
            "thread_id, customer_id, order_id, node, model, input_tokens, "
            "output_tokens, total_tokens, latency_ms, created_at, "
            "customers(full_name, email), orders(order_number)"
        )
        .order("created_at", desc=True)
        .limit(2000)
        .execute()
    )
    rows = resp.data or []

    sessions: dict[str, dict] = {}
    for row in rows:
        thread_id = row["thread_id"]
        session = sessions.setdefault(
            thread_id,
            {
                "thread_id": thread_id,
                "customer_id": None,
                "customer_name": None,
                "order_id": None,
                "order_number": None,
                "requests": 0,
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_eur": 0.0,
                "cost_complete": True,
                "latencies_ms": [],
                "last_seen": row["created_at"],
            },
        )
        # Filas más recientes primero (orden de la query): el primer
        # customer_id/order_id no-nulo que se vea es el más reciente.
        if session["customer_id"] is None and row.get("customer_id"):
            session["customer_id"] = row["customer_id"]
            session["customer_name"] = (row.get("customers") or {}).get("full_name")
        if session["order_id"] is None and row.get("order_id"):
            session["order_id"] = row["order_id"]
            session["order_number"] = (row.get("orders") or {}).get("order_number")

        session["requests"] += 1
        session["total_tokens"] += row.get("total_tokens") or 0
        session["input_tokens"] += row.get("input_tokens") or 0
        session["output_tokens"] += row.get("output_tokens") or 0
        session["latencies_ms"].append(row.get("latency_ms") or 0)

        row_cost = pricing.estimate_cost_eur(
            row["model"], row.get("input_tokens") or 0, row.get("output_tokens") or 0
        )
        if row_cost is None:
            # Precio del modelo no configurado (ver pricing.py): el total
            # queda incompleto, no se puede pretender que sea exacto.
            session["cost_complete"] = False
        else:
            session["cost_eur"] += row_cost

    result = []
    for session in sessions.values():
        latencies = session.pop("latencies_ms")
        session["avg_latency_ms"] = (
            round(sum(latencies) / len(latencies)) if latencies else 0
        )
        session["max_latency_ms"] = max(latencies) if latencies else 0
        result.append(session)

    result.sort(key=lambda s: s["last_seen"], reverse=True)
    return result[:limit]


async def get_usage_detail(thread_id: str) -> list[dict]:
    """Detalle de cada petición individual (una fila por llamada al LLM) de una sesión.

    Returns:
        Filas de `llm_usage` ordenadas cronológicamente, cada una con un
        `cost_eur` añadido (``None`` si el modelo no tiene precio
        configurado, ver pricing.py).
    """
    client = await get_supabase_client()
    resp = await (
        client.table("llm_usage")
        .select(
            "id, node, model, input_tokens, output_tokens, total_tokens, "
            "latency_ms, created_at"
        )
        .eq("thread_id", thread_id)
        .order("created_at", desc=False)
        .execute()
    )
    rows = resp.data or []
    for row in rows:
        row["cost_eur"] = pricing.estimate_cost_eur(
            row["model"], row.get("input_tokens") or 0, row.get("output_tokens") or 0
        )
    return rows
