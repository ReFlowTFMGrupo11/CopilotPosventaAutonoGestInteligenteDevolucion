# frontend/ — App Streamlit

Interfaz web de ReFlow: consume la API de [`../backend/main.py`](../backend/README.md)
por HTTP, no importa nada del grafo de LangGraph directamente. Dos vistas:
el chat del cliente y el panel de administración para el corte
Human-in-the-Loop (HITL).

## Estructura

```
frontend/
  lib/
    settings.py    # API_BASE_URL (variable de entorno REFLOW_API_URL)
    api_client.py  # ReflowApiClient — cliente HTTP fino hacia backend/main.py
  Home.py                          # Página de entrada: estado de conexión al backend
  pages/
    1_💬_Chat_Cliente.py           # Chat interactivo con streaming en vivo
    2_🛠️_Panel_Admin.py            # Aprobar/rechazar devoluciones pausadas por HITL
```

Streamlit convierte automáticamente cada fichero de `pages/` en una página
del menú lateral, en el orden del prefijo numérico y con el nombre/emoji
del archivo como título.

## `lib/api_client.py`

Deliberadamente **sin `import streamlit`**: solo construye peticiones HTTP
(vía `httpx`) contra `backend/main.py` y devuelve estructuras Python
simples (`ChatEvent`, listas de dicts). Así se puede testear con un
`httpx.MockTransport` o reutilizar desde cualquier otro cliente sin
arrastrar Streamlit.

| Método | Endpoint del backend | Uso |
|---|---|---|
| `health()` | `GET /health` | Aviso en `Home.py` si el backend no está levantado. |
| `stream_chat(message, thread_id)` | `POST /api/chat/stream` (SSE) | Generador que va cediendo cada evento (`agent_step`, `final`, `awaiting_admin`, `error`) a medida que llega. |
| `list_pending()` | `GET /api/admin/pending` | Devoluciones pausadas por HITL, para el panel admin. |
| `approve(thread_id, approved)` | `POST /api/admin/approve/{thread_id}` | Aplica la decisión del administrador. |

## `Home.py`

Landing page: explica brevemente el sistema y comprueba con
`client.health()` si el backend FastAPI responde, mostrando el comando
exacto para levantarlo si no. Enlaza a las dos páginas.

## `pages/1_💬_Chat_Cliente.py`

- Genera un `thread_id` (UUID) por sesión de navegador, guardado en
  `st.session_state` — es la clave que el checkpointer de LangGraph usa
  para mantener el historial de esa conversación entre turnos.
- Cada mensaje del usuario (`st.chat_input`) se envía con
  `client.stream_chat(...)`; mientras llegan eventos `agent_step` se
  muestra en vivo qué agente está trabajando (`"triage → evaluator → resolver"`),
  y al llegar `final`/`awaiting_admin` se pinta la respuesta definitiva.
- Si la respuesta trae `label_path` (devolución aprobada), aparece un botón
  para descargar el PDF de la etiqueta generado por
  `backend/services/logistics_service.py`.
- Botón "Nueva conversación" en la barra lateral: genera un `thread_id`
  nuevo y limpia el historial mostrado (no borra nada del checkpointer, solo
  empieza un hilo distinto).

## `pages/2_🛠️_Panel_Admin.py`

Lista (`client.list_pending()`) las conversaciones que el grafo dejó en
pausa porque el reembolso solicitado supera 100 €, con el motivo y el
importe. Cada tarjeta tiene dos botones, **Aprobar**/**Rechazar**, que
llaman a `client.approve(thread_id, approved=...)`: el backend reanuda ese
`thread_id` exacto en el grafo (`Command(resume=...)`), genera la etiqueta,
registra la devolución y notifica al cliente si se aprobó — todo eso ya
ocurre en el backend, esta página solo dispara la decisión y refresca la
lista.

## Cómo arrancarlo

Necesita el backend (`uvicorn backend.main:app`) y los dos servidores MCP
ya levantados (ver [`../backend/README.md`](../backend/README.md)):

```bash
streamlit run frontend/Home.py
```

Por defecto apunta a `http://localhost:8000`; para apuntar a otro backend:

```bash
REFLOW_API_URL=http://mi-backend:8000 streamlit run frontend/Home.py
```
