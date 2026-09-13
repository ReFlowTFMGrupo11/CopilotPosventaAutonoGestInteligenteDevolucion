# Defender el dashboard de costes propio de ReFlow

Este documento recoge los argumentos para defender, en la memoria/presentación del
TFM, el dashboard propio de coste y latencia (`frontend/pages/2_Costes.py`,
`backend/services/usage_service.py`, `backend/agents/usage_tracking.py`), y en
particular por qué existe **además de** LangFuse (ver
[`defenderLangfuse.md`](defenderLangfuse.md)) en vez de sustituirlo o depender
solo de él.

## 1. Por qué existe: un hueco de alcance explícito, no una ocurrencia tardía

### El planteamiento
La PR de controles de terminación de agentes dejó fuera a propósito un contador
de coste acumulado por sesión, con la nota explícita de que requería tocar
`state.py`, un tracker nuevo y parsear `usage_metadata` de cada respuesta —
"puedo abordarlo en una PR aparte". Este dashboard es esa PR aparte.

### Argumentos para defenderlo
- No es una funcionalidad añadida sin motivo: cubre un límite de alcance ya
  documentado y aceptado en una PR anterior, con su propia justificación de
  por qué se difirió entonces.
- El control de gasto por sesión es, en sí, uno de los controles de
  terminación/anti-abuso del sistema (junto a `GRAPH_RECURSION_LIMIT`,
  `GRAPH_TURN_TIMEOUT_SECONDS`, `MAX_CONVERSATION_TURNS` — ver
  `backend/config.py`), no una feature de observabilidad aislada.

## 2. Diseño de instrumentación: wrappers en el punto de llamada, no en cada nodo

### El planteamiento
`backend/agents/usage_tracking.py` expone dos funciones, `invoke_tracked()` e
`invoke_structured_tracked()`, que envuelven `ainvoke()` midiendo latencia
(`time.perf_counter()`) y extrayendo `usage_metadata`. `triage.py`, `evaluator.py`
y `resolution.py` sustituyen sus llamadas directas al LLM por estos wrappers en
los 4 puntos donde ya invocaban al modelo — sin cambiar su lógica de negocio.

### Argumentos para defenderlo
- **Cero intrusión en la lógica de decisión:** el wrapper solo envuelve la
  llamada; no toca qué hace cada nodo con el resultado. Es el mismo criterio
  que llevó a extraer `llm_factory.py` (una factory, no lógica de negocio,
  ver `defenderAgentes.md`) — la instrumentación es infraestructura transversal,
  no debe mezclarse con las reglas de negocio de cada nodo.
- **`include_raw=True` es la única forma de llegar a `usage_metadata` con
  salida estructurada:** por defecto, `with_structured_output()` descarta el
  `AIMessage` crudo y devuelve solo el objeto Pydantic parseado — junto con el
  mensaje se pierde el conteo de tokens. `invoke_structured_tracked()` pide el
  `AIMessage` crudo explícitamente y aun así devuelve al llamador el mismo
  contrato de antes (`SchemaT | None`), así que `triage_agent`/`evaluator_agent`
  no notan la diferencia salvo por el registro de uso.
- **Un fallo al registrar el uso nunca rompe el turno del cliente:**
  `_log_usage()` atrapa cualquier excepción y solo loguea un warning. Es
  observabilidad, no debe convertirse en un punto de fallo del flujo de
  devoluciones — mismo principio que el diseño "fail-open" de LangFuse (ver
  `defenderLangfuse.md`, sección 9).

## 3. Diseño de pricing: precios a mano, con override, y "coste incompleto" en vez de mentir

### El planteamiento
`backend/services/pricing.py` fija a mano los precios por token de
`gpt-5-nano`/`gpt-5-mini` (USD/1M) y el tipo de cambio USD→EUR, ambos
sobreescribibles por env var. Si una sesión usa un modelo sin precio
configurado, se marca como coste incompleto en vez de mostrar una cifra.

### Argumentos para defenderlo
- **OpenAI no expone precios vía API** — no hay alternativa a fijarlos a mano
  en algún sitio; la pregunta relevante no es "¿por qué a mano?" sino "¿por qué
  aquí, en este servicio, y no en otro sitio?" (ver sección 4, punto 3).
- **Override por env var sin tocar código:** si un precio cambia o se añade un
  modelo nuevo, `LLM_PRICE_<MODELO>_INPUT_PER_1M`/`_OUTPUT_PER_1M` lo corrige
  sin desplegar código nuevo.
- **"Coste incompleto" en vez de 0€ o una cifra inventada:** un panel que
  muestre confiadamente "2,50€" cuando en realidad no sabe el precio de un
  modelo es peor que uno que admita "no lo sé" — la primera decisión de
  producto de este módulo fue no fingir precisión que no existe.

## 4. Por qué dashboard propio y no (solo) LangFuse — la pregunta real

### El planteamiento
ReFlow ya tenía LangFuse integrado, con soporte de agrupación por sesión
(`langfuse_session_id`) y cliente (`langfuse_user_id`) — ver `defenderLangfuse.md`.
El propio código lo decía explícitamente: el docstring original de
`with_langfuse()` justificaba taggear sesión/cliente para "ver coste acumulado
por sesión en su dashboard, **sin tracking propio**". Este módulo construye
justo ese tracking propio. La pregunta que hay que responder de frente es:
**¿por qué no bastaba con lo que ya había?**

### Argumentos para defenderlo

**No es que LangFuse "no pueda" tener el dato — es que agregar por pedido no
es una vista nativa.** Se podría mandar `order_id` a LangFuse como metadata
arbitraria sin ningún problema técnico. Pero `session_id`/`user_id` son
ciudadanos de primera clase en LangFuse: tienen pestaña propia
("Sessions"/"Users") con agregación de coste/latencia ya construida en el
dashboard. Un campo de metadata arbitrario como `order_id` no tiene esa vista
— LangFuse deja *filtrar* trazas por `metadata.order_id = X` una por una, no
te da automáticamente "coste total por pedido, de mayor a menor". Conseguir
eso exigiría o bien la función de *custom dashboards* de LangFuse (no
disponible en el tier gratuito que usa este proyecto, ver
`defenderLangfuse.md` §3), o consultar su API y construir la agregación a
mano — que es exactamente el mismo trabajo que ya se hizo, solo que contra
Supabase en vez de contra un servicio externo.

**LangFuse es opcional y fail-open por diseño; el control de gasto no puede
serlo.** Si `LANGFUSE_SECRET_KEY`/`PUBLIC_KEY` no están en `.env` — durante la
propia defensa del TFM, en CI, o en cualquier entorno donde no se haya
configurado — `with_langfuse()` devuelve el config sin cambios y la app
funciona igual, sin trazas. Eso es correcto para observabilidad (LangFuse no
debe ser un punto de fallo), pero es exactamente lo contrario de lo que se
necesita para un control de gasto: uno de los controles de terminación de
agentes (junto a los límites de turnos/recursión), que debe funcionar siempre,
no solo cuando un servicio de terceros esté configurado.

**Control total sobre el pricing de modelos nuevos.** `gpt-5-mini`/`gpt-5-nano`
no tienen por qué estar en la tabla de precios que mantenga LangFuse
internamente — si no los conoce, mostraría 0€ o un coste incorrecto sin
avisar. `pricing.py` ya resuelve esto con override por env var y un estado
explícito de "coste incompleto" (sección 3) en vez de una cifra silenciosamente
mal calculada por un sistema externo que no se controla.

**Misma base de datos que el resto del panel admin.** `list_returns`,
`list_pending_approvals`, `get_return_detail` — todo el panel admin ya lee de
Supabase directamente vía `supabase_service`. Añadir `usage_service` a esa
misma capa es consistente con la arquitectura existente; depender de la API de
LangFuse para una vista de negocio habría introducido una dependencia externa
nueva justo en la única parte del sistema pensada para funcionar sin ellas.

### Cuándo usar cada uno — la división de responsabilidades real

No son dos sistemas redundantes: sirven a **audiencias y preguntas distintas**.

| | LangFuse | Dashboard propio |
|---|---|---|
| **Audiencia** | Quien desarrolla/depura el agente | Quien opera el negocio (admin) |
| **Pregunta que responde** | "¿Por qué el LLM respondió esto en este turno?" | "¿Cuánto nos está costando este pedido/cliente?" |
| **Granularidad** | Traza completa por llamada: prompt, respuesta, pasos intermedios | Fila agregada por sesión/pedido/cliente: tokens, coste, latencia |
| **Dimensión de negocio (pedido)** | No — solo sesión/usuario | Sí — es la razón de ser de este dashboard |
| **Disponibilidad** | Opcional, fail-open (puede no estar configurado) | Siempre (misma BD que el resto del panel admin) |
| **Uso típico** | Depurar un caso concreto, evaluar prompts (Datasets/Experiments) | Vigilar gasto agregado, detectar sesiones/pedidos anómalamente caros |

**Usa LangFuse** para entender qué pasó dentro de una llamada concreta, comparar
versiones de un prompt, o evaluar el sistema con datasets (ver
`defenderLangfuse.md`, sección 8). **Usa el dashboard propio** para responder
"¿cuánto gasta la operación, agregado por pedido o cliente, y siempre
disponible" — la pregunta operativa de negocio, no la de ingeniería de prompts.

## 5. Preguntas típicas de la defensa

**Si LangFuse permite metadata arbitraria, ¿por qué no simplemente mandarle
`order_id` y usar su API para construir la misma tabla, en vez de una tabla
nueva en Supabase?**
Porque en ese punto el trabajo de agregación (agrupar por pedido, calcular
coste con `pricing.py`, decidir qué es "coste incompleto") es idéntico se haga
contra la API de LangFuse o contra Supabase — no se ahorra nada de
implementación, solo se cambiaría de dónde se lee el dato. Y leerlo de
Supabase mantiene la consistencia con el resto del panel admin, que ya lee de
ahí, sin añadir una dependencia de red a un servicio opcional para una vista
de negocio que debe estar siempre disponible.

**¿No es esto duplicar esfuerzo — dos sistemas de tracking en el mismo
proyecto?**
Hay solape parcial en el nivel más alto (coste total, latencia media también
se ven en LangFuse), pero no en la dimensión que importa para el negocio
(pedido/cliente) ni en la disponibilidad garantizada. El solape real y
evitable era otro: el docstring de `with_langfuse()` seguía diciendo "sin
tracking propio" cuando ya existía — eso sí era una inconsistencia a corregir,
no el diseño en sí.

**¿Por qué no calcular el coste al vuelo en cada llamada en vez de guardar
tokens crudos y calcular el precio después?**
Porque los precios cambian y `pricing.py` ya lo prevé (override por env var).
Si el coste se calculara y guardara en el momento de la llamada, una
corrección de precio posterior no podría aplicarse retroactivamente a las
filas ya insertadas. Guardando `input_tokens`/`output_tokens` crudos en
`llm_usage` y calculando el coste en `get_usage_by_session()` en tiempo de
lectura, corregir un precio en `pricing.py` corrige automáticamente el coste
mostrado de todo el historial, sin migrar datos.

**¿Qué pasa si `pricing.py` no conoce el modelo usado en una sesión?**
`estimate_cost_eur()` devuelve `None` para esa llamada; la sesión se marca
como coste incompleto en el dashboard en vez de sumar 0€ silenciosamente (lo
que subestimaría el coste real sin que nadie lo note). Ver sección 3.
