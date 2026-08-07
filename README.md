# ReFlow — Copiloto de Posventa Autónomo y Gestión Inteligente de Devoluciones

TFM que propone "ReFlow", un sistema de agentes de IA Generativa para automatizar la
gestión de devoluciones y el soporte posventa en e-commerce. La arquitectura combina
**LangGraph** (orquestación multi-agente con estado compartido y memoria persistente),
**MCP (Model Context Protocol)** como capa de herramientas hacia **Supabase**
(PostgreSQL + pgvector para RAG sobre políticas de devolución), modelos de OpenAI
como motor de razonamiento, y una **API web (FastAPI) + frontend (Streamlit)** para
usar el sistema desde el navegador en vez de solo por terminal.

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
| Demo de consola — `backend/agents/cli/demo_chat.py` | ✅ |
| Backend FastAPI (chat en streaming + panel admin/HITL) — `backend/main.py` | ✅ |
| Frontend Streamlit (chat cliente + panel admin) — `frontend/` | ✅ |

## Estructura del repositorio

```
backend/
  models/        # Modelos Pydantic compartidos (Product, OrderItem, ReturnItem, etc.)
                 #   returns.py  — modelos de dominio
                 #   state.py    — ReturnState (TypedDict del grafo LangGraph)
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
    cli/         #   demo_chat.py — Demo interactiva multi-turno de terminal
  services/      # Lógica de negocio pura (sin MCP ni LLM)
                 #   supabase_service.py  — consultas, RAG, mutaciones
                 #   logistics_service.py — etiquetas PDF, notificaciones
  mcp/           # Servidores MCP: wrappers finos sobre services/ (puertos 8001/8002)
  db/            # Cliente Supabase (singleton cacheado)
  schemas.py     # Modelos Pydantic del contrato HTTP de la API web
  dependencies.py# Providers de FastAPI (grafo singleton, registro HITL en memoria)
  main.py        # API FastAPI: expone el grafo por HTTP con streaming SSE
  README.md      # Detalle de todo lo anterior
frontend/        # App Streamlit (chat cliente + panel admin), consume backend/main.py
  lib/           #   settings.py, api_client.py — cliente HTTP hacia la API
  Home.py        #   Página de entrada
  pages/         #   1_💬_Chat_Cliente.py, 2_🛠️_Panel_Admin.py
  README.md      #   Detalle de todo lo anterior
dataset/         # Dataset sintético + corpus de 17 políticas para RAG + eval_cases.csv
supabase/        # Migraciones SQL y seed de datos
tests/
  unit/          # Tests de routing, logistics_service, supabase_service
  integration/   # Tests del grafo completo, triage, policy y resolution agents
docs/            # Diagramas (grafo Mermaid, ER, flujo de llamadas end-to-end)
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
SUPABASE_API_URL=https://<tu-proyecto>.supabase.co
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

Transporte **Streamable HTTP**. Dos procesos locales, necesarios tanto para
la demo de consola como para la API web:

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

Para diagramas Mermaid detallados ver [`docs/graph_diagram.md`](docs/graph_diagram.md)
(el grafo en sí) y [`docs/FLUJO_LLAMADAS.md`](docs/FLUJO_LLAMADAS.md) (flujo
completo extremo a extremo: desde el mensaje del cliente hasta la
vectorización de la búsqueda RAG, incluyendo las llamadas HTTP a los
servidores MCP).

## Dos formas de usar el sistema

### A) Demo de consola (CLI)

```bash
python -m backend.agents.cli.demo_chat
```

Requiere los dos servidores MCP levantados y `SUPABASE_DB_URL` + `OPENAI_API_KEY` en `.env`.

### B) App web (FastAPI + Streamlit)

```bash
# Terminal 3 — API FastAPI en http://localhost:8000
uvicorn backend.main:app --reload

# Terminal 4 — Frontend Streamlit en http://localhost:8501
streamlit run frontend/Home.py
```

Incluye chat con streaming en vivo del razonamiento de los agentes, descarga
de la etiqueta PDF cuando la devolución se aprueba, y un panel de
administración para aprobar/rechazar los casos que el HITL deja pausados
(reembolso > 100 €) — ver el detalle de cada endpoint y cómo se reanuda el
grafo tras la decisión del administrador en
[`backend/README.md`](backend/README.md) y [`frontend/README.md`](frontend/README.md).

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
