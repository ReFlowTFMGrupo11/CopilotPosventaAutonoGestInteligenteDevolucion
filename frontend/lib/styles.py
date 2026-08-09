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
</style>
"""

STATUS_LABEL = {"approved": "Aprobada", "rejected": "Rechazada", "pending_approval": "Pendiente"}
STATUS_BADGE_CLASS = {"approved": "badge-approved", "rejected": "badge-rejected", "pending_approval": "badge-pending"}


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def render_header() -> None:
    st.markdown(
        '<div class="reflow-header">'
        '<span class="reflow-logo">R</span>'
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
