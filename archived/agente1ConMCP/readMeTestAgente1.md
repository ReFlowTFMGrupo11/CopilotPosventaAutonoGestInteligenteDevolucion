# Cómo probar el Agente 1 (Triaje y Empatía)

Guía rápida para probar `agente1ConMCP` en local, tanto con tests unitarios (sin
dependencias externas) como con una prueba real contra OpenAI y el servidor MCP.

## 0. Activar el entorno virtual

**Git Bash:**
```bash
source .venv/Scripts/activate
```

**PowerShell:**
```powershell
.venv\Scripts\Activate.ps1
```

Con el entorno activado puedes usar `python` directamente; si no lo activas, usa
`.venv/Scripts/python` (Git Bash) o `.venv\Scripts\python` (PowerShell) en los
comandos de abajo.

## 1. Tests unitarios (rápido, sin servidor ni API key)

Usan dobles de prueba para el cliente MCP y el agente, así que no necesitan nada
más levantado:

```bash
python -m pytest agente1ConMCP/tests -v
```

## 2. Prueba real end-to-end (con LLM y MCP de verdad)

Necesitas:
- `OPENAI_API_KEY` y las credenciales de `SUPABASE_URL` / `SUPABASE_SERVICE_KEY`
  en `.env` (ya configuradas en este repo).
- La base de datos sembrada con `supabase/seed.sql` (o el dataset sintético)
  para que exista un pedido real que consultar.

### 2.1. Levantar el servidor MCP de Supabase

En una terminal aparte, desde la raíz del repo:

```bash
python -m backend.mcp.mcp_supabase
```

Debe quedar escuchando en `http://localhost:8001/mcp`. Compruébalo con:

```bash
netstat -ano | grep ":8001" | grep LISTENING
```

### 2.2. Ejecutar el demo incluido

En otra terminal:

```bash
python -m agente1ConMCP.agente_triaje
```

Manda un mensaje de ejemplo usando un `order_id` real de `supabase/seed.sql`
(`c9d0e1f2-a3b4-5678-cdef-789012345678`, pedido `ORD-2026-00142` de María
García) y debería imprimir algo así:

```python
{'order_id': 'c9d0e1f2-a3b4-5678-cdef-789012345678', 'reason': 'llego roto', 'reason_category': 'defective', 'ready_for_evaluation': True, 'response_to_customer': 'Hola María, lamento mucho...'}
```

### 2.3. Probar con tu propio mensaje

**Git Bash:**
```bash
python -c "
import asyncio
from agente1ConMCP.agente_triaje import run_agent_triaje

output = asyncio.run(run_agent_triaje('Hola, quiero devolver el pedido c9d0e1f2-a3b4-5678-cdef-789012345678, me llegó defectuoso'))
print(output.model_dump())
"
```

**PowerShell:**
```powershell
python -c "import asyncio; from agente1ConMCP.agente_triaje import run_agent_triaje; print(asyncio.run(run_agent_triaje('Hola, quiero devolver el pedido c9d0e1f2-a3b4-5678-cdef-789012345678, me llegó defectuoso')).model_dump())"
```

Prueba también sin `order_id` (p. ej. `"Hola, quiero devolver un producto pero no
me acuerdo del pedido"`) para comprobar que el agente lo pide en vez de
inventarlo: debe devolver `order_id=None` y `ready_for_evaluation=False`.

### 2.4. Mantener una conversación de varios turnos

Reutiliza el mismo agente entre turnos para no reconectar al MCP cada vez:

```python
import asyncio
from agente1ConMCP.agente_triaje import build_triage_agent, run_agent_triaje

async def main():
    agent = await build_triage_agent()
    turno1 = await run_agent_triaje("Hola, quiero devolver un pedido", agent=agent)
    print(turno1.model_dump())
    turno2 = await run_agent_triaje(
        "Es el c9d0e1f2-a3b4-5678-cdef-789012345678, llegó roto", agent=agent
    )
    print(turno2.model_dump())

asyncio.run(main())
```

## Variables de entorno relevantes (`.env`)

| Variable | Por defecto | Descripción |
|---|---|---|
| `MCP_SUPABASE_URL` | `http://localhost:8001/mcp` | URL del servidor MCP de datos y políticas |
| `AGENTE1_MODEL` | `openai:gpt-4o-mini` | Modelo LLM, en formato `<provider>:<model>` |
| `OPENAI_API_KEY` | — | Necesaria para que `create_agent` invoque el modelo |

## Problemas comunes

- **Acentos rotos en la consola** (`Mar�a` en vez de `María`): es la consola de
  Windows en cp1252, no un problema de datos. El demo (`__main__`) ya fuerza
  UTF-8 con `sys.stdout.reconfigure`; si lo ves en tus propios `python -c`,
  añade la misma línea o usa Windows Terminal.
- **`get_order_details` falla / no encuentra el pedido**: asegúrate de usar un
  `order_id` real (no un `customer_id`). Los IDs de ejemplo de
  `supabase/seed.sql` están en la sección 2.2.
- **No conecta al MCP**: comprueba que el servidor de la sección 2.1 sigue
  levantado (`netstat -ano | grep ":8001"`).
