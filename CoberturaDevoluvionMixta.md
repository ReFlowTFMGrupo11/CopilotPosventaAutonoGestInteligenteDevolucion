# Cobertura de devolución mixta (pedido con varias categorías, elegibilidad parcial)

**Proyecto analizado:** `TFMGRUPO11/CopilotPosventaAutonoGestInteligenteDevolucion` (el copiloto "ReFlow": Triaje → Evaluador de Políticas → Resolución, orquestado con LangGraph, con RAG sobre políticas por categoría en `dataset/policies/`).

**Pregunta a validar:** si un pedido contiene productos de distintas categorías, algunos de los cuales cumplen la política de devolución y otros no, ¿la app es capaz de decidir la elegibilidad por artículo, marcar cuáles se devuelven y cuáles no, y comunicárselo así al cliente en una sola respuesta?

## Veredicto

**No, la funcionalidad no está cubierta.** La app no evalúa la elegibilidad de devolución artículo por artículo. Se verificó construyendo tests contra el código real (no simulados), y los tres pasan confirmando el bug.

## Causa raíz

En [backend/agents/nodes/policy.py](backend/agents/nodes/policy.py) (`policy_evaluator_agent`):

- **Líneas 87–95:** para decidir qué política buscar por RAG, recorre `order_details["items"]` y se queda con la categoría del **primer artículo que tenga categoría** — no la del artículo (o artículos) que el cliente realmente quiere devolver. Si el pedido tiene electrónica + cosmética y el cliente pide devolver ambos, solo se consulta la política de electrónica; la de cosmética (donde el perfume no sería elegible) nunca se recupera.
- **Líneas 146–166:** el resultado del LLM se parsea a **un único** `is_eligible` (bool), `refund_amount` (float) y `eligibility_reason` (str) para toda la solicitud. En [backend/models/state.py](backend/models/state.py) (`ReturnState`) tampoco existe ningún campo para un desglose por artículo — no hay `items_eligibility` ni nada parecido.
- **Consecuencia** en [backend/agents/nodes/resolution.py](backend/agents/nodes/resolution.py) líneas 130–143: si el flag global queda en `True`, el agente de Resolución genera etiqueta de envío y registra el reembolso para **todos** los `items_to_return`, incluido el que no debería devolverse. Si queda en `False`, se rechaza el pedido entero, perdiendo también el artículo que sí era elegible.

## Tests construidos

- Se arreglaron imports rotos preexistentes en `tests/integration/test_policy_agent.py`, `test_resolution_agent.py` y `test_triage_agent.py` (apuntaban a `backend.agents.policy_agent` etc., un módulo que ya no existe; el código se movió a `backend.agents.nodes.*`). Antes de esto, esos tres ficheros ni siquiera se podían recolectar — es decir, 0% de esa lógica se estaba verificando.
- Se añadieron fixtures de un pedido mixto (auriculares `electronica_informatica` elegibles + perfume `cosmetica_perfumeria` no elegible por precinto de higiene) en `tests/conftest.py`.
- Nuevo fichero [tests/integration/test_mixed_category_order_returns.py](tests/integration/test_mixed_category_order_returns.py) con 3 tests, todos en **PASS** contra el código actual (lo cual demuestra el gap, no lo oculta):
  1. `test_rag_search_only_considers_first_item_category` — la búsqueda RAG solo usa la categoría del primer artículo.
  2. `test_single_boolean_cannot_represent_mixed_eligibility` — aunque el LLM razone correctamente sobre ambos artículos, el estado solo guarda un booleano global.
  3. `test_ineligible_item_is_shipped_and_refunded_when_overall_flag_is_true` — el artículo no elegible acaba con etiqueta de envío y reembolso igualmente.

## Otros hallazgos (fuera del foco principal)

De paso quedó a la vista que la suite tiene más problemas preexistentes no relacionados (mocks de `supabase_service`, `test_routing.py`, tests de `triage_agent` mal mockeados, tests MCP sin marcar como async) — **18 failed / 34 passed** en total con `pytest tests/ -q`. No se tocaron por no ser el foco de esta pregunta, pero confirman que este proyecto tiene poca cobertura real hoy.

## Cómo reproducir

```bash
# Solo los tests del escenario de pedido mixto:
pytest tests/integration/test_mixed_category_order_returns.py -v

# Suite de policy + resolution (ya arreglada):
pytest tests/integration/test_policy_agent.py tests/integration/test_resolution_agent.py -q

# Suite completa (muestra el estado general, con fallos preexistentes no relacionados):
pytest tests/ -q
```

## Posibles soluciones

**A. Bucle con una llamada al LLM por artículo (o por categoría distinta)**
El evaluador itera `items_to_return`, agrupa por categoría, hace 1 búsqueda RAG y 1 llamada al LLM por artículo/categoría, y agrega los resultados en una lista.
- 👍 Sencillo de razonar, cada llamada es un caso aislado y fácil de testear.
- 👎 N llamadas al LLM por solicitud (coste y latencia), y sigue dependiendo del parseo frágil por regex de bloque ```json``` que ya hoy provoca el test de "respuesta malformada" en `policy.py:152-166`.

**B. Una sola llamada con salida estructurada (Pydantic) que devuelve una lista de decisiones**
Se define un modelo `ItemEligibility` (`order_item_id`, `is_eligible`, `eligibility_reason`, `refund_amount`, `policy_applied`) y un `PolicyEvaluationOutput` con `items: list[ItemEligibility]`. Se hace RAG una vez por cada categoría *distinta* presente en `items_to_return` (deduplicado), se pasa todo el contexto en una sola llamada, y se usa `llm.with_structured_output(...)` para obtener la lista ya tipada.
- 👍 Una sola llamada al LLM. Elimina el parseo por regex (fuente de bugs) usando el mismo patrón que **ya existe** en `triage.py:74` (`llm.with_structured_output(TriageOutput)`), así que no introduce un patrón nuevo en el proyecto.
- 👍 El LLM sigue pudiendo aplicar matices textuales de la política (alergias, "wrong_item_shipped", etc.) que no siempre están en campos estructurados.
- 👎 Sigue siendo el LLM quien decide (auditable pero no 100% determinista).

**C. Motor de decisión determinista en Python + LLM solo para redactar**
El RAG ya devuelve `policy_info` con campos estructurados (`max_return_days`, `allowed_conditions`, `requires_original_packaging`, `restocking_fee_percent`). Se compara en Python, por artículo, contra `days_since_delivery` y `condition`, sin pedirle la decisión al LLM — el LLM solo redacta el mensaje final a partir del veredicto ya calculado. (Esto es justo lo que el proyecto hermano `TFM-Tamara-Cris` documenta como corrección pedida por el profesor: *"el LLM explica, pero `evaluate_eligibility()` decide"*.)
- 👍 100% determinista, auditable y testeable sin mockear ningún LLM para la lógica central.
- 👎 Hay que codificar a mano la casuística legal de las 17 categorías (excepciones de higiene, perecederos, etc.), y mantenerla sincronizada si cambian los `.md` de políticas.

**D. Fan-out con la API `Send` de LangGraph (subgrafo por artículo)**
Un nodo dispara una evaluación en paralelo por cada `order_item_id` como sub-ejecuciones del grafo, reducidas después a una lista en el estado.
- 👍 Patrón "canónico" de LangGraph para procesar colecciones.
- 👎 Complejidad de orquestación (nodo fan-out, reducer, más superficie que testear) injustificada para pedidos que en la práctica tienen pocas líneas.

### Recomendación

**Opción B: una sola llamada con salida estructurada (lista de `ItemEligibility` vía `with_structured_output`).**

Por qué es la más sencilla, clara y mantenible en este proyecto concreto:
- Reutiliza un patrón que el propio código **ya usa y ya funciona** (`triage.py`), así que no añade un mecanismo nuevo que aprender ni mantener aparte.
- Resuelve de un solo golpe los dos bugs documentados arriba: la búsqueda RAG que solo mira la categoría del primer artículo (pasa a buscar 1 política por cada categoría distinta en `items_to_return`) y el colapso a un único booleano (pasa a una lista con un veredicto por `order_item_id`).
- Es más fácil de testear que A (menos combinaciones de mocks, una sola llamada) y no exige reimplementar a mano la casuística legal de 17 categorías como C — que es correcta pero cara de mantener si las políticas cambian.
- El cambio de estado es acotado: sustituir `is_eligible: bool`/`refund_amount: float`/`eligibility_reason: str` en `ReturnState` por `items_eligibility: list[dict]`, derivando de ahí un `any_eligible` para el enrutado (`route_after_evaluator`) y filtrando en `resolution_agent` solo los artículos con `is_eligible=True` antes de generar etiqueta/reembolso.

La D se descarta salvo que en el futuro los pedidos puedan tener decenas de líneas — hoy sería sobreingeniería. La C es la más robusta a largo plazo si se quiere auditoría legal estricta, pero es más trabajo de mantenimiento por categoría; podría ser una evolución de B más adelante (usar B ahora, migrar los criterios más objetivos —plazos, condiciones— a Python cuando se estabilicen, dejando al LLM solo los matices).

## Registro de cambios

> A medida que se vaya implementando la opción elegida, cada cambio se añade aquí con: **qué** se cambió, **dónde** (archivo/línea) y **por qué**, para que este documento quede como historial vivo de la corrección.

- **2026-08-15 — Documentación inicial.** Se creó este documento con el diagnóstico del bug (pedido mixto colapsado a una sola decisión), los tests que lo demuestran (`tests/integration/test_mixed_category_order_returns.py`) y las 4 opciones de solución evaluadas. Aún no se ha tocado código de producción (`backend/agents/nodes/policy.py`, `resolution.py`, `backend/models/state.py`); solo tests y este `.md`. Motivo: alinear primero el enfoque con el usuario antes de implementar.
- **2026-08-15 — Opción B implementada.** Se implementó la corrección elegida (salida estructurada por artículo). Detalle completo de qué se cambió, en qué archivo/línea y por qué: [fix_aplicado.md](fix_aplicado.md). Resumen: `policy_evaluator_agent` ahora evalúa cada artículo con su propia política vía RAG y una única llamada al LLM con salida estructurada (`PolicyEvaluationOutput`); `resolution_agent` filtra y solo procesa los artículos elegibles, explicando también los rechazados. Tests directamente afectados: 16/16 en verde; suite completa sin regresiones (36 passed, mismos 18 fallos preexistentes no relacionados).
- **2026-08-15 — Merge con `origin/main`.** La rama estaba basada en un `main` local 40 commits por detrás de `origin/main` (FastAPI backend, frontend Streamlit, `policy_rules.py`, triage con `order_number`/checkboxes, `start_all.sh`, docs...). Se hizo `git fetch` + `git merge origin/main`. Hallazgo relevante: `origin/main` ya tenía su propio motor de reglas deterministas (`policy_rules.py`) pero **seguía sin corregir** el bug de "categoría del primer artículo" documentado aquí. En los 4 archivos con conflicto (`policy.py`, `resolution.py`, `graph.py`, `test_triage_agent.py`) se priorizó la funcionalidad de este fix, pero conservando de `resolution.py` las mejoras de origin/main que no competían con ella (guard de duplicados, registro creado antes del interrupt de HITL, `thread_id`/`order_number`). Detalle completo de la resolución archivo por archivo, con tabla de qué se mantuvo y por qué: [fix_aplicado.md](fix_aplicado.md#merge-con-originmain-2026-08-15). Tras el merge, la suite completa pasó de 18 failed/34 passed a **5 failed/53 passed** (los 5 restantes, preexistentes y no relacionados). Commits: `ea84e41` (fix) y `90fabbf` (merge).
