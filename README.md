# ReFlow — Copiloto de Posventa Autónomo y Gestión Inteligente de Devoluciones

TFM que propone "ReFlow", un sistema de agentes de IA Generativa para automatizar la
gestión de devoluciones y el soporte posventa en e-commerce. La arquitectura combina
**LangGraph** (orquestación multi-agente con estado compartido y memoria persistente),
**MCP (Model Context Protocol)** como capa de herramientas hacia **Supabase**
(PostgreSQL + pgvector para RAG sobre políticas de devolución), y modelos de OpenAI
como motor de razonamiento.

## Estado actual del proyecto

| Bloque | Estado |
|---|---|
| Esquema Supabase (PostgreSQL + pgvector) — `supabase/` | ✅ |
| Servidor MCP de datos y políticas — `backend/mcp/mcp_supabase.py` | ✅ |
| Servidor MCP de logística — `backend/mcp/mcp_logistics.py` | ✅ |
| Grafo LangGraph (Triaje → Evaluador → Resolución) — `backend/agents/` | ✅ |
| HITL con `interrupt()` para reembolsos >100€ | ✅ |
| Memoria conversacional persistente (checkpointer PostgreSQL) | ✅ |
| Modelos Pydantic centralizados — `backend/models/` | ✅ |
| Dataset sintético + corpus de políticas RAG — `dataset/` | ✅ |
| Tests unitarios e integración — `tests/` | ✅ |
| Backend FastAPI (endpoints de chat y panel admin/HITL) — `backend/api/` | ✅ |
| Frontend Streamlit (chat cliente + dashboard admin) | ⏳ Pendiente |

## Estructura del repositorio

```
backend/
  models/        # Modelos Pydantic compartidos (Product, OrderItem, ReturnItem, etc.)
                 #   returns.py  — modelos de dominio
                 #   state.py    — ReturnState (TypedDict del grafo LangGraph)
  api/           # FastAPI — capa HTTP
                 #   main.py        — App, lifespan, CORS
                 #   schemas.py     — Pydantic DTOs (request/response)
                 #   dependencies.py— get_graph() dependency
                 #   routers/chat.py   — /api/chat endpoints
                 #   routers/admin.py  — /api/admin HITL endpoints
                 #   routers/orders.py — /api/orders, /api/stats
  agents/        # Sistema multi-agente LangGraph
    graph.py     #   Grafo: StateGraph con routing condicional y checkpointer
    state.py     #   Re-export de ReturnState (compatibilidad)
    nodes/       #   Nodos del grafo:
                 #     triage.py     — Agente de Triaje y Empatía
                 #     policy.py     — Agente Evaluador de Políticas (RAG)
                 #     resolution.py — Agente de Resolución + HITL + Rechazo
    infra/       #   Infraestructura:
                 #     mcp_client.py      — Cliente MCP unificado (Supabase + Logistics)
                 #     session_tracker.py — Registro de sesiones para métricas
    cli/         #   demo_chat.py — Demo interactiva multi-turno
  services/      # Lógica de negocio pura (sin MCP ni LLM)
                 #   supabase_service.py  — consultas, RAG, mutaciones
                 #   logistics_service.py — etiquetas PDF, notificaciones
  mcp/           # Servidores MCP: wrappers finos sobre services/ (puertos 8001/8002)
  db/            # Cliente Supabase (singleton cacheado)
dataset/         # Dataset sintético + corpus de 17 políticas para RAG + eval_cases.csv
supabase/        # Migraciones SQL y seed de datos
tests/
  unit/          # Tests de routing, logistics_service, supabase_service
  integration/   # Tests del grafo completo, triage, policy y resolution agents
docs/            # Diagramas (grafo Mermaid, ER, documentación de la fusión)
archived/        # Código histórico de referencia (agentes individuales pre-LangGraph)
```

## Configuración del entorno

### 1. Crear entorno virtual

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Variables de entorno

```bash
cp .env.example .env
```

Edita `.env` con tus valores:

```
SUPABASE_URL=https://<tu-proyecto>.supabase.co
SUPABASE_SERVICE_KEY=<tu-service-role-key>
SUPABASE_DB_URL=postgresql://postgres:<password>@<host>:5432/postgres
OPENAI_API_KEY=<tu-openai-api-key>
```

### 4. Verificar conexión

```bash
python -c "
import asyncio
from backend.db.supabase_client import get_supabase_client

async def test():
    client = await get_supabase_client()
    result = await client.table('customers').select('id').limit(1).execute()
    print('✅ Conexión exitosa:', result.data)

asyncio.run(test())
"
```

## Servidores MCP

Transporte **Streamable HTTP**. Dos procesos locales:

```bash
# Terminal 1 — Supabase (datos + RAG) en http://localhost:8001/mcp
python -m backend.mcp.mcp_supabase

# Terminal 2 — Logística en http://localhost:8002/mcp
python -m backend.mcp.mcp_logistics
```

### Tools disponibles

| Server | Tool | Descripción |
|--------|------|-------------|
| Supabase | `get_order_details` | Detalles del pedido + productos |
| Supabase | `get_customer_return_history` | Historial de devoluciones del cliente |
| Supabase | `search_return_policy` | Búsqueda semántica RAG sobre políticas |
| Supabase | `create_return_record` | Crear solicitud de devolución |
| Supabase | `update_return_status` | Actualizar estado (admin/HITL) |
| Logistics | `generate_shipping_label` | Generar PDF de etiqueta de transporte |
| Logistics | `send_customer_notification` | Simular envío de email transaccional |

## Sistema multi-agente (LangGraph)

El grafo orquesta 3 agentes como nodos de un `StateGraph` con estado compartido
(`ReturnState`) y memoria conversacional persistente:

```
START → Triage → [¿order_id + items?]
                    ├─ NO → END (espera siguiente mensaje del usuario)
                    └─ SÍ → Fetch Order Data → [¿error?]
                                                  ├─ SÍ → END
                                                  └─ NO → Evaluador → [¿elegible?]
                                                                        ├─ NO → Rechazo → END
                                                                        └─ SÍ → Resolución → [¿>100€?]
                                                                                               ├─ NO → END (aprobado)
                                                                                               └─ SÍ → HITL Admin → END
```

Para diagramas Mermaid detallados ver [`docs/graph_diagram.md`](docs/graph_diagram.md).

### Demo interactiva

```bash
python -m backend.agents.cli.demo_chat
```

Requiere los servidores MCP levantados y `SUPABASE_DB_URL` + `OPENAI_API_KEY` en `.env`.

## API FastAPI

### Arrancar el servidor

```bash
# Asegúrate de tener los servidores MCP levantados (terminales 1 y 2 de arriba)
# Terminal 3 — API REST en http://localhost:8000
uvicorn backend.api.main:app --reload --port 8000
```

### Endpoints disponibles

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/chat/new` | Crear sesión de chat (devuelve `thread_id`) |
| POST | `/api/chat` | Enviar mensaje al grafo de agentes |
| GET | `/api/chat/{thread_id}/state` | Estado actual del grafo |
| GET | `/api/admin/pending` | Devoluciones pendientes de HITL |
| POST | `/api/admin/{thread_id}/approve` | Aprobar devolución (reanuda grafo) |
| POST | `/api/admin/{thread_id}/reject` | Rechazar devolución (reanuda grafo) |
| GET | `/api/admin/returns` | Listar devoluciones (filtro `?status=`) |
| GET | `/api/admin/returns/{id}` | Detalle de una devolución |
| GET | `/api/orders/{order_id}` | Detalle de pedido |
| GET | `/api/customers/{id}/history` | Historial de devoluciones del cliente |
| GET | `/api/stats` | KPIs generales |

### Testear con curl

```bash
# 1. Health check
curl http://localhost:8000/health

# 2. Crear sesión
curl -X POST http://localhost:8000/api/chat/new
# → {"thread_id": "abc-123-..."}

# 3. Enviar mensaje (usa el thread_id del paso anterior)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "abc-123-...", "message": "Quiero devolver mi pedido ORD-001"}'

# 4. Consultar estado
curl http://localhost:8000/api/chat/abc-123-.../state

# 5. Ver devoluciones pendientes de aprobación
curl http://localhost:8000/api/admin/pending

# 6. Aprobar una devolución (HITL)
curl -X POST http://localhost:8000/api/admin/abc-123-.../approve \
  -H "Content-Type: application/json" \
  -d '{"reason": "Cliente VIP"}'

# 7. Consultar KPIs
curl http://localhost:8000/api/stats
```

### Documentación interactiva (Swagger)

Con el servidor arrancado, accede a:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## Tests

```bash
# Todos los tests
pytest tests/

# Solo unitarios
pytest tests/unit/

# Solo integración
pytest tests/integration/
```

## Dataset y políticas RAG

El directorio `dataset/` contiene:
- **`policies/`** — 17 documentos Markdown con las políticas de devolución por categoría
  (se vectorizan en `policy_embeddings` de Supabase para el RAG).
- **`eval_cases.csv`** — Golden dataset etiquetado (valid/invalid/human_review) para
  benchmarking del Agente Evaluador.
- **`generate_dataset.py`** — Script determinista (seed fija) que genera los datos
  sintéticos.

Ver [`dataset/README.md`](dataset/README.md) para más detalle.
