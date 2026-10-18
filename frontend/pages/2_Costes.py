"""ReFlow — Panel de costes.

Analítica real (tendencias por nodo en el tiempo) en vez de solo tablas
planas: coste/latencia/tokens diarios por nodo (triage/evaluator/
resolution), con filtro temporal. Los datos vienen de la tabla
`llm_usage` (ver backend/agents/usage_tracking.py, que registra cada
llamada, y backend/services/usage_service.py::get_usage_timeseries, que
la agrega por día y nodo).

El detalle por sesión (tablas de antes de este refactor) sigue disponible
en un expander más abajo -- responde una pregunta distinta ("¿cuánto costó
ESTE pedido/cliente?") que las gráficas de tendencia no cubren.
"""

from datetime import date, timedelta

import httpx
import pandas as pd
import streamlit as st

from lib import api, styles

st.set_page_config(page_title="Panel de costes — ReFlow", page_icon="💰", layout="wide")
styles.inject_css()
styles.render_header()
styles.render_backend_banner(api.health())

# ── Muro de login admin ──────────────────────────────────────────────────────
if "admin_token" not in st.session_state:
    st.markdown("### Acceso al panel de costes")
    with st.form("admin_login_costes"):
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Entrar", use_container_width=True)
    if submitted and password:
        try:
            result = api.admin_login(password)
            st.session_state["admin_token"] = result["token"]
            st.rerun()
        except httpx.HTTPStatusError as exc:
            st.error(
                "Contraseña incorrecta."
                if exc.response.status_code == 401
                else f"Error: {exc}"
            )
        except httpx.RequestError as exc:
            st.error(f"No se pudo contactar con el backend: {exc}")
    st.stop()

admin_token = st.session_state["admin_token"]

with st.sidebar:
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state.pop("admin_token", None)
        st.rerun()

st.markdown("## Coste, latencia y tokens por nodo")
st.caption(
    "💡 El coste en € es una ESTIMACIÓN: usa precios por token fijados en "
    "Settings (LLM_PRICES_JSON, ver backend/services/pricing.py -- no hay "
    "API de precios de OpenAI) y un tipo de cambio USD→EUR aproximado. Se "
    "congela en el momento de la llamada, no cambia si se corrige un precio "
    "más adelante (ver docs/REMAINING_TASKS.md §2)."
)


def money(value) -> str:
    """Formatea un importe como euros con 4 decimales, o "—" si no es numérico."""
    try:
        return f"{float(value):.4f} €"
    except (TypeError, ValueError):
        return "—"


# ── KPIs globales (todas las sesiones, sin filtro temporal) ────────────────
try:
    sessions = api.usage_sessions(token=admin_token)
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
    if any_incomplete:
        st.caption(
            "* incluye peticiones de un modelo sin precio configurado; el coste real es mayor."
        )

st.divider()

# ── Tendencias por nodo (analítica real) ────────────────────────────────────
st.markdown("### Tendencias por nodo")

PRESETS = {
    "Últimos 7 días": 7,
    "Últimos 30 días": 30,
    "Últimos 90 días": 90,
    "Todo el histórico": None,
}
preset = st.radio(
    "Periodo",
    options=list(PRESETS.keys()),
    index=1,
    horizontal=True,
    label_visibility="collapsed",
)
days = PRESETS[preset]
since = date.today() - timedelta(days=days) if days is not None else None

try:
    points = api.usage_trends(since=since, token=admin_token)
except httpx.HTTPError as exc:
    st.error(f"No se pudieron cargar las tendencias: {exc}")
    points = []

if not points:
    st.caption("Sin datos de uso en el periodo seleccionado.")
else:
    df = pd.DataFrame(points)
    df["date"] = pd.to_datetime(df["date"])
    incomplete_trend = df["cost_complete"].eq(False).any()

    def _pivot(metric: str) -> pd.DataFrame:
        """Una columna por nodo, una fila por fecha -- lo que espera st.line_chart."""
        return df.pivot_table(
            index="date", columns="node", values=metric, aggfunc="sum"
        )

    tab_coste, tab_latencia, tab_tokens = st.tabs(
        ["💰 Coste (€/día)", "⏱️ Latencia media (ms)", "🔢 Tokens/día"]
    )
    with tab_coste:
        st.line_chart(_pivot("cost_eur"))
        if incomplete_trend:
            st.caption(
                "* algún día/nodo incluye peticiones de un modelo sin precio "
                "configurado en ese momento; el coste real de esos puntos es mayor."
            )
    with tab_latencia:
        # avg_latency_ms ya es un promedio por (fecha, nodo): agregarlo con
        # aggfunc="sum" en _pivot sería incorrecto (sumaría promedios) --
        # solo hay una fila por (fecha, nodo), así que "mean"/"sum" con un
        # único valor da lo mismo, pero se usa "mean" para dejar la
        # intención explícita.
        st.line_chart(
            df.pivot_table(
                index="date", columns="node", values="avg_latency_ms", aggfunc="mean"
            )
        )
    with tab_tokens:
        st.line_chart(_pivot("total_tokens"))

    st.caption(
        f"{len(df):,} punto(s) día/nodo entre {df['date'].min().date()} y "
        f"{df['date'].max().date()}.".replace(",", ".")
    )

st.divider()

# ── Detalle por sesión (drill-down) ─────────────────────────────────────────
#
# Pregunta distinta a las tendencias de arriba: "¿cuánto costó ESTE pedido o
# ESTE cliente?", no "¿cómo evoluciona el gasto en el tiempo?". Colapsado
# por defecto porque ya no es la vista principal de la página.
with st.expander("📋 Detalle por sesión (tabla)", expanded=False):
    if not sessions:
        st.caption("Todavía no hay uso registrado.")
    else:
        st.caption(
            "Cada fila es una sesión de chat (thread_id). El cliente y el "
            "pedido se muestran en cuanto el cliente da su número de pedido; "
            "los turnos anteriores a eso se cuentan en la sesión pero sin "
            "esos datos."
        )
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

        st.markdown("#### Petición a petición")
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
                requests = api.usage_session_detail(selected, token=admin_token)
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
