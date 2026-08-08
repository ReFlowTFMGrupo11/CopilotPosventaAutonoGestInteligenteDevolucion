# Defensa de la Arquitectura FastAPI

## 1. ¿Por qué FastAPI?

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Flask | Síncrono por defecto, no soporta `async/await` nativamente (necesario para `graph.ainvoke()`) |
| Django | Demasiado opinionado para un backend de API puro. ORM innecesario (ya usamos Supabase) |
| Express.js (Node) | Cambio de lenguaje. Todo el stack es Python (LangGraph, MCP, Supabase SDK) |
| LangServe | Deprecado por LangChain en favor de LangGraph Platform. Demasiado acoplado |

**Decisión**: FastAPI es async-native, tiene validación con Pydantic (que ya usamos en `backend/models/`), genera docs OpenAPI automáticas y es el estándar de facto para APIs de ML/AI en Python.

---

## 2. Principio arquitectónico: FastAPI no habla con MCP

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI                                   │
├────────────────────────────────┬────────────────────────────────┤
│  Endpoints de CHAT / HITL      │  Endpoints de CONSULTA          │
│  (involucran agentes + LLM)    │  (datos puros, sin LLM)         │
│                                │                                  │
│  → graph.ainvoke()             │  → backend/services/ (directo)   │
│    (el grafo usa MCP           │    (sin pasar por MCP)           │
│     internamente)              │                                  │
└────────────────────────────────┴────────────────────────────────┘
```

### ¿Por qué FastAPI NO llama a MCP directamente?

MCP es un protocolo diseñado para que un **LLM elija herramientas**. FastAPI ya sabe exactamente qué función necesita:

```python
# ❌ Innecesario: FastAPI → HTTP → MCP Server → supabase_service
result = await mcp_client.call_tool("get_order_details", {"order_id": id})

# ✅ Directo: FastAPI → supabase_service (mismo proceso, cero overhead)
from backend.services.supabase_service import get_order_details
result = await get_order_details(order_id)
```

El overhead de MCP (HTTP + JSON-RPC + serialización) no aporta nada cuando el caller ya sabe la función exacta.

---

## 3. Dos tipos de endpoint, dos caminos

### Camino A: Chat y HITL → Grafo LangGraph

```python
@router.post("/api/chat")
async def chat(request: ChatRequest):
    graph = await get_return_graph()
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=request.message)]},
        config={"configurable": {"thread_id": request.thread_id}},
    )
    return {"response": result["messages"][-1].content, ...}
```

Una sola llamada a `graph.ainvoke()` ejecuta internamente:
```
triage → fetch_order_data (MCP) → evaluator (MCP/RAG) → resolver (MCP) o reject
```

El **checkpointer** restaura el estado previo del `thread_id`, permitiendo conversaciones multi-turno sin mantener conexiones abiertas.

### Camino B: Consultas de dashboard → Services directos

```python
@router.get("/api/orders/{order_id}")
async def get_order(order_id: str):
    return await supabase_service.get_order_details(order_id)

@router.get("/api/admin/returns")
async def list_returns(status: str = None):
    # Query directa a Supabase, sin LLM ni MCP
    ...
```

---

## 4. HITL (Human-in-the-Loop) via FastAPI

Cuando el grafo se pausa (reembolso >100€), el admin reanuda desde el panel:

```python
@router.post("/api/admin/{thread_id}/approve")
async def approve_return(thread_id: str):
    graph = await get_return_graph()
    result = await graph.ainvoke(
        Command(resume={"approved": True}),
        config={"configurable": {"thread_id": thread_id}},
    )
    return {"resolution": result.get("resolution")}
```

El grafo continúa exactamente donde se pausó (`interrupt()` en `resolution.py`) gracias al checkpointer.

---

## 5. Estructura de archivos propuesta

```
backend/api/
├── __init__.py
├── main.py              # app = FastAPI(), include routers, startup/shutdown
├── routers/
│   ├── chat.py          # POST /api/chat, POST /api/chat/new, GET /api/chat/{id}/history
│   ├── admin.py         # GET /api/admin/pending, POST .../approve, POST .../reject
│   └── orders.py        # GET /api/orders/{id}, GET /api/customers/{id}/history
├── schemas.py           # Request/Response models (ChatRequest, ChatResponse, etc.)
└── dependencies.py      # get_graph(), get_settings(), auth
```

---

## 6. ¿Por qué no LangGraph Platform / LangServe?

| Opción | Estado | Problema |
|--------|--------|----------|
| LangServe | Deprecado (2025) | LangChain recomienda migrar a LangGraph Platform |
| LangGraph Platform (Cloud) | SaaS de pago | Vendor lock-in, no self-hosteable en plan free |
| LangGraph Platform (self-hosted) | Requiere licencia enterprise | No viable para un TFM |
| **FastAPI + grafo compilado** ✅ | Estable, gratuito, estándar | Control total, misma funcionalidad |

Con FastAPI + `graph.ainvoke()` tenemos lo mismo que LangGraph Platform ofrece (API de chat, checkpointing, HITL) pero sin dependencia de un servicio externo.

---

## 7. Decisiones arquitectónicas relevantes

### 7.1 Streaming SSE vs. respuesta síncrona

Se implementaron **dos modos de consumo** para el endpoint de chat:

| Endpoint | Modo | Uso |
|----------|------|-----|
| `POST /api/chat` | JSON síncrono (`graph.ainvoke`) | Pruebas con curl/Postman, clientes simples |
| `POST /api/chat/stream` | SSE streaming (`graph.astream`) | Frontend, UX en tiempo real |

El endpoint síncrono espera a que todo el grafo termine (~10-20s) y devuelve la respuesta de golpe. El endpoint streaming emite un evento SSE cada vez que un nodo del grafo termina, reduciendo la **latencia percibida** a 2-3s (aunque la latencia real sea la misma). Esto se alinea con los umbrales de Nielsen: >1s requiere indicador de progreso, >10s requiere feedback continuo.

La clave técnica es la diferencia entre `async` y `streaming`:
- `await graph.ainvoke()` — asíncrono (no bloquea el servidor), pero el caller espera el resultado completo.
- `async for chunk in graph.astream(..., stream_mode="updates")` — asíncrono **y** streaming: emite resultados parciales conforme cada nodo termina.

### 7.2 Gestión de pendientes HITL: caché en memoria vs. base de datos

Para listar las devoluciones pendientes de aprobación humana (HITL >100€), se evaluaron dos estrategias:

1. **Caché en memoria** (`dict` en `app.state`): el endpoint de streaming almacena el payload del `interrupt()` en un diccionario Python al detectar que el grafo se ha pausado. Ventaja: acceso instantáneo. Desventajas: no sobrevive reinicios del servidor, no es compatible con despliegues multi-worker (cada instancia de uvicorn tendría su propia caché), e introduce una segunda fuente de verdad que requiere sincronización manual.

2. **Consulta directa a base de datos** (`return_requests.status = 'pending_approval'`): la fuente de verdad es Supabase. Ventaja: persistente, consistente, compatible con múltiples workers. Desventaja: una query por cada consulta (mitigable con índices).

**Decisión**: se optó por la base de datos como **fuente única de verdad**, complementada con `graph.aget_state()` del checkpointer de LangGraph para verificar si un thread específico está realmente pausado antes de re-invocarlo (guard anti re-invocación).

**Escalabilidad a producción**: en un entorno productivo, esta solución escalaría con una tabla dedicada `pending_approvals` con campos de SLA (`expires_at` para escalar si nadie responde en 24h) y asignación a operadores (`assigned_to`).

### 7.3 Inyección de dependencias con `Depends()` + `app.state`

El grafo LangGraph se inyecta en los endpoints mediante `Depends(get_graph)`, que lo cachea en `request.app.state.graph`:

```python
async def get_graph(request: Request):
    if getattr(request.app.state, "graph", None) is None:
        request.app.state.graph = await get_return_graph()
    return request.app.state.graph
```

Esto permite sustituir el grafo real por un mock en tests con `app.dependency_overrides[get_graph] = mock_graph`, sin modificar el código de producción.

---

## 8. Resumen para la presentación

> "FastAPI actúa como gateway entre el frontend (Streamlit) y el sistema multi-agente.
> Para endpoints de chat y HITL, invoca el grafo LangGraph completo con `ainvoke()` —
> una sola llamada que orquesta los 3 agentes internamente. Para consultas de dashboard
> (listados, KPIs), importa directamente de `backend/services/` sin pasar por MCP ni
> por el LLM, porque son queries deterministas que no necesitan razonamiento.
> Esta separación minimiza la latencia y el coste de API de OpenAI para operaciones
> que no requieren inteligencia artificial."
