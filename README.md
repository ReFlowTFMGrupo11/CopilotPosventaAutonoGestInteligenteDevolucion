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
