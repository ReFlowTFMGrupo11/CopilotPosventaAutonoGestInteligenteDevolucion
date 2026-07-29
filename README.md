# CopilotPosventaAutonoGestInteligenteDevolucion
"ReFlow" es un sistema automatizado de devoluciones y soporte de e-commerce impulsado por agentes de IA generativa en Python. Utiliza LangChain, FastAPI y Streamlit, integrando bases de datos PostgreSQL/pgvector mediante MCP para ofrecer una gestión conversacional de solicitudes.

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

Los servidores MCP utilizan transporte **Streamable HTTP** para permitir que múltiples agentes se conecten simultáneamente.

### Iniciar los servidores

Abre **dos terminales** y ejecuta cada servidor por separado:

```bash
cd /path/to/CopilotPosventaAutonoGestInteligenteDevolucion
```
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
python tests/test_mcp_logistics.py
python tests/test_mcp_supabase.py
```


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
