"""
frontend/pages/1_💬_Chat_Cliente.py
=====================================
Vista del Cliente: chat interactivo que consume el streaming SSE de FastAPI
(POST /api/chat/stream) y muestra el razonamiento de los agentes en tiempo
real, más el botón de descarga de la etiqueta de envío cuando la
devolución queda aprobada.
"""

import os
import uuid

import streamlit as st

from lib.api_client import ReflowApiClient
from lib.settings import API_BASE_URL

st.set_page_config(page_title="ReFlow — Chat Cliente", page_icon="💬")
st.title("💬 Chat con tu Copiloto de Posventa")
st.caption("Ej.: «Quiero devolver el pedido <UUID de mi pedido>, me llegó defectuoso»")

if "thread_id" not in st.session_state:
    # Un thread_id por sesión de navegador: agrupa el historial en
    # LangGraph vía el checkpointer (mismo hilo = misma conversación/caso).
    st.session_state.thread_id = str(uuid.uuid4())
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # [{"role": "user"|"assistant", "content": str, "label_path": str|None}]

client = ReflowApiClient(API_BASE_URL)


def _offer_label_download(label_path: str) -> None:
    """Botón de descarga de la etiqueta PDF si el fichero existe en disco local (ver logistics_service.py)."""
    if not label_path or not os.path.exists(label_path):
        if label_path:
            st.caption(f"Etiqueta generada en: {label_path}")
        return
    with open(label_path, "rb") as fh:
        st.download_button(
            "📄 Descargar etiqueta de envío",
            data=fh.read(),
            file_name=os.path.basename(label_path),
            mime="application/pdf",
            key=f"label-{label_path}",
        )


with st.sidebar:
    st.caption(f"thread_id: `{st.session_state.thread_id}`")
    if st.button("🆕 Nueva conversación"):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.chat_history = []
        st.rerun()

for turn in st.session_state.chat_history:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])
        if turn.get("label_path"):
            _offer_label_download(turn["label_path"])

user_message = st.chat_input("Escribe tu consulta...")

if user_message:
    st.session_state.chat_history.append({"role": "user", "content": user_message, "label_path": None})
    with st.chat_message("user"):
        st.markdown(user_message)

    with st.chat_message("assistant"):
        status_area = st.empty()
        final_content = None
        final_label_path = None
        steps_seen: list[str] = []
        try:
            for event in client.stream_chat(user_message, st.session_state.thread_id):
                if event.type == "agent_step":
                    steps_seen.append(event.agent or "?")
                    status_area.caption(" → ".join(steps_seen))
                elif event.type in ("final", "awaiting_admin"):
                    final_content = event.content
                    final_label_path = event.label_path
                elif event.type == "error":
                    final_content = f"⚠️ {event.content}"
        except Exception as exc:  # noqa: BLE001 - se muestra al usuario, no debe tumbar la app
            final_content = f"⚠️ No se ha podido contactar con el backend: {exc}"

        status_area.empty()
        st.markdown(final_content or "No he recibido respuesta del copiloto.")
        if final_label_path:
            _offer_label_download(final_label_path)

    st.session_state.chat_history.append(
        {"role": "assistant", "content": final_content or "", "label_path": final_label_path}
    )
