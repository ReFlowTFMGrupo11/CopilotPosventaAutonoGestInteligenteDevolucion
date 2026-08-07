"""
frontend/Home.py
===================
Punto de entrada de la app Streamlit de ReFlow. Muestra un resumen del
sistema y el estado de conexión con el backend; el chat de cliente y el
panel de administración viven como páginas aparte en frontend/pages/.
"""

import streamlit as st

from lib.api_client import ReflowApiClient
from lib.settings import API_BASE_URL

st.set_page_config(page_title="ReFlow", page_icon="🔄")
st.title("🔄 ReFlow — Copiloto de Posventa Autónomo")
st.write(
    "Sistema de agentes de IA (LangGraph: Triaje → Evaluador → Resolución) "
    "para automatizar la gestión de devoluciones de e-commerce, con "
    "políticas evaluadas por RAG y revisión humana (HITL) obligatoria para "
    "reembolsos superiores a 100 €."
)

client = ReflowApiClient(API_BASE_URL)
if client.health():
    st.success(f"✅ Backend conectado en {API_BASE_URL}")
else:
    st.error(
        f"⚠️ No se puede contactar con el backend en {API_BASE_URL}.\n\n"
        "Arráncalo con: `uvicorn backend.main:app --reload`\n\n"
        "Y asegúrate de que los servidores MCP estén levantados:\n"
        "`python -m backend.mcp.mcp_supabase` y `python -m backend.mcp.mcp_logistics`."
    )

st.page_link("pages/1_💬_Chat_Cliente.py", label="💬 Ir al chat de cliente")
st.page_link("pages/2_🛠️_Panel_Admin.py", label="🛠️ Ir al panel de administración")
