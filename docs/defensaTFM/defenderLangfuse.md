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
| LangSmith | Mismo propósito, pero acoplado al ecosistema LangChain de forma más cerrada y sin opción self-hosted gratuita viable para un proyecto académico |
| Weights & Biases (Prompts) | Pensado para tracking de experimentos ML clásicos (hiperparámetros, curvas de entrenamiento); el modelo de "traces" de conversación es secundario |
| Construir un dashboard propio | Reinventar tracing distribuido (spans, ingestión, UI de comparación) no aporta nada a la tesis del proyecto (agentes de devoluciones) y consume tiempo que sí aporta valor en otras partes |

**Decisión**: LangFuse es open-source, tiene SDK oficial para LangChain/LangGraph
(un solo `CallbackHandler`, sin instrumentar cada nodo a mano) y soporta tanto
Cloud como self-hosted — relevante para un TFM donde a veces interesa no
depender de un servicio de terceros con datos de clientes ficticios.

---

## 2. Diseño no invasivo: `with_langfuse()` como wrapper de `config`

Los tres agentes (`triage.py`, `policy.py`, `resolution.py`) no importan
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

## 3. LangFuse Cloud vs self-hosted: una decisión que se tomó dos veces

Este proyecto terminó con **dos implementaciones paralelas** de LangFuse
construidas de forma independiente en ramas distintas del equipo, cada una
optimizada para un caso de uso real:

| | Cloud SDK (`backend/services/observability.py`) | Self-hosted Docker (`langfuse_infra/`) |
|---|---|---|
| Backend | `cloud.langfuse.com`, cero infraestructura propia | Stack propio: Postgres + ClickHouse + Redis + MinIO + langfuse-web/worker |
| Coste operativo | Ninguno (tier gratuito) | 5 contenedores Docker en local |
| Privacidad de datos | Datos (incl. pedidos/clientes ficticios) salen a un SaaS de terceros | Todo el tracing se queda en la máquina del desarrollador |
| Capacidades expuestas | `CallbackHandler` **+** cliente `Langfuse` crudo (scores manuales) | Solo `CallbackHandler` |

**Por qué no era trivial elegir una y descartar la otra**: la versión
self-hosted resuelve un problema real de privacidad (este es un sistema de
devoluciones con datos de clientes) y la versión Cloud SDK resuelve un
problema real de evaluación (los scripts de QA en `tests/qa/scripts/` necesitan
el cliente `Langfuse` crudo para escribir métricas, no solo el callback).

**Decisión final**: mantener **una sola** implementación de código
(`backend/services/observability.py`, la más completa) pero dejar que
apunte a **cualquiera de los dos backends** vía variable de entorno —
así no hay que elegir entre privacidad y capacidad de evaluación, es una
decisión de infraestructura (`LANGFUSE_BASE_URL`) y no de código.

```python
def _host() -> str:
    """LANGFUSE_BASE_URL (nombre actual del SDK) con fallback a LANGFUSE_HOST
    (nombre usado en la documentación de langfuse_infra/), y por último
    LangFuse Cloud."""
    return (
        os.getenv("LANGFUSE_BASE_URL")
        or os.getenv("LANGFUSE_HOST")
        or "https://cloud.langfuse.com"
    )
```

`langfuse_infra/` (el stack Docker) se mantuvo como carpeta de infraestructura
independiente — no como código Python — precisamente para no forzar esa
elección: quien quiera self-hosted levanta ese stack y apunta
`LANGFUSE_BASE_URL=http://localhost:3000`; quien no, usa el default de
LangFuse Cloud sin tocar nada.

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
`LANGFUSE_HOST` (como documenta `langfuse_infra/README.md` para el stack
self-hosted) sería ignorado en silencio y el tracing iría siempre a
LangFuse Cloud sin avisar.

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
# tests/qa/scripts/evaluate_rag.py
obs = lf.start_observation(name=f"eval-case-{cat}", as_type="evaluator", ...)
lf.create_score(trace_id=run_trace_id, observation_id=obs.id,
                 name="label_match", value=1.0 if match else 0.0, data_type="NUMERIC")
```

**Decisión**: exponer el cliente crudo cuesta una función más en
`observability.py`, pero es lo que permite que la evaluación del RAG
(§7) no se quede en un JSON local sino que sea visible y comparable en la
UI de LangFuse.

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

## 8. De evaluación local a LangFuse Datasets + Experiments

El proyecto ya tenía `evaluate_rag.py`: lee los 480 casos de
`data/qa/eval_cases.csv`, corre el agente evaluador y escribe un informe
JSON/Markdown local con precisión, recall y F1. Funciona, pero comparar dos
ejecuciones (por ejemplo, antes/después de cambiar un prompt) significa abrir
dos ficheros Markdown y comparar tablas a mano.

Se añadieron dos scripts para subir ese mismo golden dataset a LangFuse:

```
migrate_eval_cases_to_langfuse.py   # sube los 480 casos como un Dataset de Langfuse (una vez)
run_langfuse_experiment.py          # corre el agente sobre ese Dataset como un Experiment
```

`run_langfuse_experiment.py` reutiliza la lógica de `evaluate_rag.py`
(`_build_state`, `_build_mock_policy`, `_result_to_label`) — no duplica el
mapeo CSV → estado del agente — pero en vez de escribir un fichero, cada
caso queda registrado como parte de un `run_experiment()` de LangFuse, con
un evaluador por caso (`label_match_evaluator`) y un evaluador de accuracy
agregado por ejecución (`accuracy_run_evaluator`).

**Decisión**: mantener `evaluate_rag.py` (rápido, sin credenciales de
LangFuse, ideal para CI/`--dry-run`) **y** añadir el camino LangFuse
(visual, comparable entre ejecuciones, mejor para la demo de defensa) en
vez de sustituir uno por el otro — son complementarios, no redundantes.

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

### Las API keys y el host se comprueban por separado — no hay fallback automático

Malentendido habitual: **`LANGFUSE_BASE_URL`/`LANGFUSE_HOST` no es un
interruptor "usa Docker si no hay Cloud"**. `_is_configured()` (§9) y
`_host()` (§4) son dos comprobaciones independientes, y la primera se evalúa
**antes** de mirar la segunda:

```python
def get_langfuse_callback() -> Optional[Any]:
    if not _is_configured():      # ← solo mira las API keys
        return None                #   si faltan, ni se llega a leer _host()
    ...
        host=_host(),              # ← solo decide A DÓNDE mandar, no SI mandar
```

Consecuencias concretas, para no confundirse configurando el `.env`:

| `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` | `LANGFUSE_BASE_URL` | Resultado |
|---|---|---|
| ❌ Ausentes | (cualquiera, o ausente) | Sin tracing. Da igual el host — nunca se llega a mirarlo |
| ✅ Presentes | Ausente | Traza a **LangFuse Cloud** (default de `_host()`) |
| ✅ Presentes | `http://localhost:3000` | Traza al **stack Docker** de `langfuse_infra/` |

Es decir: las keys deciden **si** se traza; el host decide **a dónde**. Poner
solo `LANGFUSE_BASE_URL=http://localhost:3000` sin keys no activa nada — y
poner las keys sin `LANGFUSE_BASE_URL` sí traza, pero a Cloud, no al Docker
local que se acaba de levantar.

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

**¿Por qué no usar solo el self-hosted y evitar mandar datos a un SaaS?**
Es la opción soportada (`langfuse_infra/`, apuntando `LANGFUSE_BASE_URL` a
`http://localhost:3000`), pero exige tener Docker corriendo con 5
contenedores solo para trazar. Para el flujo de desarrollo del día a día,
LangFuse Cloud sin infraestructura propia es más rápido de levantar; el
self-hosted queda disponible para quien lo necesite por privacidad de datos.

**Si levanto el Docker de `langfuse_infra/` pero no toco el `.env` de la
raíz, ¿empieza a trazar ahí automáticamente?**
No. Levantar el contenedor no basta: hay que copiar sus
`LANGFUSE_INIT_PROJECT_PUBLIC_KEY`/`SECRET_KEY` al `.env` de la raíz **y**
añadir `LANGFUSE_BASE_URL=http://localhost:3000` ahí también. Sin las keys
en el `.env` de la raíz, la app sigue sin trazar nada, tenga Docker
levantado o no — las keys son las del backend Python, no las del contenedor.
