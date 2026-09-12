# Tareas pendientes para la siguiente release

Backlog de ingeniería — deuda técnica y gaps identificados en auditorías de la
capa de servicios (`backend/services/`) y de la API (`backend/api/`), que se
dejan documentados en vez de arreglados ahora por alcance/riesgo. Distinto de
`docs/defensaTFM/`: aquello son argumentos para defender decisiones ya
tomadas; esto son cosas que **todavía no están bien** y hay que hacer.

---

## 1. [Seguridad — prioridad alta] `/api/admin/*` no tiene autenticación ni autorización

### El problema

Ningún endpoint de la API tiene ningún mecanismo de autenticación —
comprobado: no hay `HTTPBearer`, `APIKeyHeader`, `OAuth2`, `HTTPBasic` ni
ninguna comprobación de cabecera `Authorization` en todo `backend/`. Combinado
con CORS abierto a todo (`allow_origins=["*"]`, `backend/api/main.py` —
intencional para desarrollo local, ver `AGENTS.md`), esto significa que
**cualquiera que alcance la API puede**:

- Aprobar o rechazar devoluciones (`POST /api/admin/{thread_id}/approve|reject`) — mueve dinero real (reembolsos).
- Ver el historial completo de devoluciones y PII de clientes (`GET /api/customers/{id}/history`, `GET /api/admin/returns`).
- Ver coste/uso de LLM por sesión (`GET /api/admin/usage/sessions*`).
- Ver enlaces al dashboard de Langfuse (`GET /api/admin/observability`).

En desarrollo local esto es aceptable (mismo criterio que el CORS abierto). En
cualquier despliegue real (ver rama `feature/despliegue-aws-ecs-fargate`, PR
#47) es un problema real: el panel de admin quedaría accesible por cualquiera
que conozca la URL, sin login.

### Por qué no se arregla ahora

Requiere decidir primero **qué modelo de autenticación** tiene sentido para
este proyecto (no hay ningún sistema de usuarios/roles hoy):
- Más simple: una API key compartida (`Depends()` que comprueba una cabecera
  contra `Settings.admin_api_key`) — protege el endpoint, no distingue
  usuarios.
- Más completo: login real (JWT, sesión) si en algún momento hay varios
  admins con roles distintos.

### Recomendación al abordarlo

1. Empezar por lo simple (API key vía `Depends()`, aplicada solo a
   `admin.router`/`admin.public_router`/`usage.router` — el chat de cliente
   no la necesita).
2. Documentar la decisión en `docs/defensaTFM/` una vez tomada (encaja bien en
   `defenderFastAPI.md` o un nuevo `defenderSeguridad.md`).

---

## 2. [Corrección de datos — prioridad alta] El coste del dashboard se recalcula con el precio de HOY, no el de cuando se hizo la llamada

### El problema

`llm_usage` (`supabase/migrations/014_create_llm_usage.sql`) no tiene columna
de coste. `usage_service.py::list_usage_sessions()`/`get_usage_detail()`
calculan `cost_eur` **en el momento de leer**, llamando a
`pricing.estimate_cost_eur()` con los precios **configurados ahora**
(`backend/services/pricing.py`).

Consecuencia real: si se corrige un precio desactualizado o cambia el tipo de
cambio USD→EUR, **todo el histórico de coste mostrado en el dashboard cambia
retroactivamente** — una llamada de hace 3 meses "cuesta" hoy lo que cuesta el
modelo hoy, no lo que costaba entonces. El dashboard de coste (pensado para
justificar gasto real ante quien financia el proyecto) puede estar mintiendo
sobre el pasado sin que se note.

### El fix (dos pasos, en este orden)

1. **Congelar el coste en el momento de la llamada** (el más urgente,
   corrige la incorrección de fondo, no solo el hardcoding):
   - Migración: `ALTER TABLE llm_usage ADD COLUMN cost_eur numeric;`
   - `backend/agents/usage_tracking.py::_log_usage()` calcula
     `pricing.estimate_cost_eur(...)` **antes** de llamar a
     `usage_service.log_llm_usage()`, y lo pasa como argumento nuevo.
   - `usage_service.py::list_usage_sessions()`/`get_usage_detail()` dejan de
     llamar a `pricing.estimate_cost_eur()` — leen la columna ya guardada.
   - Una vez hecho esto, cambiar un precio en el futuro **no** afecta a datos
     ya registrados.

2. **Sacar los precios del código** (menos urgente tras el paso 1, pero
   sigue mereciendo la pena para no tener que redeployar cada vez que OpenAI
   cambia un precio):
   - `pricing.py` usa `os.getenv()` suelto (`get_usd_to_eur_rate()`,
     `get_price_per_million_usd()`) — viola la regla ya documentada del
     proyecto de centralizar todo en `Settings` (`backend/config.py`). Los
     precios por modelo necesitan clave dinámica
     (`LLM_PRICE_{MODEL}_INPUT_PER_1M`), que no encaja limpio en un campo
     Pydantic normal: opción más simple, una única env var JSON
     (`LLM_PRICES_JSON='{"gpt-5-mini": [0.25, 2.0]}'`) parseada a un campo
     `dict[str, tuple[float, float]]` en `Settings`.
   - Alternativa más robusta (si se quiere cambiar precios sin redeploy):
     tabla `llm_pricing` en Supabase (modelo, precio entrada, precio salida,
     activo) — con el paso 1 ya hecho, esta tabla solo necesita el precio
     **vigente**, no un historial (el historial ya vive congelado en cada
     fila de `llm_usage`).

---

## 3. [Arquitectura — prioridad media] ~~`supabase_service.py` mezcla 3 dominios de negocio bajo un nombre de tecnología~~ — RESUELTO

### El problema (ya corregido)

`backend/services/supabase_service.py` (574 líneas, 42% de toda la capa de
servicios) agrupaba, bajo un nombre que describía la base de datos (no el
negocio), al menos 3 dominios independientes:

| Dominio | Funciones | Fichero nuevo |
|---|---|---|
| Pedidos | `get_order_details`, `calculate_days_since_delivery` | `orders_service.py` |
| Devoluciones (CRUD + panel admin) | `get_customer_return_history`, `create_return_record`, `update_return_status`, `get_pending_return_request_id`, `get_latest_return_request`, `list_pending_approvals`, `list_returns`, `get_return_detail`, `get_return_stats`, `_flatten_*`, `DUPLICATE_RETURN_MARKER` | `returns_service.py` |
| Políticas / RAG | `get_policy_info`, `search_return_policy` | `policy_service.py` |

Era el mismo olor arquitectónico ya corregido en los routers de la API
(`orders.py` mezclaba pedidos + KPIs + búsqueda, corregido en PR #56) —
siguiendo el mismo criterio (`zhanymkanov/fastapi-best-practices`: un
`service.py` por dominio) se dividió `supabase_service.py` en los 3 ficheros
de la tabla anterior y se eliminó el original. Actualizados los imports en
`backend/mcp/mcp_supabase.py`, `backend/agents/nodes/resolution.py`,
`backend/agents/nodes/evaluator.py` y `backend/api/routers/admin.py`.

---

## 4. [Testing — prioridad media] ~~`supabase_service.py` tenía la cobertura más baja de la capa de servicios~~ — RESUELTO

De sus 12 funciones públicas, solo 4 tenían test dedicado
(`get_order_details`, `get_customer_return_history`, `create_return_record`,
`update_return_status`). Sin cubrir: `get_policy_info`, `search_return_policy`,
`get_pending_return_request_id`, `get_latest_return_request`,
`list_pending_approvals`, `list_returns`, `get_return_detail`,
`get_return_stats`, y las 3 funciones `_flatten_*`.

Se abordó **a la vez** que el punto 3 (split por dominio): al mover cada
función a su nuevo fichero (`test_orders_service.py`, `test_returns_service.py`,
`test_policy_service.py`), se escribió el test que le faltaba en el mismo
commit. `test_supabase_service.py` (295 líneas) se eliminó, sustituido por
los 3 ficheros anteriores.

---

## 5. [Documentación — prioridad baja] `docs/architecture.drawio` no representa el dashboard de Costes

Comprobado al auditar `docs/` y los diagramas: `architecture.drawio` (61
elementos, geometría/estilo precisos) no menciona `usage_service.py`,
`pricing.py` ni el flujo de coste (`/api/admin/usage/sessions*`,
`2_Costes.py`) en absoluto — sí incluye Langfuse y
`/api/admin/observability`, pero el dashboard de coste propio
(`defenderDashboardCostes.md`) queda sin representar visualmente. No es una
regresión de esta sesión (el diagrama ya estaba así antes); no se corrige
aquí porque añadir una caja nueva (con su propia `mxGeometry`) a mano por
texto, sin la herramienta visual, arriesga romper el layout sin que ningún
test lo detecte (el job de CI `validate-drawio` solo comprueba que el XML
sea válido, no que se vea bien). Sí se corrigió, al dividir
`supabase_service.py` (punto 3), el *label* de texto de la caja `svc_supa`
existente (`supabase_service.py` → `orders/returns/policy_service.py`) — un
cambio seguro porque solo toca el atributo `value`, no la geometría.
Pendiente: añadir con draw.io/diagrams.net directamente una caja nueva
`usage_service.py + pricing.py` junto a la caja de servicios ya renombrada,
en la sección "Services".

---

## 6. [Código — prioridad baja] Inconsistencias menores encontradas en la auditoría de la capa de servicios

- `logistics_service.py::send_customer_notification()` usa `print()` en vez
  de `logging` (líneas 148-150) — único sitio de toda la capa de servicios
  que no usa `logger.info/warning(...)`.
- `logistics_service.py`: `LABELS_DIR.mkdir(exist_ok=True)` se ejecuta como
  efecto secundario al **importar** el módulo (línea 16), no de forma
  perezosa como el resto de imports pesados del mismo fichero (`reportlab`
  se importa dentro de la función, con comentario explicando por qué).
- Patrón inconsistente para "fila no encontrada": algunas funciones usan
  `.single()` (lanza excepción si 0 o >1 filas — `get_order_details`,
  `get_policy_info`, `get_return_detail`) y otras `.limit(1)` + comprobación
  explícita de vacío (`get_pending_return_request_id`,
  `get_latest_return_request`). No necesariamente incorrecto (distintas
  funciones pueden justificar distinto tratamiento), pero no parece una
  decisión deliberada — merece una pasada para decidir un criterio único y
  documentarlo.
- `create_return_record()`: usa `.get()` defensivo en la sección de guard de
  duplicados (`item.get("order_item_id")`) pero acceso directo por índice sin
  defaults al construir `return_items_data` (`item["order_item_id"]`,
  `item["quantity"]`, líneas 348-349) — si faltara una clave, la segunda
  parte lanzaría `KeyError` sin control, mientras que la primera está
  protegida. Inconsistencia dentro de la misma función, no solo entre
  funciones distintas.
