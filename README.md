# ReFlow — Copiloto de Posventa Autónomo y Gestión Inteligente de Devoluciones

> 📐 [Ver diagrama de arquitectura (Draw.io)](docs/architecture.drawio)

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
| Dataset sintético + corpus de políticas RAG — `data/` | ✅ |
| Tests unitarios e integración — `tests/` | ✅ |
| Backend FastAPI (endpoints de chat y panel admin/HITL) — `backend/api/` | ✅ |
| Frontend Streamlit (chat cliente + dashboard admin) — `frontend/` | ✅ |
| Observabilidad LLM (Langfuse self-hosted vía Docker) — `langfuse_infra/` | ✅ (opcional) |

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
                 #     triage.py       — Agente de Triaje y Empatía
                 #     evaluator.py    — Agente Evaluador de Políticas (RAG + LLM)
                 #     policy_rules.py — Reglas de negocio deterministas (Chain of Rules)
                 #     resolution.py   — Agente de Resolución + HITL + Rechazo
     infra/       #   Infraestructura:
                 #     mcp_client.py      — Cliente MCP unificado (Supabase + Logistics)
                 #     llm_factory.py     — Factory compartida para construir el LLM de cada nodo
  services/      # Lógica de negocio pura (sin MCP ni LLM)
                 #   supabase_service.py  — consultas, RAG, mutaciones
                 #   logistics_service.py — etiquetas PDF, notificaciones
  mcp/           # Servidores MCP: wrappers finos sobre services/ (puertos 8001/8002)
  db/            # Cliente Supabase (singleton cacheado)
data/         # Dataset sintético + corpus de 17 políticas para RAG + eval_cases.csv
supabase/        # Migraciones SQL y seed de datos
langfuse_infra/ # Observabilidad LLM (Langfuse self-hosted, opcional) — ver su README
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

## API FastAPI

### Arrancar el servidor

```bash
# Asegúrate de tener los servidores MCP levantados (terminales 1 y 2 de arriba)
# Terminal 3 — API REST en http://localhost:8000
python -m backend.api.run --reload --port 8000
```

> En Windows, usa `python -m backend.api.run` en vez de `uvicorn backend.api.main:app`
> directamente: sin este wrapper, un arranque sin `--reload` tarda 30s conectando a
> Postgres antes de caer a memoria (ver comentario en `backend/api/run.py`).

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

## Frontend (Streamlit)

Aplicación web con dos vistas:
- **Chat del cliente** (`Chat.py`) — interfaz conversacional con streaming (SSE)
- **Panel admin** (`pages/1_Admin.py`) — KPIs, aprobación HITL, listado de devoluciones, buscador de pedidos

### Arrancar el frontend

```bash
pip install -r requirements.txt
streamlit run frontend/Chat.py
# → http://localhost:8501
```

Requiere el backend corriendo en `http://localhost:8000` (ver sección API FastAPI). Más
detalle en [`frontend/README.md`](frontend/README.md).

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

## Linting y formato

`black` (formato automático) y `flake8` (estilo/errores) están en `requirements.txt`.

```bash
# Formatear todo el código
black backend/ frontend/ data/ tests/

# Solo comprobar, sin modificar (útil en CI/pre-commit)
black --check backend/ frontend/ data/ tests/

# Linting
flake8 backend/ frontend/ data/ tests/
```

Config en `.flake8` (`max-line-length = 88`, igual que `black`) y `pyproject.toml`
(`[tool.black]`). Convención de comentarios (concisos, porqué no qué) en el skill
`.opencode/skills/arquitectura-backend/`.

## Dataset y políticas RAG

El directorio `data/` contiene:
- **`policies/`** — 17 documentos Markdown con las políticas de devolución por categoría
  (se vectorizan en `policy_embeddings` de Supabase para el RAG).
- **`eval_cases.csv`** — Golden dataset etiquetado (valid/invalid/human_review) para
  benchmarking del Agente Evaluador.
- **`generate_dataset.py`** — Script determinista (seed fija) que genera los datos
  sintéticos.

Ver [`data/README.md`](data/README.md) para más detalle.

## Observabilidad LLM (Langfuse, opcional)

[Langfuse](https://langfuse.com) traza cada llamada al LLM dentro del grafo
de agentes (prompts, respuestas, tokens, latencia, coste) para poder
depurar conversaciones desde un panel web. Es **opcional**: sin configurar,
la app funciona exactamente igual, sin trazas.

Todo lo relacionado vive en [`langfuse_infra/`](langfuse_infra/README.md)
(stack self-hosted vía Docker: Postgres + ClickHouse + Redis + MinIO +
langfuse-web/worker, más el pequeño adaptador Python que engancha el
`CallbackHandler` en `backend/api/routers/chat.py`). Sigue el
[README de esa carpeta](langfuse_infra/README.md) para levantarlo la
primera vez; una vez configurado, `start_all.sh`/`stop_all.sh` ya lo
arrancan y paran junto con el resto de servicios automáticamente.

## Guía rápida de arranque (todos los servicios)

Resumen de todos los pasos, en orden, para levantar la app completa desde cero.
Los pasos 1-4 se hacen una sola vez; los pasos 5-8 requieren **4 terminales
abiertas en paralelo** (uno por proceso).

| # | Terminal | Paso | Comando |
|---|----------|------|---------|
| 1 | — | Crear y activar entorno virtual | `python3 -m venv .venv` <br> `source .venv/Scripts/activate` |
| 2 | — | Instalar dependencias | `pip install -r requirements.txt` |
| 3 | — | Configurar variables de entorno | `cp .env.example .env` y editar `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_DB_URL`, `OPENAI_API_KEY` |
| 4 | — | Verificar conexión a Supabase *(opcional)* | Ver script en [Configuración del entorno → 4. Verificar conexión](#configuración-del-entorno) |
| 5 | Terminal 1 | Arrancar MCP Supabase (datos + RAG) | `python -m backend.mcp.mcp_supabase` → `http://localhost:8001/mcp` |
| 6 | Terminal 2 | Arrancar MCP Logística | `python -m backend.mcp.mcp_logistics` → `http://localhost:8002/mcp` |
| 7 | Terminal 3 | Arrancar API FastAPI | `python -m backend.api.run --reload --port 8000` → `http://localhost:8000` |
| 8 | Terminal 4 | Arrancar frontend Streamlit | `streamlit run frontend/Chat.py` → `http://localhost:8501` |

Orden de arranque importante: **MCP servers (5-6) → API (7) → Frontend (8)**,
ya que cada capa depende de que la anterior esté levantada. Con los 4 procesos
activos, la app queda disponible en `http://localhost:8501` (frontend) con el
backend en `http://localhost:8000` (Swagger en `/docs`).

### Arranque automático

[`start_all.sh`](start_all.sh) (Git Bash) automatiza los 8 pasos anteriores:
crea el `.venv` si no existe, instala dependencias, genera `.env` desde
`.env.example` si falta, y abre los 4 procesos en ventanas de Git Bash
separadas, en el orden correcto. Si ya tienes Langfuse configurado (ver
sección anterior), también lo levanta; si no, lo salta sin bloquear el
resto.

```bash
./start_all.sh
```

Para pararlo todo (incluido Langfuse, si está corriendo): `./stop_all.sh`.
