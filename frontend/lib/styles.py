"""Estilos compartidos (CSS + pequeños helpers HTML) para las páginas de ReFlow.

Traduce la paleta de marca del diseño Lovable original (azul/índigo,
verde, rojo, ámbar) a variables CSS reutilizables en toda la app.
"""

import streamlit as st

_CSS = """
<style>
:root {
    --brand: #4F46E5;
    --brand-foreground: #FFFFFF;
    --brand-soft: #EEF0FE;
    --success: #16A34A;
    --success-foreground: #FFFFFF;
    --success-soft: #EAFBF1;
    --danger: #DC2626;
    --danger-foreground: #FFFFFF;
    --danger-soft: #FDEBEB;
    --warning: #D97706;
    --warning-foreground: #3F2D06;
    --warning-soft: #FEF3DB;
    --border: #E5E7EB;
    --muted: #6B7280;
    --radius: 12px;
    --user-bubble: var(--brand-soft);
    --bot-bubble: #FFFFFF;
    --page-bg: #FFFFFF;
}
@media (prefers-color-scheme: dark) {
    :root {
        --brand: #818CF8;
        --brand-foreground: #15162B;
        --brand-soft: #262A47;
        --success: #4ADE80;
        --success-foreground: #0B2313;
        --success-soft: #16341F;
        --danger: #F87171;
        --danger-foreground: #2B0B0B;
        --danger-soft: #3A1414;
        --warning: #FBBF24;
        --warning-foreground: #2B2005;
        --warning-soft: #3A2C08;
        --border: rgba(255,255,255,0.14);
        --muted: #9CA3AF;
        --page-bg: #0E1117;
        --user-bubble: var(--brand-soft);
        --bot-bubble: #1F2130;
    }
}

.reflow-header {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding-bottom: 0.75rem;
    margin-bottom: 1.25rem;
    border-bottom: 1px solid var(--border);
}
.reflow-logo {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 2rem;
    height: 2rem;
    border-radius: 0.5rem;
    background: var(--brand);
    color: var(--brand-foreground);
    font-weight: 700;
    font-size: 0.95rem;
}
.reflow-title {
    font-size: 1.1rem;
    font-weight: 600;
}

.reflow-banner-down {
    background: var(--danger);
    color: var(--danger-foreground);
    padding: 0.5rem 1rem;
    border-radius: var(--radius);
    text-align: center;
    font-size: 0.9rem;
    font-weight: 500;
    margin-bottom: 1rem;
}

.kpi-card {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.9rem 1rem;
}
.kpi-label {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: var(--muted);
}
.kpi-value {
    font-size: 1.5rem;
    font-weight: 700;
    margin-top: 0.15rem;
}

.badge {
    display: inline-block;
    padding: 0.15rem 0.55rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
}
.badge-approved { background: var(--success-soft); color: var(--success); }
.badge-rejected { background: var(--danger-soft); color: var(--danger); }
.badge-pending { background: var(--warning-soft); color: var(--warning-foreground); }

.reflow-awaiting {
    background: var(--warning-soft);
    color: var(--warning-foreground);
    border-radius: var(--radius);
    padding: 0.6rem 1rem;
    font-size: 0.9rem;
}

/* Botón de enviar del chat input: usa el color de marca para más contraste
   que la flecha gris por defecto de Streamlit. */
[data-testid="stChatInputSubmitButton"] {
    background: var(--brand) !important;
}
[data-testid="stChatInputSubmitButton"] svg {
    fill: var(--brand-foreground) !important;
}

/* Burbujas de chat diferenciadas por rol. El selector usa el aria-label que
   Streamlit genera a partir del `name` pasado a st.chat_message("user"/
   "assistant", ...) — data-testid="stChatMessageContent" es el contenedor
   real de la burbuja (avatar y contenido van en elementos separados). */
[data-testid="stChatMessageContent"][aria-label="Chat message from user"] {
    background: var(--user-bubble);
    border-radius: var(--radius);
    padding: 0.6rem 1rem;
}
[data-testid="stChatMessageContent"][aria-label="Chat message from assistant"] {
    background: var(--bot-bubble);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.6rem 1rem;
}

/* Botones Aprobar/Rechazar del panel Admin: Streamlit añade una clase
   `st-key-<key>` al contenedor de cada widget con `key=...`, así que este
   selector funciona pese a que el key incluye el thread_id (variable por fila). */
[class*="st-key-approve_"] button {
    background: var(--success) !important;
    border-color: var(--success) !important;
    color: var(--success-foreground) !important;
}
[class*="st-key-reject_"] button {
    background: var(--danger) !important;
    border-color: var(--danger) !important;
    color: var(--danger-foreground) !important;
}

/* Cabecera fija (logo + indicador de pasos) en la página de Chat. */
[class*="st-key-reflow-sticky-top"] {
    position: sticky;
    top: 0;
    z-index: 999;
    background: var(--page-bg);
    padding-top: 0.5rem;
}

/* Indicador de pasos del proceso de devolución. */
.reflow-steps {
    display: flex;
    gap: 0.4rem;
    margin-bottom: 1.25rem;
}
.reflow-step {
    flex: 1;
    text-align: center;
    padding: 0.45rem 0.3rem;
    border-radius: var(--radius);
    font-size: 0.78rem;
    font-weight: 600;
    background: var(--brand-soft);
    color: var(--muted);
    border: 1px solid var(--border);
}
.reflow-step-done {
    background: var(--success-soft);
    color: var(--success);
    border-color: var(--success);
}
.reflow-step-active {
    background: var(--brand);
    color: var(--brand-foreground);
    border-color: var(--brand);
}

/* Tarjeta de resumen de artículo del pedido. */
.reflow-item-card {
    display: flex;
    align-items: center;
    gap: 0.85rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.7rem 0.9rem;
    margin-bottom: 0.5rem;
}
.reflow-item-thumb {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 2.75rem;
    height: 2.75rem;
    border-radius: 0.6rem;
    background: var(--brand-soft);
    font-size: 1.3rem;
    flex-shrink: 0;
}
.reflow-item-name {
    font-weight: 600;
}
.reflow-item-meta {
    color: var(--muted);
    font-size: 0.85rem;
}
</style>
"""

STATUS_LABEL = {"approved": "Aprobada", "rejected": "Rechazada", "pending_approval": "Pendiente"}
STATUS_BADGE_CLASS = {"approved": "badge-approved", "rejected": "badge-rejected", "pending_approval": "badge-pending"}


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def render_header() -> None:
    st.markdown(
        '<div class="reflow-header">'
        '<span class="reflow-logo">📦</span>'
        '<span class="reflow-title">ReFlow</span>'
        "</div>",
        unsafe_allow_html=True,
    )


def render_backend_banner(is_up: bool) -> None:
    if is_up:
        return
    st.markdown(
        '<div class="reflow-banner-down">'
        "Backend desconectado — no se puede contactar con http://localhost:8000"
        "</div>",
        unsafe_allow_html=True,
    )


def kpi_card(label: str, value: str) -> str:
    return f'<div class="kpi-card"><p class="kpi-label">{label}</p><p class="kpi-value">{value}</p></div>'


def status_badge(status: str | None) -> str:
    cls = STATUS_BADGE_CLASS.get(status or "", "badge-pending")
    label = STATUS_LABEL.get(status or "", status or "—")
    return f'<span class="badge {cls}">{label}</span>'


STEP_LABELS = ["Identificar pedido", "Seleccionar artículos", "Indicar motivo", "Generar etiqueta"]


def render_step_tracker(current_step: int) -> None:
    """Pinta el indicador de pasos del flujo de devolución.

    Args:
        current_step: índice (0-based) del paso en curso. Los pasos
            anteriores se marcan como completados; los siguientes, pendientes.
    """
    cells = []
    for i, label in enumerate(STEP_LABELS):
        if i < current_step:
            cls = "reflow-step reflow-step-done"
            icon = "✓ "
        elif i == current_step:
            cls = "reflow-step reflow-step-active"
            icon = ""
        else:
            cls = "reflow-step"
            icon = ""
        cells.append(f'<div class="{cls}">{icon}{i + 1}. {label}</div>')
    st.markdown(f'<div class="reflow-steps">{"".join(cells)}</div>', unsafe_allow_html=True)


def render_item_card(name: str, quantity: int, unit_price) -> None:
    """Tarjeta de resumen de un artículo del pedido (con hueco simulado de foto)."""
    price_text = f"{float(unit_price):.2f} €" if unit_price is not None else "—"
    st.markdown(
        '<div class="reflow-item-card">'
        '<div class="reflow-item-thumb">📦</div>'
        "<div>"
        f'<div class="reflow-item-name">{name}</div>'
        f'<div class="reflow-item-meta">Cantidad: {quantity} · Precio unitario: {price_text}</div>'
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
