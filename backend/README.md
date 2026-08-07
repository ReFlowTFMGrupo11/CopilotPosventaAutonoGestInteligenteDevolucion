# backend/ — Sistema multi-agente + API web

Todo el "cerebro" de ReFlow: el grafo de agentes LangGraph, los servidores
MCP que le dan acceso a datos/herramientas, la lógica de negocio pura, y la
API FastAPI que expone ese grafo a la web (frontend Streamlit).

## Estructura

```
backend/
  models/        # Modelos Pydantic compartidos (dominio)
    returns.py   #   Product, OrderItem, ReturnItem, ShippingLabelItem, TriageOutput
    state.py     #   ReturnState — TypedDict del estado del grafo LangGraph
  agents/        # Sistema multi-agente LangGraph
    graph.py     #   StateGraph: nodos, aristas condicionales, checkpointer
    state.py     #   Re-export de ReturnState (compatibilidad de imports)
    nodes/       #   Los 3 agentes + sus nodos auxiliares:
      triage.py     — Agente de Triaje y Empatía (+ fetch_order_data)
      policy.py     — Agente Evaluador de Políticas (RAG)
      resolution.py — Agente de Resolución (+ HITL + Rechazo)
    infra/       #   Infraestructura de soporte:
      mcp_client.py      — Cliente MCP unificado (HTTP, Supabase + Logistics)
      session_tracker.py — Registro de sesiones/mensajes para métricas
    cli/         #   demo_chat.py — demo interactiva de terminal, multi-turno
  services/      # Lógica de negocio pura (sin MCP ni LLM)
    supabase_service.py  — consultas, RAG (vectorización + pgvector), mutaciones
    logistics_service.py — generación de etiqueta PDF, notificación simulada
  mcp/           # Servidores MCP: wrappers finos sobre services/ (puertos 8001/8002)
    mcp_supabase.py   — datos + RAG (get_order_details, search_return_policy, ...)
    mcp_logistics.py  — logística (generate_shipping_label, send_customer_notification)
  db/            # Cliente Supabase (singleton cacheado)
    supabase_client.py
  schemas.py     # Modelos Pydantic del contrato HTTP (API web, no del grafo)
  dependencies.py# Providers de FastAPI (grafo singleton, registro HITL en memoria)
  main.py        # App FastAPI: expone el grafo como API web con streaming SSE
```

## Las tres capas, de dentro hacia fuera

1. **`services/`** — la única capa que toca Supabase/OpenAI/reportlab
   directamente. Sin esta capa reutilizable, cada punto de entrada
   (MCP, CLI, API web) reimplementaría sus propias consultas.
2. **`mcp/`** — envuelve cada función de `services/` como una "tool" que un
   LLM puede invocar por el protocolo MCP (JSON Schema + transporte HTTP).
   Corren como **dos procesos aparte** (`python -m backend.mcp.mcp_supabase`
   en `:8001`, `python -m backend.mcp.mcp_logistics` en `:8002`).
3. **`agents/`** — el grafo LangGraph que orquesta los 3 agentes, llamando a
   las tools MCP a través de `agents/infra/mcp_client.py` (nunca a
   `services/` directamente, para mantener la separación agente↔herramienta
   del diseño MCP).

Dos "puertas de entrada" distintas usan ese mismo grafo sin duplicar lógica:

- **`agents/cli/demo_chat.py`** — demo de terminal, un proceso Python que
  invoca `graph.ainvoke(...)` directamente en un bucle `input()`.
- **`main.py`** (+ `schemas.py`, `dependencies.py`) — API web FastAPI, para
  que el frontend Streamlit (`../frontend/`) pueda chatear por HTTP en vez
  de por terminal.

## `main.py` — la API web

Construida sobre el **mismo** `build_return_graph()`/`get_return_graph()`
de `agents/graph.py`, sin reimplementar el flujo de agentes.

| Método y ruta | Qué hace |
|---|---|
| `GET /health` | Comprobación trivial de que el proceso está vivo. |
| `POST /api/chat/stream` | Un turno de chat (`{message, thread_id}`). Responde en streaming **Server-Sent Events**: un evento `agent_step` por cada nodo del grafo que termina, y un evento final `final` (respuesta lista) o `awaiting_admin` (el grafo se pausó por HITL). |
| `GET /api/admin/pending` | Lista las conversaciones que el grafo dejó en pausa (`interrupt()`) porque el reembolso solicitado supera 100 €. |
| `POST /api/admin/approve/{thread_id}` | Aplica la decisión de un administrador (`{"approved": true/false}`) y **reanuda ese `thread_id` exacto** con `Command(resume=...)` — no se re-ejecuta el flujo desde el principio. |

### Cómo se gestiona el HITL (Human-in-the-Loop)

`resolution_agent` (`agents/nodes/resolution.py`) llama a `interrupt(...)`
**antes** de invocar ninguna tool MCP cuando `_needs_admin_approval(state)`
detecta alguna señal de `dataset/policies/00_marco_general_devoluciones.md`
§5 (reembolso > 100 €, motivo sensible como `allergic_reaction`/
`counterfeit_suspicion`, fecha de entrega en zona frontera del plazo, o
más de 3 devoluciones aprobadas en los últimos 90 días). Esto importa
porque LangGraph, al reanudar un nodo interrumpido, vuelve a ejecutarlo
desde el principio: como no hay ninguna llamada con efectos secundarios
(crear la devolución, generar la etiqueta) antes del `interrupt()`,
reanudar es seguro y no duplica nada.

`backend/dependencies.py::get_pending_store()` mantiene, en memoria por
proceso (`app.state.pending_admin`), qué `thread_id` están pausados — es
solo una caché de lectura rápida para el panel de administración; la fuente
de verdad real es siempre `graph.aget_state(config)` (LangGraph/checkpointer).

## Cómo arrancarlo

```bash
# Terminal 1 — MCP Supabase (datos + RAG)
python -m backend.mcp.mcp_supabase

# Terminal 2 — MCP Logística
python -m backend.mcp.mcp_logistics

# Terminal 3 — API FastAPI
uvicorn backend.main:app --reload
```

Requiere `.env` con `SUPABASE_API_URL`, `SUPABASE_SERVICE_KEY`,
`SUPABASE_DB_URL` (opcional, si falta se usa memoria en vez de persistencia
en PostgreSQL) y `OPENAI_API_KEY`.

Alternativa sin API web: `python -m backend.agents.cli.demo_chat` (solo
necesita los dos servidores MCP arriba, no `main.py`).

## Diagramas y documentación relacionada

- [`../docs/graph_diagram.md`](../docs/graph_diagram.md) — diagrama del
  grafo LangGraph en sí (nodos y aristas).
- [`../docs/FLUJO_LLAMADAS.md`](../docs/FLUJO_LLAMADAS.md) — flujo completo
  extremo a extremo, incluyendo el paso exacto de vectorización del RAG.
