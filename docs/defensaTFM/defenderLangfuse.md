# Defensa de la Observabilidad con LangFuse

## 1. ¿Qué es LangFuse y por qué lo usamos?

El grafo de agentes (Triage → Policy Evaluator → Resolution) hace varias llamadas
a un LLM por conversación, cada una con su propio prompt, contexto RAG, tokens
consumidos y latencia. Sin instrumentación, la única forma de depurar un caso
que salió mal es leer logs de consola línea a línea. **LangFuse** traza cada
llamada al LLM dentro del grafo (prompt, respuesta, tokens, coste, latencia,
tool calls) y las agrupa por conversación en un panel web navegable.

### Alternativas descartadas

| Alternativa | Por qué se descartó |
|-------------|----------------------|
| `logging` / prints a consola | Sin estructura ni UI: para reconstruir una conversación de 3 agentes hay que grepear timestamps a mano. No compara ejecuciones entre sí |
| LangSmith | Mismo propósito, pero acoplado al ecosistema LangChain de forma más cerrada |
| Weights & Biases (Prompts) | Pensado para tracking de experimentos ML clásicos (hiperparámetros, curvas de entrenamiento); el modelo de "traces" de conversación es secundario |
| Construir un dashboard propio | Reinventar tracing distribuido (spans, ingestión, UI de comparación) no aporta nada a la tesis del proyecto (agentes de devoluciones) y consume tiempo que sí aporta valor en otras partes |

**Decisión**: LangFuse es open-source, tiene SDK oficial para LangChain/LangGraph
(un solo `CallbackHandler`, sin instrumentar cada nodo a mano) y ofrece un
tier Cloud gratuito — cero infraestructura propia que levantar/mantener
para un TFM.

---

## 2. Diseño no invasivo: `with_langfuse()` como wrapper de `config`

Los tres agentes (`triage.py`, `evaluator.py`, `resolution.py`) no importan
LangFuse ni saben que existe. Toda la instrumentación entra por **un único
punto**: el `config` que se le pasa a `graph.ainvoke()` / `graph.astream()`
en `backend/api/routers/chat.py`.

```python
config = with_langfuse(
    {"configurable": {"thread_id": request.thread_id}},
    thread_id=request.thread_id,
)
result = await graph.ainvoke(input_state, config=config)
```

`with_langfuse()` (en `backend/services/observability.py`) añade el
`CallbackHandler` a `config["callbacks"]` si LangFuse está configurado, y
devuelve el `config` sin tocar si no lo está.

**Decisión**: LangGraph ya propaga `callbacks` a cada nodo internamente
(mecanismo estándar de LangChain). Aprovecharlo evita añadir un
`@traced` o un `logger.info(...)` en cada uno de los tres agentes —
si se añade un cuarto agente al grafo en el futuro, queda trazado
automáticamente sin tocar su código.

---

## 3. Solo LangFuse Cloud — sin self-hosted

El proyecto tuvo, en algún punto, un stack self-hosted vía Docker
(`langfuse_infra/`: Postgres + ClickHouse + Redis + MinIO + langfuse-web/worker)
además del SDK apuntando a Cloud — dos formas de llegar a lo mismo,
mantenidas en paralelo. Se eliminó el self-hosted y se quedó **solo con
Cloud**, por simplicidad: un TFM no necesita gestionar 5 contenedores
Docker para una capacidad que el tier gratuito de Cloud ya cubre, y mantener
una sola vía reduce la superficie a explicar/defender sin perder nada
funcional (el SDK de código es idéntico contra cualquiera de los dos hosts).

**¿Y la privacidad?** Es tentador pensar "self-hosted = los datos no salen
de la máquina", pero ya era falso antes de quitarlo: `SUPABASE_URL` apunta a
Supabase Cloud y cada llamada al LLM manda ese mismo contenido a OpenAI. Lo
que LangFuse traza es una copia de un prompt/respuesta que ya salió hacia
OpenAI, no una categoría nueva de dato expuesto — así que usar Cloud no
cambia la superficie de exposición real del proyecto. Si en el futuro esto
fuera producción con datos reales, la palanca correcta sería el parámetro
`mask` del constructor de `Langfuse()` (redacta campos sensibles antes de
convertirlos en span), no dónde vive el servidor.

---

## 4. Por qué `LANGFUSE_BASE_URL` y no `LANGFUSE_HOST`

Detalle que sale fácil en preguntas de código: el SDK de Python `langfuse`
(4.x) tiene **dos** variables de entorno para el host, y una está deprecada:

```python
# langfuse/_client/environment_variables.py
LANGFUSE_BASE_URL = "LANGFUSE_BASE_URL"   # nombre actual
LANGFUSE_HOST = "LANGFUSE_HOST"           # "Deprecated. Use LANGFUSE_BASE_URL instead."
```

El propio cliente del SDK, internamente, prioriza `LANGFUSE_BASE_URL` sobre
`LANGFUSE_HOST` si ambas están presentes. `_host()` (arriba) replica ese
mismo orden de prioridad a mano, porque `get_langfuse()` /
`get_langfuse_callback()` pasan `host=` **explícitamente** al construir el
cliente — y un parámetro explícito no cae automáticamente al fallback de
variables de entorno del SDK. Sin esta función, un `.env` con solo
`LANGFUSE_HOST` (nombre usado en documentación/tutoriales antiguos) sería
ignorado en silencio y el tracing iría siempre al default sin avisar.

---

## 5. Agrupación por sesión: `thread_id` → `langfuse_session_id`

Cada conversación cliente-agente tiene un `thread_id` (usado también como
clave del checkpointer de LangGraph en Postgres). `with_langfuse()` reutiliza
ese mismo identificador como `langfuse_session_id`:

```python
if thread_id:
    metadata["langfuse_session_id"] = thread_id
```

**Decisión**: sin esto, cada turno de la conversación (cada llamada a
`/api/chat` o `/api/chat/stream`) aparecería como una traza aislada en
LangFuse, sin relación visible con los turnos anteriores del mismo cliente.
Reutilizar el `thread_id` — que ya existe para el checkpointer — evita
generar un segundo identificador y mantiene "una conversación = una sesión"
tanto en Postgres como en LangFuse.

---

## 6. Cliente crudo además del `CallbackHandler`: por qué

`backend/services/observability.py` expone dos helpers, no uno:

```python
get_langfuse_callback()   # → CallbackHandler, para instrumentar el grafo
get_langfuse()            # → cliente Langfuse crudo, para scores manuales
```

El `CallbackHandler` traza automáticamente lo que LangGraph ya sabe hacer
(latencia, tokens, prompts). Pero **no** puede escribir un score de negocio
como "¿esta predicción coincidió con la etiqueta esperada del golden
dataset?" — eso requiere llamar a `create_score()` sobre el cliente
directamente, algo que un callback pasivo no ofrece.

```python
# evaluation/golden/scripts/evaluate_evaluator_agent.py
obs = lf.start_observation(name=f"eval-case-{cat}", as_type="evaluator", ...)
lf.create_score(trace_id=run_trace_id, observation_id=obs.id,
                 name="label_match", value=1.0 if match else 0.0, data_type="NUMERIC")
```

**Decisión**: exponer el cliente crudo cuesta una función más en
`observability.py`, pero es lo que permite que la evaluación del golden
dataset (§8, en [`defenderDatos.md`](defenderDatos.md)) no se quede en un
JSON local sino que sea visible y comparable en la UI de LangFuse.

---

## 7. `flush()` explícito al cerrar la app

```python
# backend/api/main.py (lifespan de FastAPI)
yield
langfuse_flush()  # al shutdown
```

**Por qué es necesario**: el SDK 4.x de LangFuse manda las trazas por
OpenTelemetry en **lotes** (batching), no una petición HTTP por evento —
así se reduce la sobrecarga de red en producción. La contrapartida es que,
si el proceso termina (reload de `uvicorn`, `Ctrl+C`, redeploy) antes de que
el lote se vacíe por temporizador, las últimas trazas se pierden en
silencio. Llamar a `flush()` en el `lifespan` de FastAPI garantiza que el
buffer se vacía antes de que el proceso muera, sin tener que esperar al
intervalo de flush automático del SDK.

---

## 8. Evaluación del agente: fuera de este documento

El golden dataset (480 casos), los scripts `evaluate_evaluator_agent.py` /
`migrate_eval_cases_to_langfuse.py` / `run_langfuse_experiment.py`, y cómo
se correlaciona la accuracy de un run con la versión del prompt que estaba
activa ("Link to Traces") viven documentados en
[`defenderDatos.md`](defenderDatos.md) §4 y §4bis — no se duplican aquí.
Este documento cubre solo el diseño de la instrumentación de tracing en sí
(cómo se conecta LangFuse al grafo, qué es opcional/fail-open, cómo se
agrupan sesiones/usuarios); `defenderDatos.md` cubre qué se mide con esa
instrumentación y cómo se compara entre ejecuciones.

---

## 9. Diseño "fail-open": opcional en todo momento

Regla seguida en cada punto de integración: si `LANGFUSE_PUBLIC_KEY` /
`LANGFUSE_SECRET_KEY` no están en `.env`, la app funciona exactamente igual,
sin trazas — nunca un `raise`.

```python
def get_langfuse_callback() -> Optional[Any]:
    if not _is_configured():
        return None
    ...
```

Y en cada punto de uso, un callback/cliente `None` se trata como "no-op",
no como error:

```python
callback = get_langfuse_callback()
if callback is None:
    return config          # devuelve el config sin tocar
```

**Decisión**: LangFuse es una herramienta de observabilidad, no una
dependencia funcional del sistema de devoluciones. Que falte no debe poder
tirar abajo el flujo de un cliente pidiendo una devolución — de ahí que
todos los `try/except` alrededor de la inicialización sean deliberadamente
anchos (`except Exception`) y logueen un `warning`, no un `error`.

Precisamente por ser opcional y fail-open, LangFuse no es el sitio adecuado
para un control de gasto que debe estar siempre disponible — ver
[`defenderDashboardCostes.md`](defenderDashboardCostes.md) para por qué existe
además un dashboard propio de coste por pedido/cliente, y cuándo usar cada uno
de los dos.

### Las API keys deciden si se traza; el host decide a dónde

Dos comprobaciones independientes: `_is_configured()` (§9) mira solo las
keys; `_host()` (§4) solo decide a qué URL apuntar, y ni se evalúa si las
keys faltan:

```python
def get_langfuse_callback() -> Optional[Any]:
    if not _is_configured():      # ← solo mira las API keys
        return None                #   si faltan, ni se llega a leer _host()
    ...
        host=_host(),              # ← solo decide A DÓNDE mandar, no SI mandar
```

Sin `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` no hay tracing, sin importar qué diga
`LANGFUSE_BASE_URL` — ese valor solo importa una vez que las keys ya están.

---

## 10. Preguntas típicas de la defensa

**¿Por qué no instrumentar cada nodo del grafo individualmente?**
Porque LangGraph ya propaga `callbacks` desde el `config` de nivel superior
a cada nodo. Instrumentar nodo a nodo sería reinventar algo que el framework
ya resuelve, y forzaría a tocar los tres agentes cada vez que se añade o
quita un punto de traza.

**¿Qué pasa si LangFuse Cloud tiene una caída mientras corre la demo?**
Nada visible para el usuario: `get_langfuse_callback()` atrapa cualquier
excepción de inicialización y devuelve `None`; `with_langfuse()` entonces
devuelve el `config` original sin el callback. El grafo de agentes no
depende de LangFuse para ejecutar.

**¿Por qué no self-hosted, si evitaría sumar un SaaS más?**
Porque ya no cambia gran cosa: `SUPABASE_URL` apunta a Supabase Cloud y cada
llamada al LLM manda el mismo contenido a OpenAI, así que "los datos no
salen de la máquina" ya no era cierto con o sin self-hosted. Lo poco que
aportaba (una empresa menos viendo la sesión correlacionada) no compensaba
mantener 5 contenedores Docker para un TFM — ver §3.

---

## 11. Mapa de qué hay implementado, por área

Cuatro áreas típicas de un panel de observabilidad, y qué hay de cada una
en este proyecto — con nivel de madurez explícito, no solo lo que existe.

### Costes y consumo — nivel medio

- `with_langfuse()` (`observability.py:142-172`) añade `langfuse_session_id`/
  `langfuse_user_id` a cada invocación del grafo → LangFuse agrega coste por
  sesión y por cliente sin contador propio en la app.
- `search_return_policy()` (`supabase_service.py:149-195`) usa
  `langfuse.openai` (drop-in del SDK de OpenAI) para trazar el embedding de
  la query RAG como una `GENERATION` con tokens y coste reales — antes de
  esto, ese embedding era invisible para LangFuse y el RAG aparecía siempre
  a $0 en el dashboard de coste.
- **Decisión explícita**: no hay contador de coste propio en la app.
  `GET /api/admin/observability` (`admin.py:112-122`) solo devuelve enlaces
  al dashboard de LangFuse; el comentario en el propio código dice por qué
  no se reimplementa esa agregación.

### Rendimiento técnico (latencias y errores) — la más débil de las cuatro

- La latencia se ve en LangFuse porque el `CallbackHandler` la captura
  **pasivamente** (viene del SDK, no es instrumentación propia).
- `score_error(thread_id, "timeout"|"exception")` (`observability.py`,
  llamado desde `chat.py`) marca en LangFuse cuándo un *turno completo*
  terminó en error — filtrable/contable por sesión en la UI de Scores.
- **Gap ya cerrado**: antes, el error se registraba solo a nivel de
  *turno*, no de *tool* — si `create_return_record`/
  `generate_shipping_label`/etc. fallaba, la excepción subía y en el mejor
  caso marcaba el turno como "exception", sin registro de *qué tool*
  falló. Ahora `call_tool()` (`mcp_client.py`, el único punto de paso de
  las 10 tools MCP) envuelve la invocación real en try/except: registra
  éxito/fallo y latencia en la tabla propia `mcp_tool_calls` (siempre
  disponible, mismo criterio que el dashboard de coste, ver
  `tool_call_service.py`) y, si hay `thread_id` y LangFuse está
  configurado, también un score `tool_call` como canal extra
  (`observability.score_tool_call`). "¿Qué tools fallan más?" se responde
  agregando por tool (`tool_call_service.get_tool_call_error_rates()`,
  expuesto en `GET /api/admin/observability` y en el panel de admin,
  expander "🔧 Salud de tools MCP").
- No hay retries instrumentados en las llamadas a LLM/MCP.

### Calidad y evaluación — la más fuerte de las cuatro

- **En producción**: `score_rag_similarity()` (`observability.py:175-262`)
  anota en LangFuse la mejor similitud coseno de cada búsqueda RAG,
  incluyendo `value=0.0` explícito cuando no hay resultados — decisión
  deliberada de no callar los "miss".
- **Evaluación masiva contra el golden dataset**: ver
  [`defenderDatos.md`](defenderDatos.md) §4 y §4bis — no se duplica aquí.

### Trazas y prompt management

- Trazas: diseño no invasivo ya cubierto en la sección 2 — ni los tres
  agentes ni `graph.py` importan LangFuse, todo entra por `config`. Dos
  procesos distintos generan trazas de forma independiente: el
  `CallbackHandler` (proceso de la API) y `langfuse.openai` para el
  embedding (proceso del MCP server, `mcp_supabase.py`) — cada uno necesita
  su propio cliente LangFuse registrado porque son procesos separados.
- **Prompt management: sincronizado, no leído en runtime — decisión
  deliberada.** Los 4 prompts de sistema (`TRIAGE_SYSTEM_PROMPT` en
  `triage.py`, `POLICY_SYSTEM_PROMPT` en `evaluator.py`,
  `RESOLUTION_SYSTEM_PROMPT`/`REJECTION_SYSTEM_PROMPT` en `resolution.py`)
  siguen siendo constantes de Python — **la fuente de verdad sigue siendo
  el código**, revisable en PR con historia de git real. `scripts/
  sync_prompts_to_langfuse.py` empuja su contenido actual a Langfuse
  (`create_prompt(..., labels=["production"])`), de forma idempotente (solo
  crea una versión nueva si el texto cambió) — nunca al revés: los agentes
  NUNCA llaman a `langfuse.get_prompt()`, así que un cambio hecho a mano en
  la UI de Langfuse no tendría ningún efecto y se perdería en el siguiente
  `sync`. Esto da versionado e historial navegable en la UI de Langfuse sin
  añadir una dependencia en tiempo de ejecución a un servicio opcional
  (mismo criterio de disponibilidad que el resto del proyecto).
  **"Link to Traces"** (correlacionar accuracy de una evaluación con la
  versión de prompt que estaba activa) sí se ganó, pero no en runtime de
  producción — son los scripts de evaluación los que leen la versión
  `production` y enlazan sus propios runs, ver
  [`defenderDatos.md`](defenderDatos.md) §4bis para el mecanismo y su
  fallback cuando código y Langfuse no coinciden. A/B testing o rollback
  instantáneo de prompts sin desplegar código sigue sin existir: seguirían
  siendo, respectivamente, un experimento manual con dos ramas y un revert
  de commit.
