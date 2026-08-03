# Cómo probar el Agente 3 (Resolución y Logística)

Guía rápida para probar `agente3ConMCP` en local, tanto con tests unitarios (sin
dependencias externas) como con una prueba real contra OpenAI y los dos servidores
MCP.

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

## 1. Tests unitarios (rápido, sin servidores ni API key)

Usan dobles de prueba para el cliente MCP y el agente:

```bash
python -m pytest agente3ConMCP/tests -v
```

Estos tests cubren, entre otras cosas, que el corte HITL (`refund_amount >
HITL_THRESHOLD_EUR`) nunca llega a construir el agente ni a tocar el LLM.

## 2. Prueba real end-to-end (con LLM y MCP de verdad)

Necesitas:
- `OPENAI_API_KEY`, `SUPABASE_URL` y `SUPABASE_SERVICE_KEY` en `.env` (ya
  configuradas en este repo).
- La base de datos sembrada con `supabase/seed.sql` (o el dataset sintético).

⚠️ **A diferencia del Agente 1** (que solo lee datos), el camino de aprobación
automática del Agente 3 **escribe datos de verdad**: crea una fila en
`return_requests`, un PDF en `generated_labels/` y una línea en
`generated_labels/notifications_log.jsonl`. Para probar sin efectos secundarios,
usa un `refund_amount` por encima de `HITL_THRESHOLD_EUR` (sección 2.4).

### 2.1. Levantar los dos servidores MCP

En dos terminales separadas, desde la raíz del repo:

```bash
python -m backend.mcp.mcp_supabase
```
```bash
python -m backend.mcp.mcp_logistics
```

Comprueba que ambos escuchan:

```bash
netstat -ano | grep -E ":8001|:8002" | grep LISTENING
```

### 2.2. Ejecutar el demo incluido (camino aprobado, con escritura real)

En otra terminal:

```bash
python -m agente3ConMCP.agente_resolucion
```

Usa un caso real de `supabase/seed.sql` (pedido `ORD-2026-00163` de Laura
Fernández, devolviendo el libro "Clean Code" por 34.99 €, bajo el umbral HITL) y
debería imprimir algo así:

```python
{'return_id': '...', 'tracking_number': 'RF-XXXXXXXXXX', 'label_path': '.../generated_labels/label_RF-XXXXXXXXXX.pdf', 'requires_human_approval': False, 'refund_amount': 34.99, 'response_to_customer': 'Tu devolución ha sido aprobada...'}
```

Verifica el efecto en disco:

```bash
ls generated_labels/
tail -n 1 generated_labels/notifications_log.jsonl
```

### 2.3. Probar con tu propio caso (camino aprobado)

**Git Bash:**
```bash
python -c "
import asyncio
from agente3ConMCP.agente_resolucion import ResolutionRequest, run_agent_resolucion

request = ResolutionRequest(
    order_id='e1f2a3b4-c5d6-7890-efab-901234567890',
    customer_id='c3d4e5f6-a7b8-9012-cdef-123456789012',
    customer_email='laura.fernandez@email.com',
    customer_name='Laura Fernandez Soto',
    customer_address='Calle Sierpes 15, Sevilla',
    reason='Llego roto',
    reason_category='defective',
    refund_amount=79.99,
    products=[{'order_item_id': 'c5d6e7f8-a9b0-1234-cdef-345678901234', 'quantity': 1, 'condition': 'defective', 'name': 'Batidora de Vaso 1200W'}],
)
output = asyncio.run(run_agent_resolucion(request))
print(output.model_dump())
"
```

**PowerShell:**
```powershell
python -c "import asyncio; from agente3ConMCP.agente_resolucion import ResolutionRequest, run_agent_resolucion; r = ResolutionRequest(order_id='e1f2a3b4-c5d6-7890-efab-901234567890', customer_id='c3d4e5f6-a7b8-9012-cdef-123456789012', customer_email='laura.fernandez@email.com', reason='Llego roto', reason_category='defective', refund_amount=79.99, products=[{'order_item_id': 'c5d6e7f8-a9b0-1234-cdef-345678901234', 'quantity': 1, 'name': 'Batidora de Vaso 1200W'}]); print(asyncio.run(run_agent_resolucion(r)).model_dump())"
```

### 2.4. Probar el corte HITL (sin efectos secundarios, no necesita servidores)

Con un `refund_amount` superior a `HITL_THRESHOLD_EUR` (100 € por defecto) el
agente no llama a ninguna tool ni al LLM, así que ni siquiera necesitas los
servidores MCP levantados:

```bash
python -c "
import asyncio
from agente3ConMCP.agente_resolucion import ResolutionRequest, run_agent_resolucion

request = ResolutionRequest(
    order_id='c9d0e1f2-a3b4-5678-cdef-789012345678',
    customer_id='a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    customer_email='maria.garcia@email.com',
    reason='Llego roto',
    reason_category='defective',
    refund_amount=899.99,
    products=[{'order_item_id': 'f2a3b4c5-d6e7-8901-fabc-012345678901', 'quantity': 1}],
)
output = asyncio.run(run_agent_resolucion(request))
print(output.model_dump())
"
```

Debe devolver `requires_human_approval=True`, `return_id=None`,
`tracking_number=None` y un `response_to_customer` mencionando que se ha
derivado a un administrador.

## Variables de entorno relevantes (`.env`)

| Variable | Por defecto | Descripción |
|---|---|---|
| `MCP_SUPABASE_URL` | `http://localhost:8001/mcp` | URL del servidor MCP de datos y políticas |
| `MCP_LOGISTICS_URL` | `http://localhost:8002/mcp` | URL del servidor MCP de logística |
| `AGENTE3_MODEL` | `openai:gpt-4o-mini` | Modelo LLM, en formato `<provider>:<model>` |
| `HITL_THRESHOLD_EUR` | `100` | Importe (€) a partir del cual se deriva a un administrador |
| `OPENAI_API_KEY` | — | Necesaria para que `create_agent` invoque el modelo |

## Problemas comunes

- **Acentos/€ rotos en la consola**: es la consola de Windows en cp1252, no un
  problema de datos. El demo (`__main__`) ya fuerza UTF-8 con
  `sys.stdout.reconfigure`.
- **`create_return_record` o `generate_shipping_label` fallan / no encuentran el
  pedido o item**: asegúrate de usar IDs reales de `supabase/seed.sql` (`order_id`,
  `customer_id`, `order_item_id`), no inventados.
- **No conecta a los MCP**: comprueba que los dos servidores de la sección 2.1
  siguen levantados (`netstat -ano | grep -E ":8001|:8002"`).
- **Quiero repetir la prueba del demo sin acumular registros**: cambia el
  `order_id`/`products` a otro pedido de la seed, o revisa/limpia manualmente la tabla
  `return_requests` en Supabase.
