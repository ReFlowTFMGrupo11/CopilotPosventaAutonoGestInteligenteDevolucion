# ReFlow — Copiloto de Posventa Autónomo y Gestión Inteligente de Devoluciones

TFM que propone "ReFlow", un sistema de agentes de IA Generativa para automatizar la
gestión de devoluciones y el soporte posventa en e-commerce. La arquitectura objetivo
combina **LangChain** (orquestación multi-agente), **MCP (Model Context Protocol)** como
capa de herramientas hacia **Supabase** (PostgreSQL + pgvector para RAG sobre políticas
de devolución), **FastAPI** como backend y **Streamlit** como frontend conversacional.

El detalle completo del planteamiento, motivación y objetivos está en la propuesta del TFM
(`propuesta1.pdf`); el diseño técnico, el backlog por épicas y el cronograma están en
[`doc/guia.md`](doc/guia.md).

## Estado actual del proyecto

Este repositorio implementa por ahora las **Épicas 1 y 2** de `doc/guia.md`: la capa de
datos, los servidores MCP y el sistema multi-agente de LangChain (Triaje, Evaluador y
Resolución). Todavía no incluye el backend FastAPI ni el frontend Streamlit descritos en
la propuesta.

| Bloque | Estado |
|---|---|
| Esquema Supabase (PostgreSQL + pgvector) — `supabase/` | ✅ Implementado |
| Servidor MCP de datos y políticas — `backend/mcp/mcp_supabase.py` | ✅ Implementado |
| Servidor MCP de logística — `backend/mcp/mcp_logistics.py` | ✅ Implementado |
| Agente 1: Triaje y Empatía — `agente1ConMCP/` | ✅ Implementado |
| Agente 2: Evaluador de Políticas — `agente2ConMCP/` | ✅ Implementado |
| Agente 3: Resolución y Logística — `agente3ConMCP/` | ✅ Implementado |
| Flujo completo encadenado (los 3 agentes) — `demo_flujo_completo.py` | ✅ Implementado |
| Backend FastAPI (endpoints de chat y panel admin/HITL) | ⏳ Pendiente |
| Frontend Streamlit (chat cliente + dashboard admin) | ⏳ Pendiente |
| Observabilidad (LangSmith) y despliegue en AWS | ⏳ Pendiente |

## Estructura del repositorio

```
backend/
  db/            # Cliente y settings de Supabase (backend/db/supabase_client.py)
  mcp/           # Servidores MCP: mcp_supabase.py (puerto 8001), mcp_logistics.py (puerto 8002)
agente1ConMCP/   # Agente 1: Triaje y Empatía (extrae order_id y motivo)
agente2ConMCP/   # Agente 2: Evaluador de Políticas (decide valid/invalid/human_review)
agente3ConMCP/   # Agente 3: Resolución y Logística (ejecuta la devolución, HITL >100€)
demo_flujo_completo.py  # Demo de los 3 agentes encadenados (ver sección siguiente)
supabase/        # Migraciones SQL, seed de datos de prueba y diagrama ER
dataset/         # Dataset sintético grande (clientes, pedidos, devoluciones) y
                 # documentación de políticas de devolución para el RAG — ver dataset/README.md
tests/           # Clientes de prueba para los servidores MCP
doc/guia.md      # Arquitectura técnica completa, backlog por épicas y cronograma
defenderMCP.md   # Argumentario de defensa de las decisiones de arquitectura MCP
```

## Configuración del entorno

### 1. Crear entorno virtual

```bash
python3 -m venv .venv
source .venv/Scripts/activate
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt 
```

### 3. Variables de entorno

Copia el archivo de ejemplo y completa tus credenciales:

```bash
cp .env.example .env
```

Edita `.env` con tus valores:

```
SUPABASE_URL=https://<tu-proyecto>.supabase.co
SUPABASE_SERVICE_KEY=<tu-service-role-key>
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

Los servidores MCP utilizan transporte **Streamable HTTP** (el sustituto oficial de
HTTP+SSE, deprecado en la revisión de spec 2025-03-26). En este MVP se ejecutan como dos
procesos Python locales; ver [`defenderMCP.md`](defenderMCP.md) para la justificación de
por qué la arquitectura objetivo los aísla en contenedores independientes.

### Iniciar los servidores

Abre **dos terminales** y ejecuta cada servidor por separado desde la raíz del proyecto:

**Terminal 1** — Supabase (Datos y Políticas) en `http://localhost:8001/mcp`:

```bash
python -m backend.mcp.mcp_supabase
```

**Terminal 2** — Logística en `http://localhost:8002/mcp`:
```bash
python -m backend.mcp.mcp_logistics
```

### Probar la conexión (desde un tercer terminal)

```bash
python tests/test_mcp_supabase.py
python tests/test_mcp_logistics.py
```

### `mcp_supabase.py` — Datos y Políticas (puerto 8001)

| Herramienta | Entradas | Descripción |
|---|---|---|
| `get_order_details` | `order_id` | Consulta detalles del pedido, fechas y productos (Agentes 1 y 2) |
| `get_customer_return_history` | `customer_id` | Historial de devoluciones para detectar abusos (Agente 2) |
| `search_return_policy` | `query`, `category` | Búsqueda semántica RAG con pgvector sobre políticas (Agente 2) |
| `create_return_record` | `order_id`, `customer_id`, `reason`, ... | Inserta solicitud de devolución (Agente 3) |
| `update_return_status` | `return_id`, `status` | Actualiza estado de devolución (Admin / HITL) |

### `mcp_logistics.py` — Logística (puerto 8002)

| Herramienta | Entradas | Descripción |
|---|---|---|
| `generate_shipping_label` | `order_id`, `items` | Genera PDF de etiqueta de transporte con reportlab (Agente 3) |
| `send_customer_notification` | `email`, `message` | Simula envío de correo transaccional con enlace al PDF (Agente 3) |

## Sistema multi-agente (LangChain)

Tres agentes especializados, cada uno en su propio directorio, encadenados en el orden
Triaje → Evaluador → Resolución (doc/guia.md, Épica 2):

| Agente | Directorio | Rol | Tools MCP |
|---|---|---|---|
| 1. Triaje y Empatía | [`agente1ConMCP/`](agente1ConMCP/README.md) | Extrae `order_id` y motivo de forma conversacional | `get_order_details` |
| 2. Evaluador de Políticas | [`agente2ConMCP/`](agente2ConMCP/README.md) | Decide `valid` / `invalid` / `human_review` de forma determinista | `get_order_details`, `search_return_policy`, `get_customer_return_history` |
| 3. Resolución y Logística | [`agente3ConMCP/`](agente3ConMCP/README.md) | Ejecuta la devolución elegible (HITL si el importe supera 100 €) | `create_return_record`, `generate_shipping_label`, `send_customer_notification` |

En los tres, el LLM (`create_agent` de LangChain 1.x) solo llama a las tools y
transcribe lo que devuelven — nunca decide importes, plazos ni umbrales HITL: esas
reglas de negocio están en código Python determinista (ver el README de cada agente).

Cada agente tiene sus propios tests unitarios (`pytest agenteNConMCP/tests`, sin
servidores ni API key reales) y un demo `python -m agenteNConMCP.agente_*`. Para ver los
tres encadenados en un único caso, con los dos primeros contra datos reales de
`supabase/seed.sql`:

```bash
python demo_flujo_completo.py
```
