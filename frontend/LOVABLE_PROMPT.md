# Prompt usado en Lovable para generar la UI

Crea una aplicación web React con dos vistas para un sistema de gestión de devoluciones e-commerce llamado "ReFlow":

## Vista 1: Chat del cliente (`/`)

- Interfaz de chat tipo WhatsApp/ChatGPT
- Al entrar, hace `POST http://localhost:8000/api/chat/new` para obtener un `thread_id`
- El usuario escribe mensajes que se envían a `POST http://localhost:8000/api/chat/stream` con body `{"thread_id": "...", "message": "..."}`
- La respuesta es Server-Sent Events (SSE). Cada evento es un JSON con `type` que puede ser:
  - `"agent_step"`: mostrar un indicador sutil "Agente {agent} procesando..."
  - `"final"`: mostrar la respuesta del agente como mensaje en el chat
  - `"awaiting_admin"`: mostrar un aviso amarillo "Tu solicitud está pendiente de revisión"
  - `"error"`: mostrar error en rojo
- Diseño moderno, minimalista, con avatares distintos para usuario y agente

## Vista 2: Panel de administración (`/admin`)

- Dashboard con KPIs arriba: total devoluciones, aprobadas, rechazadas, pendientes, tasa de aprobación. Datos de `GET http://localhost:8000/api/stats`
- Tabla de devoluciones pendientes de aprobación (`GET http://localhost:8000/api/admin/pending`). Cada fila muestra: order_id, customer_id, refund_amount, reason. Con botones "Aprobar" y "Rechazar"
  - Aprobar: `POST http://localhost:8000/api/admin/{thread_id}/approve` con body `{"reason": "..."}`
  - Rechazar: `POST http://localhost:8000/api/admin/{thread_id}/reject` con body `{"reason": "..."}`
- Tabla de todas las devoluciones (`GET http://localhost:8000/api/admin/returns?status=`) con filtro por estado (dropdown: all, approved, rejected, pending_approval)
- Buscador de pedidos: input para order_id que consulta `GET http://localhost:8000/api/orders/{order_id}` y muestra los detalles

## Requisitos técnicos

- React + TypeScript + Tailwind CSS
- Navegación con React Router (sidebar o navbar con "Chat" y "Admin")
- Para SSE usar `fetch` con `reader.read()` (ReadableStream), no EventSource (porque es POST)
- El backend corre en `http://localhost:8000` (ya tiene CORS habilitado)
- Colores: azul/índigo para la marca, verde para aprobado, rojo para rechazado, amarillo para pendiente
- Responsive (mobile-first)
- Health check al cargar: `GET http://localhost:8000/health` — si falla, mostrar banner "Backend desconectado"
