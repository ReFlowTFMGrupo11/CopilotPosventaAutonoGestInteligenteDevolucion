# Defensa de la Arquitectura Multi-Agente

## 1. ¿Por qué LangGraph y no LangChain secuencial?

| Criterio | LangChain (cadena) | LangGraph (grafo) |
|----------|-------------------|-------------------|
| Flujo condicional | Hack con `if/else` entre eslabones | Nativo con `add_conditional_edges` |
| Volver atrás (falta info) | Imposible sin reescribir la cadena | Arista de retorno al nodo anterior |
| HITL (Human-in-the-Loop) | No soportado nativamente | `interrupt()` + `Command(resume=...)` |
| Persistencia entre turnos | Manual | Checkpointer integrado |
| Visualización del flujo | No disponible | `graph.get_graph().draw_mermaid_png()` |

**Decisión**: LangGraph modela exactamente nuestro flujo (condicionales, loops, pausa para admin).

---

## 2. ¿Por qué 3 agentes y no 1 solo?

### Separación de responsabilidades (Single Responsibility Principle)

| Agente | Rol | Temperature | Justificación |
|--------|-----|-------------|---------------|
| **Triaje** | Empatía + extracción de datos | 0 (`triage.py::_build_llm`) | Prioriza la fiabilidad de la extracción estructurada (`order_number`, `reason_category`, `condition`...) sobre la variedad de la redacción — un `order_number` mal extraído por "creatividad" del modelo rompe el turno; una frase de `response_to_customer` algo menos variada no |
| **Evaluador** | Auditoría de políticas | 0.0 (`evaluator.py::_build_llm`) | Debe ser determinista y objetivo |
| **Resolución** | Ejecutar acciones + comunicar | 0.4 (`resolution.py::_build_llm`) | Balance entre claridad y calidez |

> Corrección: una versión anterior de esta tabla indicaba `0.3` para Triaje
> ("necesita creatividad para conversar"). Comprobado el código
> (`triage.py::_build_llm` → `build_chat_llm("TRIAGE_MODEL", temperature=0)`):
> es `0`, no `0.3` — no hay override en `.env.example` para
> `TRIAGE_MODEL_TEMPERATURE`, así que `0` es el valor real en desarrollo y
> producción salvo que se configure explícitamente lo contrario.

### Ventajas de la separación

1. **Contexto acotado**: Cada agente recibe solo el prompt y datos que necesita. Un solo agente con todo saturaría el contexto.
2. **Seguridad**: El agente de Triaje no puede ejecutar acciones (crear devoluciones, generar etiquetas). Solo el Resolución tiene acceso a esas herramientas.
3. **Testabilidad**: Se puede testear cada nodo de forma aislada con mocks.
4. **Auditoría**: El Evaluador siempre devuelve JSON estructurado con `is_eligible` + `eligibility_reason`, trazable y auditable.

### Contraste con las 4 razones "por qué multi-agente" del framework docente (EBIS)

| Razón (framework) | ¿Aplica en ReFlow? |
|---|---|
| **1. Especialización** ("cada agente domina una tarea específica") | ✅ Sí, en pleno — es exactamente la tabla de arriba: Triaje/Evaluador/Resolución, cada uno con su propio prompt, modelo configurable (`{triage,evaluator,resolver}_model`) y `temperature` propia (0, 0.0, 0.4 respectivamente) |
| **2. Escalabilidad** ("tareas complejas → múltiples subtareas"; "procesamiento **paralelo**, necesitan diferente contexto o tools") | ⚠️ Solo la mitad — la descomposición en subtareas con contexto/tools distintos sí aplica (punto 1, "Contexto acotado"). El **procesamiento paralelo NO aplica**: los 3 agentes son estrictamente **secuenciales** (`graph.py`: `START → triage → fetch_order_data → evaluator → resolver/reject`), cada uno depende del `state` que dejó el anterior. No hay ningún tramo del grafo donde dos agentes corran a la vez |
| **3. Mantenibilidad** ("modificar un agente sin afectar otros"; "reutilización de componentes") | ✅ Sí — cada agente vive en su propio módulo (`nodes/triage.py`, `nodes/evaluator.py`, `nodes/resolution.py`), con el `ReturnState` como único contrato entre ellos. El punto 3 ("Testabilidad") ya lo evidencia: se testea cada nodo con mocks sin tocar los demás |
| **4. Resiliencia** ("si un agente falla, otros continúan"; "redundancia y backup") | ❌ **No aplica, y es importante no fingir que sí**: al ser un pipeline secuencial (no un enjambre de agentes independientes), si `evaluator_agent` lanza una excepción, `resolution_agent` sencillamente no se ejecuta — no hay ningún agente redundante que lo sustituya. Lo que sí existe es **degradación elegante dentro de cada nodo** (no entre nodos): `evaluator_agent` cae a "no elegible" si el structured output devuelve `None` (ver §9); el checkpointer cae a `InMemorySaver` si Postgres no responde (ver §6). Es tolerancia a fallos a nivel de infraestructura/nodo individual, no la resiliencia por redundancia entre agentes que describe el framework |

**Por qué esta arquitectura no busca resiliencia por redundancia**: el pipeline es intencionalmente una cadena de dependencia estricta (Triaje decide el pedido → Evaluador decide elegibilidad → Resolución actúa sobre esa decisión) — cada etapa necesita el resultado exacto de la anterior para tener sentido, así que "que el Evaluador falle y el Resolución continúe sin él" no es una opción de diseño válida en este dominio (actuaría sobre una elegibilidad que no existe). La resiliencia que sí tiene sentido aquí es la que hay: fallar de forma controlada y visible (excepción/log/LangFuse), no silenciosamente ni con un agente sustituto improvisado.

---

## 3. ¿Por qué `TypedDict` y no Pydantic para el estado?

- Es lo recomendado por la documentación oficial de LangGraph.
- Zero overhead en runtime (Pydantic valida en cada actualización de estado).
- `Annotated[list[AnyMessage], add_messages]` funciona nativamente con TypedDict.
- `total=False` permite actualizaciones parciales desde cada nodo.

---

## 4. Arquitectura de comunicación: Agentes → MCP → Servicios

```
Agentes → mcp_client.py → HTTP → MCP Servers → services/ → Supabase
                                                    ↑
                                              FastAPI (dashboard)
```

### Tres capas bien definidas

| Capa | Responsabilidad | Ejemplo |
|------|----------------|--------|
| `services/` | Lógica de negocio y acceso a datos | `get_order_details()`, `generate_shipping_label()` |
| `mcp/` | Expone services como tools MCP via HTTP | `@mcp.tool()` → wrapper fino |
| `agents/mcp_client.py` | Cliente MCP que llama a los servers | `call_tool("get_order_details", {...})` |

### ¿Por qué los agentes llaman via MCP y no importan services directamente?

1. **Coherencia con producción**: En AWS los MCP servers estarán en contenedores separados. El mismo código funciona en local y en producción.
2. **Validación del protocolo MCP**: Demuestra que el estándar funciona end-to-end, no solo como decoración.
3. **Desacoplamiento real**: Los agentes no conocen la implementación interna (Supabase, pgvector, reportlab). Solo conocen el contrato MCP.
4. **Interoperabilidad**: Cualquier cliente MCP (Claude Desktop, Copilot, otro equipo) puede usar los mismos servers.

**Cumplimiento verificado** (`grep -n "from backend.services" backend/agents/nodes/*.py backend/agents/graph.py`):
ningún nodo importa `backend.services` para acceder a datos de negocio. Antes sí lo
hacían dos (`evaluator.py` y `resolution.py`, arrastrado del `supabase_service.py`
original) — corregido: `orders_service.get_order_details()` ahora precalcula y
devuelve `order["days_since_delivery"]` (así el Evaluador lo lee del dato que ya le
llega vía MCP, sin necesitar `calculate_days_since_delivery` importado aparte), y se
añadieron las tools `get_pending_return_request_id`/`get_latest_return_request` para
que `resolution.py` recupere el registro duplicado tras un `interrupt()` vía MCP en
vez de leer `returns_service` directamente. Quedan solo dos excepciones deliberadas,
ninguna de acceso a datos de negocio:
- `resolution.py` importa `DUPLICATE_RETURN_MARKER` (constante string) de
  `returns_service` — necesaria para interpretar un mensaje de error que ya llegó
  *a través* de MCP (`call_tool()` aplana toda excepción a `RuntimeError` con un
  string en el límite del protocolo; no hay forma de propagar un tipo de excepción
  custom a través de ese roundtrip, así que hace falta un marcador de texto
  compartido entre quien lo lanza y quien lo interpreta).
- `graph.py` importa `observability` — logging/trazas transversales (Langfuse), no
  un dominio de negocio; mismo criterio que el resto del código (p. ej.
  `mcp_client.py` también importa `observability.score_rag_similarity` directamente).

### ¿Y si los MCP servers no están levantados?

- En **tests**: se mockea `backend.agents.mcp_client` (nunca se hace HTTP real).
- En **desarrollo**: se levantan los servers localmente (`python -m backend.mcp.mcp_supabase`).
- En **producción**: son contenedores Docker con health checks.

### ¿Por qué NO dejamos que el LLM elija qué tool llamar?

El flujo es **determinista**: cada nodo sabe exactamente qué tool necesita.

```python
# Opción descartada: LLM elige (no determinista)
llm_with_tools = llm.bind_tools(all_tools)
response = await llm_with_tools.ainvoke(messages)  # ← puede elegir mal

# Opción elegida: llamada directa por nombre (determinista)
result = await get_order_details(order_id)  # ← siempre llama a lo correcto
```

Si quisiéramos forzar la tool podríamos usar `tool_choice="get_order_details"`, pero eso equivale a una llamada directa con overhead HTTP + LLM innecesario.

### FastAPI y el dashboard

FastAPI importa directamente de `services/` (no pasa por MCP) porque:
- Está en el mismo proceso/contenedor que los services.
- No necesita el overhead del protocolo MCP para consultas simples (listar devoluciones, KPIs).
- El protocolo MCP está diseñado para LLMs, no para UIs.

---

## 5. ¿Por qué HITL con `interrupt()` y no con `interrupt_before`?

| Enfoque | Uso |
|---------|-----|
| `interrupt_before=["nodo"]` | Debugging estático (breakpoints) |
| `interrupt()` dentro del nodo | HITL dinámico basado en lógica de negocio |

Usamos `interrupt()` porque la pausa es **condicional** (solo si `refund_amount > 100€`), no siempre.

```python
if refund_amount > HITL_REFUND_THRESHOLD:
    admin_response = interrupt({...})  # Pausa y espera respuesta del admin
```

El admin responde con `Command(resume={"approved": True})` y el grafo continúa exactamente donde paró.

---

## 6. ¿Cómo se gestiona la memoria del chat?

### Dos niveles

| Nivel | Mecanismo | Para qué |
|-------|-----------|----------|
| Corto plazo | `add_messages` reducer + Checkpointer | Estado del grafo entre turnos, HITL, reanudación |
| Largo plazo | `return_requests` (vía `get_customer_return_history`) | Historial de devoluciones del cliente entre sesiones — señal de cliente frecuente en `policy_rules.py` |

El checkpointer guarda todo el estado (incluido `messages`) asociado a un `thread_id`. Cuando el usuario vuelve (mismo `thread_id`), el grafo se reanuda con el estado completo; el LLM de triaje, eso sí, solo recibe los últimos 20 mensajes (ver abajo).

> **Nota histórica**: una versión anterior de esta tabla listaba aquí
> `chat_sessions`/`chat_messages` como el mecanismo de memoria de largo plazo
> "para UI, auditoría, analytics". Auditado el código
> (`grep -rn "chat_sessions\|chat_messages" backend/ frontend/`): **ningún**
> nodo, router ni página del frontend leía o escribía esas tablas — solo las
> poblaba `data/generate_dataset.py` (generador del dataset sintético de
> QA/seed), nunca el chat en producción. Eliminadas en
> `015_drop_chat_sessions.sql` por no tener consumidor real; ver el análisis
> completo en §15.

### Persistencia del estado conversacional (Checkpointer)

El grafo LangGraph utiliza un *checkpointer* para persistir el estado completo de cada conversación entre turnos. Cada sesión de usuario se identifica mediante un `thread_id` único. LangGraph guarda un checkpoint en cada paso del grafo, incluidas las pausas HITL (`interrupt()`), y el checkpointer serializa el `ReturnState` —historial de mensajes, datos parciales extraídos y decisiones intermedias— asociado a ese `thread_id`.

El backend elige el checkpointer al arrancar (`build_return_graph` en `backend/agents/graph.py`):

- **Con `SUPABASE_DB_URL` configurada** se usa `AsyncPostgresSaver` sobre el pooler de Postgres de Supabase (pool de 1 a 3 conexiones, `autocommit=True`). Las tablas (`checkpoints`, `checkpoint_writes`, `checkpoint_migrations`) las crea `setup()` en el esquema por defecto; el código no configura un schema propio.
- **Si la conexión falla o falta la URL**, el comportamiento depende de `ENVIRONMENT`. En `development` se degrada a `InMemorySaver` (estado en RAM, se pierde al reiniciar el proceso) y se registra un aviso. En `production` el arranque se detiene, porque el estado multi-turno y las pausas HITL no pueden perderse en silencio.
- El estado del checkpointer se expone en `/health` y en `/api/admin/observability`, para que una degradación sea visible fuera de los logs.

Dos límites del mecanismo, que conviene conocer:

- **El almacenamiento no se recorta, el prompt sí.** `trim_history` manda solo los últimos `MAX_HISTORY_MESSAGES` (20 por defecto) mensajes al LLM de triaje. Los datos clave sobreviven al recorte porque viajan en campos estructurados del estado (`order_id`, `customer_id`, `reason`, `items_to_return`), no solo en el texto.
- **Conversaciones acotadas:** `MAX_CONVERSATION_TURNS` (40 turnos de usuario por `thread_id`, 0 desactiva el límite) impide conversaciones sin fin que harían crecer coste y contexto. No hay resumen incremental del historial.

Este mecanismo permite un patrón conversacional multi-turno sin mantener conexiones abiertas: cada mensaje del usuario dispara una nueva invocación del grafo (`graph.invoke()`), el checkpointer restaura el estado previo asociado al `thread_id`, y la ejecución continúa desde donde se detuvo. Esto es fundamental para el agente de triaje, que puede requerir varios intercambios con el cliente antes de reunir toda la información necesaria (`order_id`, motivo, artículos) para avanzar al evaluador de políticas.

---

## 7. ¿Por qué mocks en los tests y no llamadas reales?

| | Tests con mocks | Tests con servicios reales |
|---|---|---|
| Coste | $0 | $$ (OpenAI API) |
| Velocidad | ms | segundos |
| Determinismo | 100% reproducible | No determinista (LLM varía) |
| CI/CD | Sin secrets ni infra | Requiere Supabase + OpenAI |
| Cobertura de edge cases | Total (puedes simular errores) | Difícil provocar fallos |

### Estrategia de testing

```
tests/unit/          → Lógica pura, routing, cálculos (sin mocks de LLM)
tests/integration/   → Nodos individuales + grafo completo (LLM mockeado)
```

---

## 8. Modelo elegido: `gpt-5-nano`

| Criterio | Justificación |
|----------|---------------|
| Coste | Más económico que gpt-4o para tareas acotadas |
| Latencia | Respuesta rápida para UX conversacional |
| Capacidad | Suficiente para triaje, evaluación de políticas y redacción de mensajes |
| Contexto | Las conversaciones de devolución son cortas (5-15 turnos) |

---

## 9. Evaluador híbrido: guardrails deterministas + LLM

### Problema

Dejar que el LLM decida solo si una devolución es elegible introduce errores en:
- Aritmética (calcular reembolsos con descuentos).
- Comparación de fechas (¿está en plazo o no?).
- Aplicación estricta de reglas (categorías excluidas por higiene).

### Solución: patrón Chain of Rules (`policy_rules.py`)

Se aplican **reglas de negocio en código puro** antes de invocar al LLM. El LLM
solo aporta la explicación en lenguaje natural y valora los casos grises.

```
┌──────────────────────────────────────────────┐
│ CAPA 1: Código (policy_rules.py)             │
│ Funciones puras, 100% deterministas          │
│ • rule_deadline     • rule_hygiene           │
│ • rule_condition    • rule_high_amount       │
│ • rule_borderline   • rule_frequent_returner │
└──────────────────────────────────────────────┘
                    ↓ veredicto
┌──────────────────────────────────────────────┐
│ CAPA 2: LLM (evaluator.py)                   │
│ Recibe el veredicto como contexto obligatorio │
│ NO puede contradecir un "invalid"            │
└──────────────────────────────────────────────┘
                    ↓ reconciliación
┌──────────────────────────────────────────────┐
│ Resultado final:                             │
│ invalid → rechazado (veto del código)        │
│ human_review → pasa por HITL                 │
│ valid → se respeta al LLM                   │
└──────────────────────────────────────────────┘
```

### Arquitectura del módulo

```
backend/agents/nodes/
  policy_rules.py   ← Código puro Python (sin dependencias externas)
                       PolicyContext (dataclass inmutable)
                       RuleResult (dataclass)
                       7 reglas individuales (funciones puras) —
                         6 activas en POLICY_RULES; rule_sensitive_reason
                         queda definida pero excluida de la cadena: su
                         SENSITIVE_REASONS (allergic_reaction,
                         counterfeit_suspicion) no tiene equivalente en
                         el reason_category de 6 valores que triage.py
                         produce hoy. Red de seguridad para si esa
                         extracción se amplía en el futuro.
                       POLICY_RULES (cadena ordenada)
                       deterministic_check() (orquestador)
                       compute_refund() (aritmética exacta)
  evaluator.py      ← Agente LLM + RAG + reconciliación
```

### Best practices aplicadas

| Principio | Cómo se aplica |
|-----------|----------------|
| **Single Responsibility** | Cada regla es una función que hace una sola comprobación |
| **Open/Closed** | Añadir regla = crear función + meterla en `POLICY_RULES` |
| **Inmutabilidad** | `PolicyContext` es `frozen=True` |
| **Testeabilidad** | Cada regla se testea sin mocks de LLM/MCP |
| **Separación de capas** | `policy_rules.py` no importa nada de LangChain/OpenAI |

### ¿Por qué no se usa Pydantic para validar la respuesta del MCP?

`call_tool()` es genérico (7 tools con respuestas distintas). Un `json.loads()`
genérico en un solo punto es más limpio que un modelo Pydantic por cada tool.

---

## 10. Flujo del grafo

```
START → triage ──────────────────┐
           ▲                     │ (order_id + items?)
           │ falta info          ▼
           └──────────── fetch_order_data
                                 │
                          (error?)│
                    ┌────────────┤
                    │            ▼
                    │       evaluator
                    │            │
                    │   ┌────────┴────────┐
                    │   │ elegible        │ no elegible
                    │   ▼                 ▼
                    │ resolver          reject → END
                    │   │
                    │   ├── ≤100€ → END (auto-aprobado)
                    │   └── >100€ → interrupt (HITL)
                    │                    │
                    │         resume EN el mismo nodo resolver → END
                    └─── (order no encontrado)
```

---

## 11. Decisiones descartadas

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Un solo agente con muchas tools | Saturación del contexto, riesgo de que ejecute acciones sin evaluar |
| Clases para los agentes | Sobreingeniería; LangGraph espera funciones, no hay estado interno mutable |
| LLM elige tools libremente (`bind_tools` sin restricción) | No determinista; el LLM puede llamar a la tool incorrecta o no llamar ninguna |
| Import directo de services (sin MCP) | No demuestra el protocolo MCP end-to-end; no refleja la arquitectura de producción |
| Pydantic para el estado del grafo | Overhead de validación en cada nodo; TypedDict es lo idiomático en LangGraph |

---

## 12. HITL: Flujo Human-in-the-Loop end-to-end

### El patrón

El sistema no es "todo automático" ni "todo manual" — es **híbrido con umbral configurable**:
- Devoluciones ≤ 100 € → auto-aprobación instantánea.
- Devoluciones > 100 € (o marcadas por el Evaluador) → requiere revisión humana.

Este patrón es estándar en producción (Amazon, Zalando): reduce costes operativos sin perder control sobre operaciones de alto valor.

### Diagrama de secuencia

```
Cliente ──msg──► Chat API ──invoke──► Grafo LangGraph
                                         │
                              ┌──────────┼──────────┐
                              │ Triaje → Evaluador → Resolución
                              │                        │
                              │              refund > 100€?
                              │                 │ SÍ
                              │    ┌────────────▼────────────┐
                              │    │ 1. Crear return_request │
                              │    │    (status=pending_approval, │
                              │    │     thread_id=UUID sesión)   │
                              │    │ 2. interrupt()               │
                              │    └────────────┬────────────┘
                              │                 │
                              │    ◄── grafo PAUSADO ──►
                              │
Admin Panel ◄── GET /pending ── consulta BD (pending_approval)
     │                              devuelve thread_id
     │
     ├── POST /admin/{thread_id}/approve
     │         │
     │         ▼
     │   graph.ainvoke(Command(resume={"approved": true}))
     │         │
     │         ▼
     │   Resolución continúa:
     │     • Genera etiqueta
     │     • Actualiza BD → status=approved
     │     • Notifica al cliente
     │
     └── POST /admin/{thread_id}/reject
               │
               ▼
         Actualiza BD → status=rejected
         Mensaje empático de rechazo al cliente
```

### Retos técnicos resueltos

| Reto | Problema | Solución |
|------|----------|----------|
| **Vinculación grafo↔BD** | El panel admin necesita saber qué grafo reanudar | Se persiste `thread_id` (UUID de sesión LangGraph) en `return_requests` |
| **Re-ejecución del nodo** | LangGraph re-ejecuta el nodo completo al hacer `resume` → el guard de duplicados bloquea el INSERT | Try/except: si el registro ya existe, se reutiliza (patrón *create-or-reuse* idempotente) |
| **Errores silenciosos MCP** | Las tools MCP devolvían errores como datos (lista) en vez de excepciones → `TypeError` difícil de diagnosticar | `call_tool` detecta respuestas de error y lanza `RuntimeError` explícito |

### Por qué `interrupt()` y no polling

| Alternativa | Inconveniente |
|-------------|---------------|
| Polling (el nodo espera en un bucle) | Consume recursos, no escala, bloquea el worker |
| Webhook externo | Complejidad extra, hay que gestionar estado fuera de LangGraph |
| **`interrupt()` nativo** ✅ | Persistencia automática via checkpointer, cero recursos consumidos mientras espera |

### Idempotencia del nodo de Resolución

El nodo debe funcionar correctamente tanto en la primera ejecución (antes del interrupt) como en la re-ejecución (tras el resume). Se garantiza con:

```python
try:
    record = await create_return_record(...)  # Primera vez
except (RuntimeError, ValueError):
    # Re-ejecución: registro ya existe, buscarlo en BD
    record_id = await buscar_registro_existente(order_id)
```

Esto sigue el principio de **diseño para fallos** (*design for failure*): el nodo no asume que es la primera vez que se ejecuta.

### Los cuatro tipos de decisión del framework docente: cuáles implementamos

| Tipo | ¿Lo tenemos? | Detalle |
|---|---|---|
| **Approve** | ✅ `POST /api/admin/{thread_id}/approve` | Ejecuta con los datos calculados por el Evaluador |
| **Reject** | ✅ `POST /api/admin/{thread_id}/reject` | No ejecuta nada; rechazo total, con `reason` opcional informativo |
| **Edit** | ✅ **Implementado** — `AdminDecisionRequest.override_refund_amount` en `/approve` | El admin corrige `refund_amount` antes de aprobar. Se propaga por `Command(resume={"override_refund_amount": ...})` → `resolution_agent` lo aplica ANTES de cualquier uso posterior del importe (BD, email, mensaje final) — ver `resolution.py`, bloque *"Decisión Edit"* justo después del `interrupt()`. Persistido en BD vía `update_return_status(..., refund_amount=...)` (nuevo parámetro, `None` = no tocar la columna) |
| **Respond** | ❌ No aplica | No hay ninguna tool tipo "preguntar al humano" donde la respuesta del humano sea directamente el resultado (ver framework: *"el humano ES la herramienta"*) — no existe ese patrón en el dominio de devoluciones |

**Antes de esta iteración, el HITL era binario** (solo Approve/Reject) — un admin que creyera que el reembolso calculado debía ser distinto no podía corregirlo, solo aprobar tal cual o rechazar la solicitud completa. Con `Edit`, el flujo real es: el panel de admin (`frontend/pages/1_Admin.py`) muestra el importe calculado en un campo editable; si el admin lo cambia, se manda como `override_refund_amount`; si no lo toca, se manda `None` y no se edita nada (mismo importe que calculó el Evaluador). Este es el nivel de HITL que usan sistemas reales de aprobación de reembolsos — no un simple sí/no.

**Corrección de un bug latente que introdujo `Edit`**: `admin_decision` (en el `Command` final) comparaba `refund_amount <= hitl_threshold` para distinguir `"auto_approved"` de `"approved"`. Como `Edit` puede corregir el importe a un valor por debajo del umbral *después* de que el HITL ya se disparó, esa comparación habría etiquetado mal una aprobación humana como automática. Corregido para basarse en `needs_admin_approval` (si realmente pasó por `interrupt()`), no en el importe final.

### ¿Por qué no usamos `HumanInTheLoopMiddleware`?

Es un patrón real (LangChain/LangGraph, API `create_agent()`), pero pensado para un paradigma distinto al nuestro: declarar la política de pausa como configuración externa (`interrupt_on={tool: {...}}`) para que el LLM, que elige dinámicamente entre *muchas* tools, no necesite que cada tool sepa que existe supervisión humana.

ReFlow no tiene ese paradigma — no hay un LLM eligiendo entre tools (§4: *"¿Por qué NO dejamos que el LLM elija qué tool llamar?"*), y solo hay **un punto de pausa real** (`resolution_agent`, umbral configurable). Con un solo punto de decisión, una capa de configuración genérica para *N* tools no aporta nada que no tengamos ya con un `if needs_admin_approval: interrupt(...)` directamente en el nodo. El middleware escala bien de 1 a muchas tools; nosotros nunca tuvimos "muchas", así que no pagamos ese coste de abstracción.

Si en el futuro ReFlow adoptara `create_agent()` con un LLM eligiendo libremente entre las 10 tools MCP actuales, ahí sí el middleware seria la herramienta correcta — y sabríamos exactamente qué tools marcar (`create_return_record`, `update_return_status`, `generate_shipping_label`, `send_customer_notification` → requieren aprobación; las 6 de solo lectura → no).

---

## 13. Los tres ámbitos de memoria multiagente, aplicados a ReFlow

| Ámbito (teoría) | Mecanismo en ReFlow | Quién lo usa |
|---|---|---|
| **Corto plazo** (historial del chat) | `checkpointer` (`AsyncPostgresSaver`/`InMemorySaver`) + `thread_id` | Solo `triage_agent` — es el único nodo que conversa con el cliente turno a turno |
| **Contexto de subtarea** (encargo acotado, no el chat) | Cada nodo construye su propio bloque de `context`/`SystemMessage` con solo los datos que necesita evaluar o resolver | `evaluator_agent` (política + pedido + historial de devoluciones) y `resolution_agent` (`resolution_context`) |
| **Compartida** (largo plazo, cruza entre agentes) | El propio `ReturnState` del grafo — poblado por `triage`/`fetch_order_data` y leído por `evaluator`/`resolution` sin que nadie repita nada | Todos los nodos, vía el estado del grafo (no vía un `store` separado) |

> **Mapeo completo a la taxonomía de memoria de corto/largo plazo (Buffer,
> Sliding Window, Episódica, Semántica...) y qué falta por cubrir: ver §15.**

### ¿Por qué no hay un `store` (`InMemoryStore`) como en el lab 1?

El patrón `store` de la clase resuelve un problema que ReFlow **no tiene**: preferencias de un mismo usuario que persisten *entre conversaciones distintas* (ej. "el cliente prefiere que le hablen en tono formal", vigente en la conversación de la semana que viene). Una devolución es una transacción de una sola sesión — todo lo que un agente necesita saber del cliente/pedido nace y muere dentro del mismo `thread_id`, y ya viaja en el `ReturnState` compartido de la fila de arriba. Añadir un `store` cruzaría información entre distintas solicitudes de devolución sin que exista ningún requisito de negocio que lo pida — sería una capa de memoria sin caso de uso.

Si en el futuro ReFlow necesitara recordar algo del cliente entre solicitudes distintas (p. ej. "cliente VIP: aplicar tolerancia extra de plazo"), ahí sí correspondería un `store` compartido entre los tres nodos, poblado una vez y leído por `evaluator_agent` sin pasar por el chat — el mismo patrón que el lab 1, aplicado a un hecho que sí sobrevive a la sesión.

### Contexto aislado: el caso que SÍ había que corregir

Antes de esta revisión, `evaluator_agent` inyectaba `trim_history(state["messages"])` (el chat crudo, recortado a los últimos `MAX_HISTORY_MESSAGES`) además de su `context` ya autosuficiente — exactamente el antipatrón que la clase pide reconocer ("si le pasas todo el historial a cada subagente... el subagente se distrae con contenido que no es de su tarea"). `resolution_agent` nunca tuvo este problema (construye su propio `resolution_context` sin tocar `state["messages"]`). Se eliminó la inyección redundante en `evaluator.py`; el criterio de "quién necesita el chat" queda ahora así:

- **Necesita el chat**: `triage_agent` (conversa con el cliente).
- **No lo necesita**: `evaluator_agent` y `resolution_agent` (reciben el encargo ya resuelto en datos estructurados).

---

## 14. Condiciones de terminación: qué límites tiene ReFlow y por qué uno no aplica

### El problema teórico

Un agente sin límites puede: entrar en loops infinitos (`tool → LLM → tool → ...`),
gastar dinero sin control, o no dar nunca una respuesta. El framework docente
(EBIS) propone 4 mecanismos comunes para cortar eso. Los repasamos uno a uno
contra el código real de ReFlow — 3 sí existen (adaptados a que ReFlow es un
**workflow determinista**, no un agente con loop de tools, ver §4 "¿Por qué
NO dejamos que el LLM elija qué tool llamar?"); uno no existe como
guardarraíl real, y uno no aplica por diseño.

| Mecanismo (teoría) | ¿Existe en ReFlow? | Dónde |
|---|---|---|
| `MAX_ITERATIONS` (límite de ciclos) | ✅ Adaptado: límite de *supersteps del grafo*, no de un loop LLM↔tool | `GRAPH_RECURSION_LIMIT = 25` (`backend/config.py`), aplicado vía `with_graph_limits()` (`backend/api/dependencies.py`) en cada `ainvoke()`/`astream()` |
| `Timeout` (límite de tiempo) | ✅ Por turno, no por sesión — más un `LLM_TIMEOUT_SECONDS` por llamada individual | `GRAPH_TURN_TIMEOUT_SECONDS = 60.0` cancela el turno completo si LLM/MCP/BD se cuelgan (`chat.py`, `admin.py`); `llm_timeout_seconds` en `llm_factory.py` acota cada `ainvoke()` de LLM por separado |
| `Token budget` (límite de tokens consumidos) | ❌ **No existe como condición de terminación** | Existe `llm_max_output_tokens`/`{triage,evaluator,resolver}_model_max_tokens` — es un tope de tokens de **salida por llamada** (parámetro de generación), no un presupuesto acumulado que corte el agente. `llm_usage` (tabla BD + `usage_service.py`, ver `defenderDashboardCostes.md`) registra coste/tokens por sesión para el dashboard de Costes, pero es solo observabilidad — nada lee esa tabla para decidir detener una conversación |
| `Terminación natural` (el LLM responde sin pedir tools) | ⚠️ **No aplica tal cual** | Esta condición asume un loop agéntico (ReAct: el LLM decide si llama una tool o responde). ReFlow no tiene ese loop — las llamadas MCP están hardcodeadas en Python dentro de cada nodo (ver §4, "¿Por qué NO dejamos que el LLM elija qué tool llamar?"); el LLM nunca "pide" una tool, así que nunca puede "decidir dejar de pedirlas". El cierre real del turno lo decide un guard determinista (`route_after_*` en `graph.py`) devolviendo `"__end__"`, no el LLM |

### Extra que tenemos y no está en el framework docente

- **`MAX_CONVERSATION_TURNS = 40`** (`config.py`, aplicado en `chat.py::_conversation_turn_limit_reached`): corta la conversación completa si un mismo `thread_id` acumula demasiados turnos — protección a nivel de *sesión*, distinta de `GRAPH_RECURSION_LIMIT` (que limita ciclos *dentro de un solo turno*).
- **`ThreadLockRegistry`** (`dependencies.py`): no es un límite de iteración, sino un guardarraíl de concurrencia — serializa invocaciones solapadas al mismo `thread_id` (doble clic, reintento de red) para que no se dispare el grafo dos veces en paralelo sobre el mismo checkpoint.

### Por qué la "terminación natural" no aplica: no es un descuido, es el mismo argumento de fondo del proyecto

Igual que en §4 ("¿Por qué NO dejamos que el LLM elija qué tool llamar?"), el
routing y la decisión de parar son deliberadamente deterministas. Un agente con
loop de tools necesita ese mecanismo porque, sin él, el LLM podría seguir
pidiendo tools indefinidamente; ReFlow no tiene ese riesgo porque el LLM nunca
tuvo esa capacidad de pedir tools en primer lugar — el guardarraíl "sobra"
porque el problema que resuelve no existe en esta arquitectura, no porque se
haya pasado por alto.

### Gap real a reconocer en la defensa

El único hueco genuino es el **token budget como guardarraíl** (no como
métrica de coste): hoy nada impediría que un turno con contexto muy largo
(ej. una conversación de 40 turnos, justo en el límite de
`MAX_CONVERSATION_TURNS`) generase una factura alta antes de que
`MAX_CONVERSATION_TURNS` la corte. Mitigantes ya existentes que reducen el
riesgo sin cerrarlo del todo: `max_history_messages=20` (recorta cuánto
historial se manda al LLM de triaje en cada llamada, `llm_factory.py::trim_history`)
y que cada nodo hace como máximo 1 llamada LLM por turno (nunca un loop). Pendiente
de una futura iteración: usar la fila que ya se registra en `llm_usage` para
cortar el turno si el coste acumulado de la sesión supera un umbral — no
implementado hoy, sería trabajo futuro (ver `docs/REMAINING_TASKS.md`).

---

## 15. Memoria de corto y largo plazo: taxonomía completa, cobertura real y gaps

§6 y §13 ya cubren *cómo* se implementa la memoria en ReFlow (checkpointer,
contexto aislado por nodo, `ReturnState` compartido). Esta sección la mapea
explícitamente contra la taxonomía estándar de memoria de agentes (corto
plazo: Buffer/Sliding Window/Token-based/Summarization; largo plazo:
Resumen/Episódica/Semántica/Procedimental/Customizada), para poder responder
con precisión si el tribunal pregunta "¿qué tipo de memoria usáis, de las que
hemos visto en clase?".

### 15.1 Memoria de corto plazo (STM): qué mecanismo usamos y por qué

**Mecanismo real**: `trim_history()` (`backend/agents/llm_factory.py`) — se
queda con los últimos `max_history_messages` (20 por defecto) mensajes del
historial antes de mandarlo al LLM. De las 4 estrategias estándar (Buffer /
Sliding Window+resumen / Token-based / Summarization), ReFlow implementa la
más simple: **Buffer puro** — corte por número de mensajes, sin resumir ni
medir tokens.

| Característica del framework | ¿Aplica en ReFlow? |
|---|---|
| "Se borra una vez que se reinicia la sesión" | ⚠️ Matizado: el *contenido* de la ventana no se pierde al reiniciar el proceso — el checkpointer (`AsyncPostgresSaver`) persiste el historial completo en Postgres por `thread_id`. Lo que se "reinicia" es el *scope*: es memoria de UN hilo de conversación, nunca cruza a otro `thread_id` |
| "Capacidad limitada por la ventana de contexto del modelo" | ✅ — por eso existe `trim_history`, para no depender de que el modelo aguante un contexto ilimitado |
| Quién la usa | Solo `triage_agent` — `evaluator_agent`/`resolution_agent` no reciben `state["messages"]` en absoluto (contexto aislado, ver §13) |

**Por qué Buffer y no Sliding Window / Token-based / Summarization** (para
anticipar la pregunta "¿por qué no algo más sofisticado?"):

1. Las conversaciones de devolución son cortas por diseño (5-15 turnos, ver
   §8) y `MAX_CONVERSATION_TURNS=40` es el techo duro — el caso donde un
   Buffer de 20 mensajes realmente "pierde contexto antiguo" (el contra que
   marca la tabla de estrategias del framework) es la minoría, no el caso
   típico.
2. Más importante — **el dato de negocio no vive solo en el buffer**: campos
   como `order_number` se re-inyectan explícitamente como `SystemMessage` en
   *cada* turno directamente desde el `ReturnState` estructurado
   (`triage.py`, bloque `if state.get("order_number"): context.append(...)`),
   que nunca se recorta. El buffer de chat solo sostiene tono y coherencia
   conversacional ("¿qué dijo el cliente hace 3 mensajes?"); los hechos que
   cambian el resultado de la devolución tienen su propio canal de memoria
   sin ventana. Esto reduce mucho el riesgo real de Sliding Window/Summarization
   (evitar "perder contexto importante") sin pagar su coste (resumir cuesta
   una llamada LLM extra; Token-based es más preciso pero más complejo).
3. Conclusión: **Buffer es una elección justificada para este caso de uso**,
   no una simplificación por omisión — ver el mismo criterio de "simplicidad
   deliberada" que el proyecto aplica en otras decisiones (§11, "Decisiones
   descartadas").

**RAG como extensión de contexto (no como memoria del agente)**: el
mecanismo "Recuperación RAG: los documentos relevantes se recuperan
dinámicamente" del framework también existe en ReFlow —
`search_return_policy()` en `evaluator.py` — pero sobre una base de
conocimiento **estática** (documentos de política de devolución), no sobre
interacciones pasadas del cliente. Es RAG de dominio, no memoria de agente;
importante no confundir los dos en la defensa.

### 15.2 Memoria de largo plazo (LTM): cobertura real por tipo

| Tipo (framework) | ¿Lo tenemos? | Detalle |
|---|---|---|
| **Resumen** | ❌ No | Ninguna conversación se resume ni se guarda un resumen textual reutilizable en el futuro |
| **Episódica** | ⚠️ Parcial | `return_history["returns"]` — lista de devoluciones pasadas del cliente (fecha, motivo, estado), persistida en `return_requests` (Postgres) y recuperada por `get_customer_return_history()` (MCP). Cubre solo devoluciones, no conversaciones completas |
| **Semántica** | ⚠️ Parcial | Los agregados `approved`/`rejected`/`total_returns` (mismo `return_history`) son un patrón aprendido del cliente, consumido por `policy_rules.py::rule_frequent_returner` (`FREQUENT_RETURNER_THRESHOLD=5`) para marcar posible abuso — una señal semántica real que **afecta una decisión de negocio** (HITL), aunque es una sola señal, no un perfil de cliente rico |
| **Procedimental** | ❌ No | Nada aprende ni almacena "cómo resolver mejor" a partir de casos pasados (sin biblioteca de casos, sin few-shot dinámico) |
| **Customizada** | ❌ No | Sin preferencias de cliente persistidas (tono, idioma...) — mismo argumento que §13 ya usa para justificar no tener un `store`: una devolución es una transacción de una sola sesión, sin requisito de negocio que lo pida hoy |

**El único mecanismo de LTM real y en uso** es la combinación
episódica+semántica de `return_history`: persiste entre sesiones distintas
(a diferencia del checkpointer, que es memoria de UN `thread_id`), y
efectivamente cambia el comportamiento del Evaluador. Es memoria de largo
plazo genuina, aunque acotada a un solo propósito (detectar clientes
frecuentes), no una capa general de "recordar al cliente".

### 15.3 ¿Deberíamos mejorarlo?

**STM: no hace falta tocarlo.** Buffer(20) + re-inyección de campos
estructurados ya cubre el caso de uso real sin el coste añadido de
Summarization/Token-based. Solo reconsiderar si en producción se observaran
conversaciones que agoten `MAX_CONVERSATION_TURNS` perdiendo contexto de
negocio real (no debería ocurrir, por el punto 2 de §15.1) — no hay evidencia
de eso hoy.

**LTM: una mejora ya resuelta, una descartada deliberadamente:**

1. ~~Resolver la ambigüedad de `chat_sessions`/`chat_messages`~~ — **RESUELTO**:
   eran esquema sin consumidor real (solo poblado por el generador de
   dataset sintético, nunca por el chat en producción — ver §6). En vez de
   conectarlas artificialmente para justificar su existencia, se eliminaron
   por completo (`015_drop_chat_sessions.sql`): el propósito que se les
   había dado (transcripción auditable de la conversación) ya lo cubre, y
   mejor, el checkpointer de LangGraph + Langfuse (tokens/coste/latencia por
   `thread_id`, algo que esas tablas nunca tuvieron). Menos esquema, menos
   código en el generador, cero pérdida de capacidad real.
2. **La memoria semántica es una señal única** (`rule_frequent_returner`) —
   si el proyecto evolucionara hacia personalización real del cliente (más
   allá de detectar abuso), ahí encajaría una memoria semántica más rica.
   Pero, igual que con el `store` descartado en §13, **no hay ningún
   requisito de negocio hoy que lo justifique** — añadirlo ahora sería
   sobreingeniería sin caso de uso, no una mejora. Se deja como está.

**Conclusión para la defensa**: la memoria de ReFlow es deliberadamente
acotada al alcance del producto (transacciones de devolución de una sola
sesión + una señal cross-sesión de abuso). El único gap real que había
(esquema sin consumidor) ya está eliminado, no solo documentado.

---

## 16. Patrones multiagente y control de agentes: contraste con el framework docente

### 16.1 Lab 3 — ¿Router o Pipeline?

| Patrón (lab) | ¿Lo seguimos? |
|---|---|
| **Router** (especialistas como tools de un router; memoria compartida vía `store`) | ❌ No — no hay un router/supervisor que despache dinámicamente a especialistas independientes. Descartado explícitamente en §1 (*"¿Por qué LangGraph y no LangChain secuencial?"*) a favor de un grafo explícito |
| **Pipeline** (extractor → enriquecedor → resumidor, con "expediente" explícito; memoria de trabajo se tira, la del usuario persiste) | ✅ **Es nuestro patrón exacto**: Triaje (extrae) → Evaluador (enriquece con elegibilidad) → Resolución (resume/actúa), con `ReturnState` como "expediente". Las "dos memorias" del lab son literalmente §13/§15: `ReturnState` (de trabajo, muere con el `thread_id`) vs. `return_history` (del cliente, persiste) |
| **Strands Agents** (mismo patrón, otro framework) | N/D — usamos LangGraph, no Strands (decisión ya justificada en §1) |

### 16.2 Best Practices - Control: contraste DO/DON'T

| DO (framework) | ¿Lo hacemos? |
|---|---|
| Límites claros desde el inicio | ⚠️ Existen hoy (`GRAPH_RECURSION_LIMIT`, `GRAPH_TURN_TIMEOUT_SECONDS`, §14), pero varios se añadieron **reactivamente** tras detectar el problema (p. ej. degradación silenciosa del checkpointer), no estaban desde el diseño inicial |
| Logging exhaustivo | ✅ Langfuse + `llm_usage` (`usage_tracking.py`) + `logger` en todos los nodos |
| Validación en múltiples capas | ✅ Pydantic structured output + `policy_rules.py` determinista + overrides de UI (`_apply_deterministic_selection`) |
| Plan de rollback | ❌ No existe — una devolución auto-aprobada (etiqueta generada, email enviado) no tiene ningún mecanismo de "deshacer". Un rollback real aquí sería una *transacción compensatoria* (nueva acción que revierte el efecto), no un "undo" literal — no implementado |
| Monitorear costos en tiempo real | ⚠️ Dashboard de Costes existe (`2_Costes.py`), pero es *on-demand* (se consulta al abrir la página), no un stream en vivo ni alertas si el gasto se dispara |
| Documentar comportamientos esperados | ✅ Todo `docs/defensaTFM/` |

| DON'T (framework) | ¿Lo evitamos? |
|---|---|
| Confiar ciegamente en salidas del agente | ✅ Evitado con fuerza — `refund_amount` nunca del LLM (siempre `compute_refund()`), `items_confirmed` nunca en el mismo turno de la inferencia, overrides deterministas por todo el código |
| Permitir acceso ilimitado a recursos | ⚠️ **Parcial** — CORS abierto a todo + **cero autenticación** en `/api/admin/*` (gap crítico ya trackeado, `REMAINING_TASKS.md` §1): cualquiera que alcance la API puede aprobar/rechazar/editar reembolsos sin login |
| Ignorar señales de alerta temprana | ✅ Evitado — la degradación del checkpointer se loguea Y lanza excepción en producción, nunca en silencio (`graph.py::_fail_or_degrade`) |
| Implementar solo después de problemas | ⚠️ Parcialmente cierto — varios guardarraíles (recursion limit, timeout) se añadieron reactivamente, no proactivamente desde el diseño inicial (mismo caso que la fila 1 de DO) |

### 16.3 Control de agentes: los 7 mecanismos

| Mecanismo | ¿Lo tenemos? |
|---|---|
| **Límites de recursos** (contadores, timeouts) | ✅ `GRAPH_RECURSION_LIMIT`, `GRAPH_TURN_TIMEOUT_SECONDS`, `MAX_CONVERSATION_TURNS`, `llm_timeout_seconds` — §14 |
| **Permisos** (RBAC, whitelists) | ❌ No existe RBAC real. Que Triaje no pueda crear devoluciones (§2) es porque su código no importa esa función — no hay ningún check de permisos en runtime que lo impida si alguien añadiera ese import. `/api/admin/*` no tiene autenticación (`REMAINING_TASKS.md` §1) |
| **Validación** (guardrails, validators) | ✅ Extenso — structured output + `policy_rules.py` + overrides deterministas (§9, §2) |
| **Logging** (structured logs) | ✅ Langfuse + `llm_usage` + `logger` |
| **HITL** (approval queues) | ✅ Núcleo del proyecto — `interrupt()` + `/api/admin/pending`, con los 3 tipos de decisión aplicables (Approve/Edit/Reject) — ver §12 |
| **Circuit Breakers** (estado y umbrales) | ❌ No existe (comprobado: `grep circuit_breaker` sin resultados). Si un MCP server falla repetidamente, cada llamada se reintenta igual hasta el timeout — no hay un estado que "abra el circuito" temporalmente |
| **Monitoreo** (dashboards, alertas) | ⚠️ Dashboards sí (Langfuse, Costes); alertas proactivas no — visibilidad pasiva, hay que ir a mirar |

### 16.4 ¿Merece la pena cerrar estos gaps?

Criterio aplicado (mismo que en §14/§15: no implementar por implementar):

- **Circuit Breakers, alertas proactivas, rollback**: **NO** implementar — resuelven problemas de *escala/tráfico real* o de *operación 24/7* que un TFM sin tráfico de producción no tiene. Documentar como límite consciente del alcance.
- **`Respond`**: no aplica al dominio (ya explicado en §12) — no es un gap, es un patrón no aplicable.
- **`Edit`**: ✅ **implementado** (ver §12) — barato, y refuerza el argumento central del proyecto (HITL realista, no binario).
- **Permisos/RBAC en `/api/admin/*`**: pendiente, trackeado como prioridad alta en `REMAINING_TASKS.md` §1 — el único gap de esta lista con severidad real (dinero sin autenticación), recomendado cerrarlo con una API key simple antes de cualquier despliegue, aunque no bloquea la defensa académica del TFM.
