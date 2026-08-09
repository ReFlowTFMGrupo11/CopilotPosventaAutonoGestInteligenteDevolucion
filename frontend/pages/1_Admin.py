"""ReFlow — Panel de administración.

Reimplementación en Streamlit de la vista "/admin" generada
originalmente con Lovable (React): KPIs, aprobación HITL de
devoluciones pendientes, listado filtrable y buscador de pedidos.
"""

import httpx
import streamlit as st

from lib import api, styles

st.set_page_config(page_title="Panel de administración — ReFlow", page_icon="🛠️", layout="wide")
styles.inject_css()
styles.render_header()
styles.render_backend_banner(api.health())

st.markdown("## Panel de administración")


def money(value) -> str:
    try:
        return f"{float(value):.2f} €"
    except (TypeError, ValueError):
        return "—"


try:
    stats = api.stats()
    pending = api.pending_returns()
except httpx.HTTPError as exc:
    st.error(f"No se pudieron cargar los datos: {exc}")
    stats, pending = {}, []

# ── KPIs ─────────────────────────────────────────────────────────────────

rate = stats.get("approval_rate")
rate_text = f"{rate:.0f}%" if isinstance(rate, (int, float)) else "—"

cols = st.columns(5)
kpis = [
    ("Total", stats.get("total_returns", "—")),
    ("Aprobadas", stats.get("approved", "—")),
    ("Rechazadas", stats.get("rejected", "—")),
    ("Pendientes", stats.get("pending", "—")),
    ("Tasa aprobación", rate_text),
]
for col, (label, value) in zip(cols, kpis):
    col.markdown(styles.kpi_card(label, str(value)), unsafe_allow_html=True)

# ── Pendientes de aprobación ─────────────────────────────────────────────

st.markdown("### Pendientes de aprobación")

if not pending:
    st.caption("No hay devoluciones pendientes.")
else:
    header = st.columns([2, 2, 1.3, 3, 2.2, 1, 1])
    for col, label in zip(header, ["Pedido", "Cliente", "Importe", "Motivo", "Motivo decisión", "", ""]):
        col.markdown(f"**{label}**")

    for row in pending:
        thread_id = row.get("thread_id") or row.get("id")
        c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 2, 1.3, 3, 2.2, 1, 1])
        c1.write(row.get("order_id", "—"))
        c2.write(row.get("customer_id", "—"))
        c3.write(money(row.get("refund_amount")))
        c4.write(row.get("reason", "—"))
        reason = c5.text_input(
            "Motivo", key=f"reason_{thread_id}", placeholder="Motivo (opcional)", label_visibility="collapsed"
        )
        if c6.button("Aprobar", key=f"approve_{thread_id}", type="primary"):
            api.approve(thread_id, reason)
            st.rerun()
        if c7.button("Rechazar", key=f"reject_{thread_id}"):
            api.reject(thread_id, reason)
            st.rerun()

# ── Todas las devoluciones ───────────────────────────────────────────────

st.markdown("### Todas las devoluciones")

status_options = {"Todas": "", "Aprobadas": "approved", "Rechazadas": "rejected", "Pendientes": "pending_approval"}
status_label = st.selectbox("Filtrar por estado", options=list(status_options.keys()), label_visibility="collapsed")

try:
    rows = api.list_returns(status_options[status_label])
except httpx.HTTPError as exc:
    st.error(f"No se pudieron cargar las devoluciones: {exc}")
    rows = []

if not rows:
    st.caption("Sin resultados.")
else:
    table = [
        {
            "Pedido": r.get("order_id", "—"),
            "Cliente": r.get("customer_id", "—"),
            "Importe": money(r.get("refund_amount")),
            "Motivo": r.get("reason", "—"),
            "Estado": styles.STATUS_LABEL.get(r.get("status"), r.get("status") or "—"),
        }
        for r in rows
    ]
    st.dataframe(table, use_container_width=True, hide_index=True)

# ── Buscador de pedidos ──────────────────────────────────────────────────

st.markdown("### Buscador de pedidos")

with st.form("buscador_pedidos", border=False):
    col_input, col_button = st.columns([4, 1])
    order_id = col_input.text_input(
        "order_id", placeholder="order_id (p. ej. ORD-1024)", label_visibility="collapsed"
    )
    buscar = col_button.form_submit_button("🔍 Buscar")

if buscar and order_id.strip():
    try:
        st.json(api.get_order(order_id.strip()))
    except httpx.HTTPError:
        st.error(f"No se encontró el pedido {order_id.strip()}")
