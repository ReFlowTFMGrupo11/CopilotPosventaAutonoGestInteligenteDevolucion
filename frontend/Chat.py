"""ReFlow — Chat de devoluciones (página de inicio).

Reimplementación en Streamlit de la vista "/" generada originalmente
con Lovable (React). Mismo flujo: crea un thread_id, envía mensajes al
backend y muestra el progreso de los agentes vía streaming (SSE).
"""

import httpx
import streamlit as st

from lib import api, styles

st.set_page_config(page_title="Chat de devoluciones — ReFlow", page_icon="💬", layout="centered")
styles.inject_css()

# Contenedor fijo (sticky) arriba de la página: logo + indicador de pasos.
# Se reutiliza más abajo (tras calcular current_step) para que ambos queden
# dentro del mismo bloque y se fijen juntos al hacer scroll.
sticky_top = st.container(key="reflow-sticky-top")
with sticky_top:
    styles.render_header()
    styles.render_backend_banner(api.health())

if "messages" not in st.session_state:
    st.session_state.messages = []  # cada item: {"kind": "user"|"agent"|"awaiting"|"error", "text": str}

if "thread_id" not in st.session_state:
    try:
        st.session_state.thread_id = api.new_chat()
    except httpx.HTTPError:
        st.session_state.thread_id = None
        st.session_state.messages.append(
            {"kind": "error", "text": "No se pudo iniciar la conversación con el backend."}
        )

thread_id = st.session_state.thread_id

order_items: list[dict] = []
selection_required = False
reason_pending = False
current_order_id = None
tracking_number = None
resolution = None
if thread_id:
    try:
        chat_state = api.chat_state(thread_id)
        order_items = chat_state.get("order_items") or []
        selection_required = bool(chat_state.get("selection_required"))
        reason_pending = bool(chat_state.get("reason_pending"))
        current_order_id = chat_state.get("order_id")
        tracking_number = chat_state.get("tracking_number")
        resolution = chat_state.get("resolution")
    except httpx.HTTPError:
        order_items = []
        selection_required = False

# ── Indicador de pasos del flujo de devolución ─────────────────────────────
if current_order_id:
    if selection_required:
        current_step = 1
    elif reason_pending:
        current_step = 2
    elif not (tracking_number or resolution in ("approved", "rejected")):
        current_step = 3
    else:
        current_step = 4
else:
    current_step = 0
with sticky_top:
    styles.render_step_tracker(current_step)


BOT_AVATAR = "📦"
USER_AVATAR = "👤"


def render_bubble(kind: str, text: str) -> None:
    if kind == "user":
        with st.chat_message("user", avatar=USER_AVATAR):
            st.write(text)
        return
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        if kind == "agent":
            st.write(text)
        elif kind == "awaiting":
            st.markdown(f'<div class="reflow-awaiting">{text}</div>', unsafe_allow_html=True)
        else:
            st.error(text)


def _render_item_selection(
    items: list[dict],
) -> tuple[list[str], list[str], bool]:
    """Renderiza checkboxes de selección de ítems.

    Returns:
        selected_ids, selected_names, submitted
    """
    st.markdown("### Selección de artículo")
    st.caption("Marca el/los artículo(s) a devolver para selección determinista.")
    selected_ids: list[str] = []
    selected_names: list[str] = []
    for item in items:
        item_id = item.get("id")
        label = f"{item.get('name','Artículo')} · cant: {item.get('quantity',1)} · precio: {item.get('unit_price')}€"
        if item_id and st.checkbox(label, key=f"item_select_{item_id}"):
            selected_ids.append(item_id)
            selected_names.append(item.get("name", "Artículo"))
    st.caption(f"Seleccionados: {len(selected_ids)}")
    submitted = st.button(
        "Confirmar selección y continuar",
        disabled=not selected_ids,
        use_container_width=True,
    )
    return selected_ids, selected_names, submitted


QUICK_REPLY_REASONS = [
    ("Talla incorrecta", "La talla no es correcta. El artículo está sin abrir."),
    ("Producto defectuoso", "El producto ha llegado defectuoso."),
    ("No era lo que esperaba", "No era lo que esperaba, cambié de opinión. Está sin abrir."),
    ("Llegó dañado", "El paquete llegó dañado durante el transporte."),
]


def _render_quick_replies() -> str | None:
    """Botones de motivo de devolución más frecuentes.

    Devuelve el texto a enviar como mensaje si el usuario pulsa alguno,
    o None si no ha pulsado ninguno en este rerun.
    """
    st.caption("Motivos frecuentes:")
    cols = st.columns(len(QUICK_REPLY_REASONS))
    for col, (label, message) in zip(cols, QUICK_REPLY_REASONS):
        if col.button(label, key=f"quick_reply_{label}", use_container_width=True):
            return message
    return None


chat_scroll = st.container(height=420, key="reflow-chat-scroll")
with chat_scroll:
    if not st.session_state.messages:
        st.markdown(
            '<div style="text-align:center;margin-top:2.5rem;color:var(--muted);">'
            '<p style="font-size:1.1rem;font-weight:600;color:inherit;">¿Necesitas devolver un pedido?</p>'
            "<p>Cuéntame tu número de pedido y el motivo, y me encargo del resto.</p>"
            "</div>",
            unsafe_allow_html=True,
        )

    for message in st.session_state.messages:
        render_bubble(message["kind"], message["text"])

if order_items:
    st.markdown("#### Tu pedido")
    for item in order_items:
        styles.render_item_card(
            item.get("name", "Artículo"), item.get("quantity", 1), item.get("unit_price")
        )

selected_item_ids: list[str] = []
selected_item_names: list[str] = []
selection_submitted = False
if order_items and selection_required:
    selected_item_ids, selected_item_names, selection_submitted = _render_item_selection(order_items)

quick_reply_text: str | None = None
if reason_pending and not selection_required:
    quick_reply_text = _render_quick_replies()

prompt = st.chat_input("Escribe tu mensaje..." if thread_id else "Conectando...", disabled=not thread_id)

user_text: str | None = None
if selection_submitted:
    user_text = "Quiero devolver: " + ", ".join(selected_item_names)
elif quick_reply_text:
    user_text = quick_reply_text
elif prompt:
    user_text = prompt

if user_text:
    st.session_state.messages.append({"kind": "user", "text": user_text})

    with chat_scroll:
        render_bubble("user", user_text)

        with st.chat_message("assistant", avatar=BOT_AVATAR):
            status = st.empty()
            status.caption("Estamos trabajando en tramitar tu petición...")
            body = st.empty()
            kind, text = "agent", "(sin contenido)"
            try:
                for event in api.stream_chat(
                    thread_id,
                    user_text,
                    selected_item_ids=selected_item_ids or None,
                ):
                    etype = event.get("type")
                    content = event.get("content") or ""
                    if etype == "agent_step":
                        status.caption(f"Agente {event.get('agent', 'desconocido')} procesando...")
                    elif etype == "final":
                        kind, text = "agent", content or "(sin contenido)"
                    elif etype == "awaiting_admin":
                        kind, text = "awaiting", content or "Tu solicitud está pendiente de revisión"
                    elif etype == "error":
                        kind, text = "error", content or "Se ha producido un error."
            except httpx.HTTPError as exc:
                kind, text = "error", f"No se pudo contactar con el backend: {exc}"

            status.empty()
            if kind == "agent":
                body.write(text)
            elif kind == "awaiting":
                body.markdown(f'<div class="reflow-awaiting">{text}</div>', unsafe_allow_html=True)
            else:
                body.error(text)

    st.session_state.messages.append({"kind": kind, "text": text})
    st.rerun()
