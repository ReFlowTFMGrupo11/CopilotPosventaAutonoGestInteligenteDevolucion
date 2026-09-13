"""
Acceso a datos de llamadas a tools MCP (tabla ``mcp_tool_calls``):
éxito/fallo y latencia por tool, para responder "¿qué tools fallan más?"
-- hueco identificado en docs/defensaTFM/defenderLangfuse.md: antes solo se
sabía que un TURNO acababa en error (``observability.score_error``), nunca
qué tool en concreto falló dentro de ese turno.

Quién escribe aquí: backend/agents/infra/mcp_client.py::call_tool(), el
único punto de paso de las 10 tools MCP. Un fallo al escribir NUNCA debe
enmascarar el resultado real de la tool ni romper el turno del cliente --
ese guard vive en mcp_client.py, no aquí (mismo principio que
usage_tracking.py/usage_service.py para el coste de LLM).
"""

from __future__ import annotations

from backend.db.supabase_client import get_supabase_client


async def log_tool_call(
    *,
    tool_name: str,
    success: bool,
    latency_ms: int,
    thread_id: str | None = None,
    error_message: str | None = None,
) -> None:
    """Inserta una fila de resultado para una llamada individual a una tool MCP."""
    client = await get_supabase_client()
    await client.table("mcp_tool_calls").insert(
        {
            "thread_id": thread_id,
            "tool_name": tool_name,
            "success": success,
            "error_message": error_message,
            "latency_ms": latency_ms,
        }
    ).execute()


async def get_tool_call_error_rates(limit: int = 500) -> list[dict]:
    """Agrega llamadas por tool: total, nº de errores, % de error y
    latencia media -- ordenado por % de error descendente (las tools que
    más fallan primero, para responder de un vistazo "¿qué tool está dando
    problemas?").

    Se agrega en Python en vez de una vista SQL: mismo criterio que
    ``usage_service.list_usage_sessions()`` -- el volumen esperado (uso
    interno de un panel admin) no lo justifica y evita otra migración.

    Args:
        limit: número máximo de filas de ``mcp_tool_calls`` a leer (las más
            recientes primero) antes de agregar por tool.

    Returns:
        Lista de dicts, uno por tool, con ``tool_name``, ``total``,
        ``errors``, ``error_rate`` (0.0-1.0) y ``avg_latency_ms``.
    """
    client = await get_supabase_client()
    resp = await (
        client.table("mcp_tool_calls")
        .select("tool_name, success, latency_ms, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = resp.data or []

    stats: dict[str, dict] = {}
    for row in rows:
        tool_name = row["tool_name"]
        entry = stats.setdefault(
            tool_name,
            {"tool_name": tool_name, "total": 0, "errors": 0, "latencies_ms": []},
        )
        entry["total"] += 1
        if not row.get("success", True):
            entry["errors"] += 1
        entry["latencies_ms"].append(row.get("latency_ms") or 0)

    result = []
    for entry in stats.values():
        latencies = entry.pop("latencies_ms")
        entry["error_rate"] = (
            round(entry["errors"] / entry["total"], 4) if entry["total"] else 0.0
        )
        entry["avg_latency_ms"] = (
            round(sum(latencies) / len(latencies)) if latencies else 0
        )
        result.append(entry)

    result.sort(key=lambda e: e["error_rate"], reverse=True)
    return result
