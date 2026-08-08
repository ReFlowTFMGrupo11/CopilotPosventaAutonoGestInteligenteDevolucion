# ReFlow — Frontend (Streamlit)

Interfaz web de ReFlow: chat de devoluciones para clientes y panel de
administración para el equipo. Reimplementación en Streamlit + Python
+ HTML/CSS de la versión original generada con Lovable (React).

## Resumen de la migración (React/Lovable → Streamlit)

Se eliminó por completo el frontend generado con Lovable (React +
TypeScript + TanStack Router/Query + Tailwind + shadcn/ui, ~90
ficheros) y se reescribió desde cero en Streamlit, replicando la misma
funcionalidad y el mismo contrato con el backend (`backend/api/`), sin
cambiar una línea del backend.

**Eliminado:** `frontend/src/` (rutas, componentes shadcn/ui, cliente
`api.ts`), `package.json`/`package-lock.json`, `vite.config.ts`,
`tsconfig.json`, `eslint.config.js`, `components.json`,
`LOVABLE_PROMPT.md` y demás tooling de Node/Vite.

**Añadido**, con equivalencia directa a la versión React:

| React/Lovable | Streamlit | Notas |
|---|---|---|
| `routes/index.tsx` (`/`) | `Chat.py` | página de inicio |
| `routes/admin.tsx` (`/admin`) | `pages/1_Admin.py` | Streamlit genera la navegación lateral automáticamente a partir de `pages/` |
| `routes/__root.tsx` (header + nav) | `lib/styles.py::render_header()` | logo "R" + título; la navegación Chat/Admin la da la sidebar nativa de Streamlit |
| `components/BackendBanner.tsx` | `lib/styles.py::render_backend_banner()` | mismo texto y color si `/health` falla |
| `lib/api.ts` (fetch + parseo SSE manual) | `lib/api.py` (httpx) | una función por endpoint, sin envoltorios innecesarios |
| `styles.css` (tokens oklch) | `lib/styles.py::_CSS` | misma paleta (marca índigo, éxito verde, error rojo, aviso ámbar) traducida a hex, con variante `prefers-color-scheme: dark` |
| Burbujas de chat hechas a mano | `st.chat_message` / `st.chat_input` | se usan los componentes nativos de chat de Streamlit en vez de reconstruir HTML de burbujas |
| `window.prompt()` para el motivo de aprobar/rechazar | `st.text_input` inline por fila | Streamlit no tiene prompts bloqueantes; un input junto a los botones es el equivalente más simple |
| `JSON.stringify(order, null, 2)` en `<pre>` | `st.json(order)` | visor JSON nativo, plegable |

**Contrato de API sin cambios:** `POST /api/chat/new`, `POST
/api/chat/stream` (SSE), `GET /api/admin/pending`, `GET
/api/admin/returns`, `POST /api/admin/{thread_id}/approve|reject`,
`GET /api/orders/{order_id}`, `GET /api/stats`, `GET /health`.

**Dependencias:** se añadieron `streamlit` y `httpx` a
`requirements.txt` (sección "Frontend"); no se tocó nada del backend.

Verificado con `streamlit run frontend/Chat.py`: arranca sin errores y
sirve correctamente tanto `/` (Chat) como `/Admin`.

## Vistas

- **Chat** (`Chat.py`): el cliente pide su devolución conversando con
  los agentes. Muestra el progreso en tiempo real (SSE) y los avisos
  de "pendiente de aprobación" o error.
- **Admin** (`pages/1_Admin.py`): KPIs, aprobación/rechazo de
  devoluciones pendientes (HITL), listado filtrable de devoluciones y
  buscador de pedidos.

## Estructura

```
frontend/
  Chat.py            # página de inicio (vista de chat)
  pages/
    1_Admin.py        # panel de administración
  lib/
    api.py            # cliente HTTP del backend (httpx)
    styles.py          # CSS de marca + helpers HTML (header, KPIs, badges)
```

## Ejecutar

El backend (`backend/api/main.py`) debe estar corriendo en
`http://localhost:8000`:

```sh
uvicorn backend.api.main:app --reload
```

Y en otra terminal, el frontend:

```sh
pip install -r requirements.txt
streamlit run frontend/Chat.py
```

Streamlit añade automáticamente la navegación "Chat" / "Admin" en la
barra lateral a partir de `pages/`.
