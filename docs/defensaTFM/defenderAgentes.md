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
| **Triaje** | Empatía + extracción de datos | 0.3 | Necesita creatividad para conversar naturalmente |
| **Evaluador** | Auditoría de políticas | 0.0 | Debe ser determinista y objetivo |
| **Resolución** | Ejecutar acciones + comunicar | 0.4 | Balance entre claridad y calidez |

### Ventajas de la separación

1. **Contexto acotado**: Cada agente recibe solo el prompt y datos que necesita. Un solo agente con todo saturaría el contexto.
2. **Seguridad**: El agente de Triaje no puede ejecutar acciones (crear devoluciones, generar etiquetas). Solo el Resolución tiene acceso a esas herramientas.
3. **Testabilidad**: Se puede testear cada nodo de forma aislada con mocks.
4. **Auditoría**: El Evaluador siempre devuelve JSON estructurado con `is_eligible` + `eligibility_reason`, trazable y auditable.

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
| Largo plazo | Tabla `chat_sessions` + `chat_messages` | UI, auditoría, analytics |

El checkpointer guarda todo el estado (incluido `messages`) asociado a un `thread_id`. Cuando el usuario vuelve (mismo `thread_id`), el grafo se reanuda con todo el historial.

### Persistencia del estado conversacional (Checkpointer)

El grafo LangGraph utiliza un *checkpointer* para persistir el estado completo de cada conversación entre turnos. Cada sesión de usuario se identifica mediante un `thread_id` único, y al finalizar cada turno (cuando el grafo alcanza el nodo `END`), el checkpointer serializa el `ReturnState` —incluyendo el historial de mensajes, datos parciales extraídos y decisiones intermedias— y lo almacena.

En desarrollo se emplea `InMemorySaver`, que mantiene el estado en memoria RAM (se pierde al reiniciar el proceso). En producción se utilizaría `PostgresSaver`, que persiste el estado en tablas gestionadas automáticamente por LangGraph (`checkpoints`, `checkpoint_writes`, `checkpoint_migrations`) dentro de la misma instancia PostgreSQL de Supabase, en un schema separado (`langgraph`) para no interferir con el modelo de datos del dominio.

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

---

## 13. Los tres ámbitos de memoria multiagente, aplicados a ReFlow

| Ámbito (teoría) | Mecanismo en ReFlow | Quién lo usa |
|---|---|---|
| **Corto plazo** (historial del chat) | `checkpointer` (`AsyncPostgresSaver`/`InMemorySaver`) + `thread_id` | Solo `triage_agent` — es el único nodo que conversa con el cliente turno a turno |
| **Contexto de subtarea** (encargo acotado, no el chat) | Cada nodo construye su propio bloque de `context`/`SystemMessage` con solo los datos que necesita evaluar o resolver | `evaluator_agent` (política + pedido + historial de devoluciones) y `resolution_agent` (`resolution_context`) |
| **Compartida** (largo plazo, cruza entre agentes) | El propio `ReturnState` del grafo — poblado por `triage`/`fetch_order_data` y leído por `evaluator`/`resolution` sin que nadie repita nada | Todos los nodos, vía el estado del grafo (no vía un `store` separado) |

### ¿Por qué no hay un `store` (`InMemoryStore`) como en el lab 1?

El patrón `store` de la clase resuelve un problema que ReFlow **no tiene**: preferencias de un mismo usuario que persisten *entre conversaciones distintas* (ej. "el cliente prefiere que le hablen en tono formal", vigente en la conversación de la semana que viene). Una devolución es una transacción de una sola sesión — todo lo que un agente necesita saber del cliente/pedido nace y muere dentro del mismo `thread_id`, y ya viaja en el `ReturnState` compartido de la fila de arriba. Añadir un `store` cruzaría información entre distintas solicitudes de devolución sin que exista ningún requisito de negocio que lo pida — sería una capa de memoria sin caso de uso.

Si en el futuro ReFlow necesitara recordar algo del cliente entre solicitudes distintas (p. ej. "cliente VIP: aplicar tolerancia extra de plazo"), ahí sí correspondería un `store` compartido entre los tres nodos, poblado una vez y leído por `evaluator_agent` sin pasar por el chat — el mismo patrón que el lab 1, aplicado a un hecho que sí sobrevive a la sesión.

### Contexto aislado: el caso que SÍ había que corregir

Antes de esta revisión, `evaluator_agent` inyectaba `trim_history(state["messages"])` (el chat crudo, recortado a los últimos `MAX_HISTORY_MESSAGES`) además de su `context` ya autosuficiente — exactamente el antipatrón que la clase pide reconocer ("si le pasas todo el historial a cada subagente... el subagente se distrae con contenido que no es de su tarea"). `resolution_agent` nunca tuvo este problema (construye su propio `resolution_context` sin tocar `state["messages"]`). Se eliminó la inyección redundante en `evaluator.py`; el criterio de "quién necesita el chat" queda ahora así:

- **Necesita el chat**: `triage_agent` (conversa con el cliente).
- **No lo necesita**: `evaluator_agent` y `resolution_agent` (reciben el encargo ya resuelto en datos estructurados).
