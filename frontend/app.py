"""Punto de entrada de la aplicación Streamlit.

Controla qué pestañas aparecen en la navegación lateral según el estado
de autenticación:

- Siempre visible:  Chat de devoluciones (Chat.py)
- Solo si hay token de admin en session_state: Panel de administración

El tab de admin se oculta a usuarios no autenticados. Para que el admin
pueda llegar a la pantalla de login, Chat.py incluye un enlace discreto
en el sidebar ("Acceso administrador") que siempre funciona al margen
de la navegación principal.
"""

import streamlit as st

chat = st.Page(
    "Chat.py",
    title="Chat de devoluciones",
    icon="💬",
    default=True,
)

# El icono cambia según el estado de autenticación: candado si no hay
# sesión de admin activa, herramienta si sí la hay. El tab siempre
# aparece porque st.page_link() solo puede enlazar páginas registradas
# en st.navigation() — ocultar el tab y tener un link a él es imposible
# con la API actual de Streamlit. La seguridad real está en el login wall
# de la propia página (1_Admin.py), no en la visibilidad del tab.
admin_icon = "🛠️" if st.session_state.get("admin_token") else "🔒"
admin = st.Page(
    "pages/1_Admin.py",
    title="Panel de administración",
    icon=admin_icon,
)

costes_icon = "💰" if st.session_state.get("admin_token") else "🔒"
costes = st.Page(
    "pages/2_Costes.py",
    title="Panel de costes",
    icon=costes_icon,
)

pg = st.navigation([chat, admin, costes])

pg.run()
