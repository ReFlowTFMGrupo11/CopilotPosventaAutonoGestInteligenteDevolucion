"""
frontend/pages/2_🛠️_Panel_Admin.py
=====================================
Panel de administración HITL: lista las conversaciones que el grafo dejó
en pausa (interrupt()) porque el reembolso solicitado supera el umbral de
100 €, y permite aprobarlas o rechazarlas. Al decidir, el backend reanuda
directamente el grafo de LangGraph de ESE thread_id con
Command(resume=...) — no se vuelve a ejecutar el flujo desde el principio.
"""

import streamlit as st

from lib.api_client import ReflowApiClient
from lib.settings import API_BASE_URL

st.set_page_config(page_title="ReFlow — Panel Admin", page_icon="🛠️")
st.title("🛠️ Panel de Administración (HITL)")
st.caption("Devoluciones pausadas a la espera de aprobación manual (reembolso > 100 €).")

client = ReflowApiClient(API_BASE_URL)

if st.button("🔄 Refrescar"):
    st.rerun()

try:
    pending = client.list_pending()
except Exception as exc:  # noqa: BLE001
    st.error(f"No se ha podido contactar con el backend: {exc}")
    pending = []

if not pending:
    st.info("No hay devoluciones pendientes de revisión en este momento.")

for item in pending:
    with st.container(border=True):
        st.markdown(f"**Pedido:** `{item.get('order_id') or 'N/D'}`")
        st.markdown(f"**Cliente:** `{item.get('customer_id') or 'N/D'}`")
        refund_amount = item.get("refund_amount")
        st.markdown(f"**Importe a reembolsar:** {refund_amount:.2f} €" if refund_amount is not None else "**Importe:** N/D")
        st.markdown(f"**Motivo:** {item.get('reason') or 'N/D'}")
        st.caption(item.get("message") or "")

        thread_id = item["thread_id"]
        col_ok, col_ko = st.columns(2)
        if col_ok.button("✅ Aprobar", key=f"approve-{thread_id}", type="primary"):
            result = client.approve(thread_id, approved=True)
            st.success(f"Devolución aprobada. Estado: {result.get('status')}")
            st.rerun()
        if col_ko.button("❌ Rechazar", key=f"reject-{thread_id}"):
            result = client.approve(thread_id, approved=False)
            st.warning(f"Devolución rechazada. Estado: {result.get('status')}")
            st.rerun()
