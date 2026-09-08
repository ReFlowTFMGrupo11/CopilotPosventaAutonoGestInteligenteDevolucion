"""ReFlow — Panel de costes.

Coste en tokens y latencia de cada llamada al LLM, agregado por sesión
(cliente + pedido asociados) y con detalle petición a petición. Los datos
vienen de la tabla `llm_usage` (ver backend/agents/usage_tracking.py, que
registra cada llamada desde triage/evaluator/resolution).
"""

import httpx
import streamlit as st

from lib import api, styles

st.set_page_config(page_title="Panel de costes — ReFlow", page_icon="💰", layout="wide")
styles.inject_css()
styles.render_header()
styles.render_backend_banner(api.health())

st.markdown("## Coste y latencia por sesión")
st.caption(
    "Cada fila es una sesión de chat (thread_id). El cliente y el pedido se "
    "muestran en cuanto el cliente da su número de pedido; los turnos "
    "anteriores a eso se cuentan en la sesión pero sin esos datos."
)
st.caption(
    "💡 El coste en € es una ESTIMACIÓN: usa precios por token fijados a mano "
    "en backend/services/pricing.py (no hay API de precios de OpenAI) y un "
    "tipo de cambio USD→EUR aproximado. Revísalos si quieres cifras exactas."
)


def money(value) -> str:
    """Formatea un importe como euros con 4 decimales, o "—" si no es numérico."""
    try:
        return f"{float(value):.4f} €"
    except (TypeError, ValueError):
        return "—"


try:
    sessions = api.usage_sessions()
except httpx.HTTPError as exc:
    st.error(f"No se pudieron cargar los datos de uso: {exc}")
    sessions = []

if not sessions:
    st.caption("Todavía no hay uso registrado.")
else:
    total_tokens = sum(s.get("total_tokens", 0) for s in sessions)
    total_requests = sum(s.get("requests", 0) for s in sessions)
    total_cost = sum(s.get("cost_eur", 0.0) for s in sessions)
    any_incomplete = any(not s.get("cost_complete", True) for s in sessions)
    avg_latency = round(
        sum(s.get("avg_latency_ms", 0) for s in sessions) / len(sessions)
    )

    cols = st.columns(5)
    kpis = [
        ("Sesiones", str(len(sessions))),
        ("Peticiones a LLM", str(total_requests)),
        ("Tokens totales", f"{total_tokens:,}".replace(",", ".")),
        ("Coste total (~)", money(total_cost) + (" *" if any_incomplete else "")),
        ("Latencia media", f"{avg_latency} ms"),
    ]
    for col, (label, value) in zip(cols, kpis):
        col.markdown(styles.kpi_card(label, value), unsafe_allow_html=True)

    st.markdown("### Sesiones")
    table = [
        {
            "Sesión": s["thread_id"],
            "Cliente": s.get("customer_name") or s.get("customer_id") or "—",
            "Pedido": s.get("order_number") or s.get("order_id") or "—",
            "Peticiones": s.get("requests", 0),
            "Tokens totales": s.get("total_tokens", 0),
            "Coste (~)": money(s.get("cost_eur"))
            + ("*" if not s.get("cost_complete", True) else ""),
            "Latencia media": f"{s.get('avg_latency_ms', 0)} ms",
            "Latencia máx.": f"{s.get('max_latency_ms', 0)} ms",
            "Última actividad": s.get("last_seen", "—"),
        }
        for s in sessions
    ]
    st.dataframe(table, use_container_width=True, hide_index=True)
    if any_incomplete:
        st.caption(
            "* incluye peticiones de un modelo sin precio configurado; el coste real es mayor."
        )

    st.markdown("### Detalle por sesión")
    options = {s["thread_id"]: s for s in sessions}
    selected = st.selectbox(
        "Elige una sesión para ver el detalle petición a petición",
        options=list(options.keys()),
        format_func=lambda tid: (
            f"{tid} — {options[tid].get('customer_name') or options[tid].get('customer_id') or 'sin cliente'} "
            f"/ {options[tid].get('order_number') or options[tid].get('order_id') or 'sin pedido'}"
        ),
    )

    if selected:
        try:
            requests = api.usage_session_detail(selected)
        except httpx.HTTPError as exc:
            st.error(f"No se pudo cargar el detalle de la sesión: {exc}")
            requests = []

        if not requests:
            st.caption("Sin peticiones registradas para esta sesión.")
        else:
            detail_table = [
                {
                    "Fecha": r.get("created_at", "—"),
                    "Nodo": r.get("node", "—"),
                    "Modelo": r.get("model", "—"),
                    "Tokens entrada": r.get("input_tokens", 0),
                    "Tokens salida": r.get("output_tokens", 0),
                    "Tokens totales": r.get("total_tokens", 0),
                    "Coste (~)": (
                        money(r["cost_eur"])
                        if r.get("cost_eur") is not None
                        else "sin precio"
                    ),
                    "Latencia": f"{r.get('latency_ms', 0)} ms",
                }
                for r in requests
            ]
            st.dataframe(detail_table, use_container_width=True, hide_index=True)
