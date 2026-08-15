# Registro de correcciones QA

Cada entrada documenta un bug encontrado durante las pruebas manuales QA:
qué se observó, por qué pasaba (causa raíz) y qué se cambió (o queda pendiente).
Entradas en orden cronológico inverso (la más reciente arriba).

---

## 2026-08-11 — Mejoras visuales de UX en el chat (rama `cambio-en-frontend`)

**Petición**
Adaptar el aspecto del front para que sea más acorde a un chat de devolución
de pedidos: burbujas diferenciadas por color, respuestas rápidas para el
motivo, tarjeta de resumen del artículo, e indicador de pasos del proceso.

**Cambios aplicados**

1. **Burbujas de chat diferenciadas por rol** (`frontend/lib/styles.py`).
   Streamlit no expone un testid de rol para avatares custom (emoji) —
   verificado leyendo el bundle minificado de Streamlit 1.61
   (`streamlit/static/static/js/index.*.js`): con avatar custom, tanto
   usuario como asistente devuelven `data-testid="stChatMessageAvatarCustom"`,
   sin diferenciar. La única señal estable y documentada por el propio
   código de Streamlit es el `aria-label="Chat message from ${name}"` que sí
   incluye el rol (`name` = "user"/"assistant", el mismo valor que pasamos a
   `st.chat_message(...)`). Se usó `[data-testid="stChatMessageContent"]
   [aria-label="Chat message from user"]` / `...assistant` como selector CSS,
   en vez de un testid o clase adivinados (que habrían sido frágiles).

2. **Botones de respuesta rápida** (`frontend/Chat.py`,
   `_render_quick_replies()`): 4 motivos frecuentes (talla incorrecta,
   defectuoso, cambio de opinión, dañado en transporte). Se muestran cuando
   `reason_pending=True` (nuevo campo en `GET /api/chat/{thread_id}/state`,
   `backend/api/routers/chat.py`): pedido ya identificado, artículo(s) ya
   determinados (o pedido de 1 solo artículo, que no requiere selección
   explícita) y motivo aún sin dar. Verificado en caliente contra el backend
   real que `reason_pending` pasa a `true` justo tras identificar un pedido
   de 1 artículo y vuelve a `false` en cuanto se informa el motivo.

3. **Tarjeta de resumen de artículo** (`styles.render_item_card()`): tarjeta
   con hueco de foto simulado (📦), nombre, cantidad y precio, por cada
   artículo del pedido — sustituye tener que leerlo solo en el párrafo del bot.

4. **Indicador de pasos** (`styles.render_step_tracker()`): 4 pasos
   (Identificar pedido → Seleccionar artículos → Indicar motivo → Generar
   etiqueta), calculado en `frontend/Chat.py` a partir de `order_id`,
   `selection_required`, `reason_pending`, `tracking_number` y `resolution`.

**Estado:** ✅ Implementado en la rama `cambio-en-frontend`. Verificado
funcionalmente contra el backend real (curl); pendiente de verificación
visual en navegador por el usuario antes de pushear/documentar como cerrado.

---

## 2026-08-11 — Panel Admin mostraba el UUID interno en vez del número de pedido

**Petición**
En el panel `/Admin`, tanto "Pendientes de aprobación" como "Todas las
devoluciones" mostraban en la columna "Pedido" el UUID interno de
`return_requests.order_id` (p. ej. `c3d4e5f6-a7b8-9012-cdef-123456789006`)
en vez del número de pedido legible (`ORD-QA-0006`). El "Buscador de
pedidos" de la misma pantalla, en cambio, busca por `order_number`
(`get_order_details`, `backend/services/supabase_service.py:60`, recibe
`order_number` no el UUID) — así que el valor que se veía en la tabla no
servía para copiar y pegar en el buscador.

**Cambio aplicado**
- `backend/services/supabase_service.py`: `list_pending_approvals()` y
  `list_returns()` ahora piden también `orders(order_number)` vía el embed
  de PostgREST (FK `return_requests.order_id → orders.id`,
  `supabase/migrations/006_create_return_requests.sql:4`). Se añadió
  `_flatten_order_number()` para aplanar `row["orders"]["order_number"]` a
  un campo `order_number` de primer nivel en cada fila devuelta.
- `frontend/pages/1_Admin.py`: la columna "Pedido" en ambas tablas
  (pendientes y listado completo) ahora muestra `order_number` con fallback
  al `order_id` si por lo que sea no viniera el join.

Verificado en caliente contra el backend real: `GET /api/admin/returns` y
`GET /api/admin/pending` ya devuelven `"order_number": "ORD-QA-0001"`, etc.

**Estado:** ✅ Implementado. No se ha commiteado/pusheado todavía.

---

## 2026-08-11 — Panel Admin mostraba 0 devoluciones (falsa alarma, no era bug)

**Síntoma**
Tras aprobar automáticamente la devolución de ORD-QA-0001 (ver caso
"auto-aprobación" más abajo), el panel `/Admin` mostraba Total: 0,
Aprobadas: 0, Pendientes: 0, "Sin resultados" en el listado — parecía que la
devolución no se había guardado en la BBDD.

**Investigación**
Se verificó el mismo registro (`return_requests`, id `5c4aae20-...`,
status `approved`, tracking `RF-A070D5BBCD`) por tres vías independientes:
1. Consulta directa a la API REST de Supabase con el cliente Python del backend.
2. `GET /api/stats` del backend → `{"total_returns":1,"approved":1,...}`.
3. `GET /api/admin/returns?status=approved` → devuelve la fila completa.

Las tres coinciden. La devolución **sí estaba guardada** correctamente en la
base de datos real (no hay mock ni in-memory en el flujo de `create_return_record`
— pasa por `backend/services/supabase_service.py` → Supabase real).

**Causa raíz**
No es un bug de persistencia. `frontend/pages/1_Admin.py` no tiene ningún
`st.cache_data`/autorefresh — Streamlit solo re-ejecuta el script de una
página cuando hay interacción del usuario o recarga manual. Si la pestaña
Admin ya estaba abierta desde antes de crear la devolución en el Chat, se
quedó con el snapshot antiguo (0 devoluciones) hasta recargar.

**Estado:** ✅ No era un bug — confirmado con recarga de la pestaña Admin.
No se tocó código.

---

## 2026-08-11 — Error crudo al reintentar una devolución duplicada

**Síntoma**
Al probar "Quiero devolver: Alimento QA #1" el chat devolvía un error técnico
sin procesar:
```
Error procesando tu solicitud: MCP tool 'create_return_record' failed:
Ya existe una devolución previa para el/los artículo(s): <order_item_id>.
```

**Causa raíz**
`create_return_record` (`backend/services/supabase_service.py:228-234`) lanza
`ValueError` cuando el artículo ya tiene una devolución registrada — esto es
correcto (guard de duplicados). Pero en `resolution_agent`
(`backend/agents/nodes/resolution.py`), la rama de **auto-aprobación**
(importe ≤ 100€, sin HITL) llamaba a `create_return_record` sin `try/except`,
a diferencia de la rama HITL (línea ~129) que sí captura el error y reutiliza
el registro existente. El resultado: la excepción se propagaba sin control
hasta `chat.py` (`_stream_chat_events`, línea ~144-146), que la mostraba como
"Error procesando tu solicitud: ...".

Nota: este caso normalmente aparece al re-ejecutar un caso de QA (p. ej.
QA-001) sin resetear la base de datos entre pruebas — el artículo ya tenía
una devolución de una ejecución anterior.

**Corrección aplicada**
`backend/agents/nodes/resolution.py`, rama `else` (auto-aprobación, ~línea 228):
se envolvió la llamada a `create_return_record` en `try/except (RuntimeError,
ValueError)`. Si ya existe una devolución para el pedido, se consulta el
registro existente en `return_requests` y se responde al cliente con un
mensaje empático indicando que su solicitud ya está en curso, en vez de
propagar el error. También se simplificó `return_request_id` para que se
asigne en ambas ramas (HITL y auto-aprobación) de forma consistente.

**Estado:** ✅ Corregido.

---

## 2026-08-11 — QA-001 caído en revisión humana (HITL) en vez de auto-aprobarse

**Síntoma**
Según `qa_manual_testing_cases_v2.csv` (fila QA-001), el pedido ORD-QA-0001
(alimentación, `defective`, 5/14 días, 29.99€) debería **aprobarse
automáticamente**. Al probarlo en la app, el flujo terminó en
"Tu solicitud sigue pendiente de revisión por nuestro equipo" (HITL), sin
llegar a la aprobación automática.

**Causa raíz (identificada, no corregida)**
`rule_deadline_borderline` (`backend/agents/nodes/policy_rules.py:126-136`)
marca `human_review` si `days_since_order` cae en la franja
`[max_return_days - 2, max_return_days + 5]` → para alimentación
(`max_return_days=14`) eso es `[12, 19]` días.

El seed (`usecasetotest/RESET_AND_SEED_COMPLETE.sql:119`) fija
`delivered_at = NOW() - INTERVAL '5 days'` **en el momento de ejecutar el
script**, no relativo al día de la prueba. Si el seed se ejecutó hace más de
~7 días, `days_since_order` real ya ha superado 12 y el caso entra en la
"zona frontera", aunque el CSV documente 5 días fijos.

**Estado:** ⏳ Pendiente — causa identificada, sin corregir todavía.
Opciones para la próxima sesión:
1. Re-sembrar `usecasetotest/RESET_AND_SEED_COMPLETE.sql` antes de cada
   tanda de pruebas (fechas relativas se recalculan desde "ahora").
2. Cambiar el seed para fijar `delivered_at` con fecha absoluta y
   documentar en `qa_manual_testing_cases_v2.csv` la fecha de referencia,
   en vez de días relativos a la ejecución del script.
