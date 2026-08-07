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

Usamos `interrupt()` porque la pausa es **condicional** — solo si
`_needs_admin_approval(state)` encuentra alguna señal de
`dataset/policies/00_marco_general_devoluciones.md` §5 (importe > 100€,
motivo sensible, zona frontera del plazo o reincidencia reciente) —, no
siempre.

```python
needs_hitl, reasons = _needs_admin_approval(state)
if needs_hitl:
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

## 9. Flujo del grafo

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
                    │   ├── sin señales HITL → END (auto-aprobado)
                    │   └── >100€ / motivo sensible / zona frontera /
                    │       reincidencia → interrupt (HITL)
                    │                    │
                    │              hitl_admin → END
                    └─── (order no encontrado)
```

---

## 10. Decisiones descartadas

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Un solo agente con muchas tools | Saturación del contexto, riesgo de que ejecute acciones sin evaluar |
| Clases para los agentes | Sobreingeniería; LangGraph espera funciones, no hay estado interno mutable |
| LLM elige tools libremente (`bind_tools` sin restricción) | No determinista; el LLM puede llamar a la tool incorrecta o no llamar ninguna |
| Import directo de services (sin MCP) | No demuestra el protocolo MCP end-to-end; no refleja la arquitectura de producción |
| Pydantic para el estado del grafo | Overhead de validación en cada nodo; TypedDict es lo idiomático en LangGraph |
