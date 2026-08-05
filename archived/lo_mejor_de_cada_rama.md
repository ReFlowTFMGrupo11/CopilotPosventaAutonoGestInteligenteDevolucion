# Lo mejor de cada rama

## Rama: `feature/MCP_Agent_CCS`

| Elemento | Ubicación actual | Descripción |
|----------|-----------------|-------------|
| Dataset sintético | `dataset/` | Script generador determinista (`generate_dataset.py`) + estadísticas |
| Corpus de políticas (RAG) | `dataset/policies/` | 17 documentos Markdown con reglas de devolución por categoría (electrónica, moda, alimentación, etc.) |
| Golden dataset de evaluación | `dataset/eval_cases.csv` | Casos etiquetados (valid/invalid/human_review) para benchmarking del Agente Evaluador |
| Tipado Pydantic de productos | `backend/mcp/mcp_supabase.py`, `mcp_logistics.py` | Modelos `ReturnItem`, `ShippingLabelItem` con tipado estricto |
| Servidores MCP | `backend/mcp/` | `mcp_supabase.py` (puerto 8001) y `mcp_logistics.py` (puerto 8002) |
| Capa de datos | `backend/db/supabase_client.py` | Cliente Supabase compartido |
| Migraciones SQL | `supabase/migrations/` | 11 migraciones incrementales para crear el esquema |
| Seed de datos | `supabase/seed.sql` | Datos iniciales para desarrollo |

## Rama: `agentes-tamara-testing`

| Elemento | Ubicación actual | Descripción |
|----------|-----------------|-------------|
| Grafo LangGraph | `backend/agents/graph.py` | Orquestación declarativa con `StateGraph`, routing condicional y checkpointer PostgreSQL |
| Estado tipado compartido | `backend/agents/state.py` | `ReturnState` (TypedDict) con reducer `add_messages` para acumular historial |
| Nodo Triaje | `backend/agents/nodes/triage.py` | Agente conversacional con structured output (Pydantic) + nodo `fetch_order_data` |
| Nodo Evaluador | `backend/agents/nodes/policy.py` | Búsqueda RAG de políticas + evaluación LLM con JSON estructurado |
| Nodo Resolución | `backend/agents/nodes/resolution.py` | Genera etiqueta, registra devolución, notifica cliente. HITL con `interrupt()` si >100€ |
| Cliente MCP unificado | `backend/agents/infra/mcp_client.py` | Wrapper con `MultiServerMCPClient`, routing automático de tools por servidor, conexión lazy |
| Session tracker | `backend/agents/infra/session_tracker.py` | Registro de sesiones y mensajes en Supabase para métricas |
| Demo interactiva | `backend/agents/cli/demo_chat.py` | Chat multi-turno con checkpointer persistente |
| Capa de servicios | `backend/services/` | `supabase_service.py` y `logistics_service.py` (lógica de negocio desacoplada de MCP) |
| Tests unitarios | `tests/unit/` | Routing del grafo, logistics service, supabase service |
| Tests de integración | `tests/integration/` | Flujo completo del grafo, triage, policy y resolution agents |
| Fixtures compartidos | `tests/conftest.py` | Datos mock reutilizables (pedidos, historial, políticas, etiquetas) |
| Documentación técnica | `docs/graph_diagram.md` | Diagramas Mermaid del flujo + secuencia multi-turno |
| Diagrama ER | `docs/ER_diagram.md` | Esquema completo de la base de datos en Mermaid |

## Archivado (referencia histórica)

Movido a `archived/` — código supersedido pero conservado como referencia:

- `agente1ConMCP/`, `agente2ConMCP/`, `agente3ConMCP/` → sustituidos por `backend/agents/nodes/`
- `demo_flujo_completo.py` → sustituido por `backend/agents/cli/demo_chat.py`
- `doc/` (guia.md, flujo conversacional, auditoría) → docs actualizados en `docs/`
- PDFs y anotaciones del profesor
