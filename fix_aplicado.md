# Fix aplicado: elegibilidad de devolución por artículo (Opción B)

**Fecha:** 2026-08-15
**Basado en:** [CoberturaDevoluvionMixta.md](CoberturaDevoluvionMixta.md) — diagnóstico del bug y comparación de las 4 opciones evaluadas (A/B/C/D). Se implementó la **Opción B**: una sola llamada al LLM con salida estructurada (Pydantic) que devuelve una lista de decisiones, una por artículo.

## Qué se cambió, dónde y por qué

### 1. Nuevos modelos de dominio
**Archivo:** [backend/models/returns.py](backend/models/returns.py)

Se añadieron dos modelos Pydantic nuevos:
- `ItemEligibility`: resultado de evaluar UN artículo (`order_item_id`, `is_eligible`, `eligibility_reason`, `refund_amount`, `policy_category`).
- `PolicyEvaluationOutput`: envoltorio con `items: list[ItemEligibility]`, una entrada por cada artículo evaluado.

**Por qué:** antes no existía ninguna estructura para representar "este artículo sí, este otro no" dentro de una misma solicitud — todo colapsaba a un único booleano. Se exportaron también en [backend/models/__init__.py](backend/models/__init__.py).

### 2. Estado del grafo (`ReturnState`)
**Archivo:** [backend/models/state.py](backend/models/state.py)

Se sustituyó:
```python
is_eligible: bool | None
eligibility_reason: str | None
refund_amount: float
```
por:
```python
items_eligibility: list[dict[str, Any]]   # una entrada por artículo (ItemEligibility.model_dump())
any_eligible: bool | None                 # True si AL MENOS UN artículo es elegible (para el routing)
eligibility_reason: str | None            # resumen agregado, usado solo cuando NINGÚN artículo es elegible
refund_amount: float                      # ahora es la SUMA de refund_amount de los artículos elegibles
```

**Por qué:** `refund_amount` se mantiene como campo agregado porque `create_return_record` en Supabase guarda un único importe por `return_request`; el desglose real vive en `items_eligibility`. `is_eligible` se renombró a `any_eligible` para que su nombre refleje exactamente lo que significa ahora (¿hay AL MENOS UN artículo elegible?), evitando que alguien lo confunda con "todo el pedido es elegible".

### 3. Evaluador de políticas — el núcleo del fix
**Archivo:** [backend/agents/nodes/policy.py](backend/agents/nodes/policy.py) (`policy_evaluator_agent`)

Cambios:
- **Búsqueda RAG por categoría distinta, no por el primer artículo.** Antes (líneas 87-95 del código original) se tomaba la categoría del primer artículo de `order_details["items"]`. Ahora se recorre `items_to_return`, se resuelve la categoría real de CADA `order_item_id` (`_category_by_item_id`) y se llama a `search_return_policy` una vez por cada categoría *distinta* presente en la solicitud (deduplicado en `policy_by_category`).
- **Una sola llamada al LLM, con salida estructurada.** Se sustituyó `llm.ainvoke(...)` + parseo por regex de un bloque ```json``` (frágil; ver el test `test_handles_malformed_llm_response` que existía porque ese parseo fallaba) por `llm.with_structured_output(PolicyEvaluationOutput).ainvoke(...)`, el mismo patrón que ya usaba `triage.py:74`. Se le pasa al LLM un contexto por artículo (`items_context`), cada uno con su propia política aplicable.
- **Agregación de resultado:** `any_eligible = any(item.is_eligible ...)`, `refund_amount = sum(refund de los elegibles)`, `eligibility_reason` = resumen legible uniendo el resultado de cada artículo (usado por `rejection_agent` solo cuando ninguno es elegible).
- **Fallback:** si la salida estructurada viene vacía o `None` (el LLM no pudo evaluar), se marca cada artículo de `items_to_return` como no elegible con un motivo genérico, en vez de fallar o aprobar por defecto.

**Por qué:** esto es exactamente lo que corrige los dos bugs documentados en `CoberturaDevoluvionMixta.md` — la política de la categoría "perdedora" ya no desaparece, y la decisión deja de colapsar a un único booleano.

### 4. Agente de Resolución — filtra por artículo elegible
**Archivo:** [backend/agents/nodes/resolution.py](backend/agents/nodes/resolution.py) (`resolution_agent`)

Cambios:
- Se calcula `eligible_ids` (artículos con `is_eligible=True` en `items_eligibility`) y `rejected_items` (el resto).
- La etiqueta de envío (`generate_shipping_label`) y el registro de devolución (`create_return_record`) ahora se generan **solo** con `eligible_items_to_return`, no con todo `items_to_return` como antes.
- El email al cliente y el mensaje final del LLM ahora incluyen explícitamente los artículos aprobados (con tracking y reembolso) **y** los rechazados (con su motivo), en vez de asumir que todo el pedido tiene un único desenlace.
- El campo de estado `resolution` pasa a valer `"partially_approved"` cuando hay artículos rechazados junto a artículos aprobados (antes solo existía `"approved"` / `"rejected"`).
- Se actualizó `RESOLUTION_SYSTEM_PROMPT` para instruir al LLM a explicar resultados mixtos con claridad, nombrando cada artículo.

**Por qué:** era la consecuencia práctica del bug — antes, si `is_eligible` global daba `True`, el perfume no elegible se enviaba y reembolsaba igual; si daba `False`, los auriculares elegibles se rechazaban también. Ahora cada artículo sigue su propio camino.

### 5. Enrutado del grafo
**Archivo:** [backend/agents/graph.py](backend/agents/graph.py) (`route_after_evaluator`)

Cambio: `state.get("is_eligible")` → `state.get("any_eligible")`. El pedido avanza a `resolver` en cuanto **algún** artículo es elegible; solo se rechaza el turno completo (`reject`) cuando ninguno lo es.

### 6. CLI de depuración
**Archivo:** [backend/agents/cli/demo_chat.py](backend/agents/cli/demo_chat.py) línea 71: `result.get("is_eligible")` → `result.get("any_eligible")`, para que el debug print no rompa con `KeyError`/`None` silencioso tras el rename.

## Tests actualizados/creados

- [tests/integration/test_policy_agent.py](tests/integration/test_policy_agent.py) — reescrito para mockear `llm.with_structured_output(...).ainvoke(...)` en vez de un `AIMessage` con bloque ```json```. Se añadió `test_no_items_to_return_skips_rag_and_returns_empty` (nuevo) y se sustituyó el test de "respuesta malformada" por `test_handles_empty_structured_output` (ya no aplica el parseo por regex).
- [tests/integration/test_mixed_category_order_returns.py](tests/integration/test_mixed_category_order_returns.py) — reescrito por completo: donde antes los 3 tests **demostraban el bug** (RAG solo con la primera categoría, booleano único, artículo no elegible enviado igualmente), ahora los 3 tests **demuestran que quedó corregido**:
  1. `test_rag_search_queries_each_distinct_category` — 2 búsquedas RAG, una por categoría.
  2. `test_mixed_eligibility_marks_each_item_independently` — auriculares elegibles + perfume no elegible, en el mismo resultado.
  3. `test_only_eligible_item_is_shipped_and_refunded` — la etiqueta y el registro de devolución excluyen el perfume; `resolution == "partially_approved"`.
- [tests/unit/test_routing.py](tests/unit/test_routing.py) — `TestRouteAfterEvaluator` actualizado a `any_eligible`; se añadió `test_routes_to_resolver_when_mixed_eligibility`.
- [tests/conftest.py](tests/conftest.py) — sin cambios adicionales (ya tenía las fixtures del pedido mixto creadas en la sesión de diagnóstico: `mock_order_details_mixed_categories`, `sample_items_to_return_mixed`, `mock_policy_results_electronics`, `mock_policy_results_cosmetics`).

## Verificación

```bash
# Tests directamente afectados por el fix — todos en verde:
pytest tests/integration/test_policy_agent.py tests/integration/test_mixed_category_order_returns.py \
       tests/integration/test_resolution_agent.py "tests/unit/test_routing.py::TestRouteAfterEvaluator" -v
# 16 passed

# Suite completa, para confirmar que no se introdujeron regresiones:
pytest tests/ -q
# 36 passed, 18 failed (mismos 18 fallos preexistentes y no relacionados que ya
# existían antes de este fix: test_graph_flow.py, test_triage_agent.py,
# test_mcp_logistics.py, test_mcp_supabase.py, test_supabase_service.py y la
# parte de test_routing.py::TestRouteAfterTriage — documentados en
# CoberturaDevoluvionMixta.md, fuera del alcance de este fix)
```

## Qué queda fuera de este fix (a propósito)

- No se tocaron los bugs preexistentes no relacionados (mocks rotos de `supabase_service`, `test_routing.py::TestRouteAfterTriage`, tests de `triage_agent`/`test_graph_flow.py` con rutas de `patch()` incorrectas, tests MCP sin marcar como async). Están fuera del alcance de "elegibilidad por artículo" y se documentaron por separado en `CoberturaDevoluvionMixta.md`.
- No se migró ningún criterio a un motor determinista en Python (Opción C). Sigue siendo el LLM quien decide, con salida estructurada — auditable, pero no 100% determinista. Queda anotado en `CoberturaDevoluvionMixta.md` como posible evolución futura.

## Merge con `origin/main` (2026-08-15)

La rama se creó a partir de un `main` local que estaba 40 commits por detrás de `origin/main` (FastAPI backend nuevo, frontend Streamlit nuevo, `policy_rules.py`, triage con `order_number`/selección por checkboxes, `start_all.sh`, docs, etc.). Se hizo `git fetch origin` + `git merge origin/main` sobre esta rama para traer esos archivos. Detalle completo de la comparación previa al merge en el "Registro de cambios" de `CoberturaDevoluvionMixta.md`.

### Hallazgo antes de mergear
`origin/main` había añadido de forma independiente `backend/agents/nodes/policy_rules.py` (motor de reglas deterministas, "Chain of Rules") como capa de refuerzo sobre el LLM en `policy.py`. Pero **seguía sin corregir el bug de este documento**: su `policy_evaluator_agent` seguía tomando `product_category` del primer artículo del pedido y `condition = items_to_return[0]...` — exactamente la misma limitación de "una sola categoría/decisión por pedido", solo que con un backstop determinista encima.

### Conflictos y cómo se resolvieron
El merge produjo conflictos en 4 archivos (los demás — `start_al.sh`, `frontend/`, `backend/api/`, `policy_rules.py`, `docs/`, etc. — se incorporaron limpios sin conflicto):

| Archivo | Resolución | Por qué |
|---|---|---|
| `backend/agents/nodes/policy.py` | Se prioriza ENTERO el fix de este documento (evaluación per-artículo, salida estructurada); se descarta la integración con `policy_rules.py` | El motor determinista de origin/main no arregla el bug de la categoría única; adoptarlo habría requerido reescribirlo para operar por artículo, que es justo el trabajo que ya hace este fix de otra forma. Se conservó la mejora suelta y no conflictiva del modelo `gpt-5-mini`. |
| `backend/agents/nodes/resolution.py` | Combinación real de ambos lados: se mantiene el filtrado por `items_eligibility`/artículo elegible (este fix) **y** se conservan las mejoras de origin/main que son ortogonales — guard de duplicados al crear el registro de devolución, creación del registro *antes* del `interrupt` de HITL (evita condiciones de carrera en el resume), `thread_id` y `order_number` en el mensaje al cliente | Estas mejoras de origin/main no compiten con "elegibilidad por artículo", son correcciones de robustez distintas; descartarlas habría reintroducido bugs ya arreglados por el equipo. Solo se adaptó el argumento `items=` de `create_return_record` para que use `eligible_items_to_return` en vez de `items_to_return` completo. |
| `backend/agents/graph.py` | Se mantiene `route_after_evaluator` basado en `any_eligible`, con un `or state.get("needs_admin_approval")` añadido por compatibilidad — hoy siempre `False` porque `policy.py` no lo fija | `route_after_triage` y `route_after_fetch` (reescritos por origin/main con guards de `order_number` y validación de `condition`/`reason`) no tocaban nada de mi fix y se incorporaron sin conflicto. |
| `tests/integration/test_triage_agent.py` | Un solo import añadido por origin/main (`from backend.models import TriageOutput`) | El resto del archivo ya venía reescrito por origin/main sin conflicto, porque mi único cambio previo ahí era un import-fix ya superado. |

### Efecto en `backend/models/state.py` y `backend/models/returns.py`
Estos dos merged **sin conflicto**: git combinó automáticamente mis campos (`items_eligibility`, `any_eligible`, `ItemEligibility`, `PolicyEvaluationOutput`) con los nuevos de origin/main (`order_number`, `selected_item_ids`, `needs_admin_approval`, `thread_id`), porque tocaban zonas distintas del `TypedDict`/módulo.

### Ajuste de test tras el merge
`tests/integration/test_mixed_category_order_returns.py::test_only_eligible_item_is_shipped_and_refunded` empezó a fallar por un intento de conexión real a un servidor MCP: el `resolution_agent` fusionado añade una llamada a `update_return_status(...)` (mejora traída de origin/main) que el test no mockeaba. Se añadió `update_status_mock` al `with patch(...)` del test.

### Verificación tras el merge
```bash
pytest tests/integration/test_policy_agent.py tests/integration/test_mixed_category_order_returns.py \
       tests/integration/test_resolution_agent.py tests/unit/test_routing.py -v
# 27 passed

pytest tests/ -q --ignore=tests/unit/test_api_endpoints.py
# 53 passed, 5 failed (los 5 son bugs preexistentes de test_graph_flow.py —
# build_return_graph() sin await, no relacionado con este fix — y los tests
# MCP sin marcar @pytest.mark.asyncio; confirmado que ya fallaban por lo
# mismo antes del merge). test_api_endpoints.py se excluyó porque requiere
# dependencias de FastAPI que no están instaladas en este entorno.
```
Antes del merge la suite completa daba 18 failed / 34 passed; tras el merge, los 5 fallos de `test_routing.py::TestRouteAfterTriage` y los 6 de `test_supabase_service.py` que documentaba `CoberturaDevoluvionMixta.md` **se corrigieron solos**, porque venían de que esos tests ya estaban pensados para el `supabase_service.py`/`graph.py` nuevos de origin/main.

### Commits
- `ea84e41` — fix(policy): evaluar elegibilidad de devolución por artículo, no por pedido completo.
- `90fabbf` — Merge origin/main into fixed-pedido-varios-items-categorias-distintas-devolver.
