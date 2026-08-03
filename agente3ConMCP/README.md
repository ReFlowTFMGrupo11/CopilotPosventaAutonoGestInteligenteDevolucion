# Agente 3: Resolución y Logística

Implementa el **Agente de Resolución** descrito en [`doc/guia.md`](../doc/guia.md)
(Épica 2, US 2.4 y US 2.5): el último eslabón del flujo de devoluciones de ReFlow.
Recibe un caso ya validado como elegible por el Agente 2 (Evaluador) y, si el importe
no supera el umbral de aprobación automática, lo ejecuta: registra la devolución en
Supabase, genera la etiqueta de transporte y notifica al cliente.

Construido con LangChain 1.x (`create_agent`, sobre LangGraph) y
[`langchain-mcp-adapters`](https://github.com/langchain-ai/langchain-mcp-adapters),
igual que [`agente1ConMCP`](../agente1ConMCP), pero conectando a **dos** servidores
MCP a la vez:

| Tool | Servidor MCP | Puerto |
|---|---|---|
| `create_return_record` | `backend/mcp/mcp_supabase.py` | 8001 |
| `generate_shipping_label` | `backend/mcp/mcp_logistics.py` | 8002 |
| `send_customer_notification` | `backend/mcp/mcp_logistics.py` | 8002 |

## Regla Human-in-the-Loop (HITL)

Si `refund_amount > HITL_THRESHOLD_EUR` (100 € por defecto), **no se invoca ni al LLM
ni a ninguna tool**: el caso se marca con `requires_human_approval=True` y se devuelve
un mensaje derivando la revisión a un administrador. Esta comprobación está en código
Python (`_needs_human_approval`), no delegada al LLM, porque es una regla de negocio
sobre dinero y no conviene depender de que el modelo la respete en todas las
formulaciones posibles del caso.

Cuando el importe sí entra dentro del límite, `run_agent_resolucion` también
sobrescribe `refund_amount` y `requires_human_approval` en la salida del LLM con los
valores reales de la petición, en vez de confiar en lo que "recuerde" el modelo.

## Alcance

- Asume que el pedido ya fue verificado (Agente 1) y la devolución ya fue evaluada
  como elegible (Agente 2): no vuelve a comprobar plazos ni políticas.
- Solo usa `create_return_record`, `generate_shipping_label` y
  `send_customer_notification` (no `get_order_details`, `search_return_policy` ni
  `update_return_status`, que pertenecen a otros agentes o al panel de Admin/HITL).
- Devuelve una salida estructurada (`ResolutionOutput`) con `return_id`,
  `tracking_number`, `label_path`, `requires_human_approval`, `refund_amount` y
  `response_to_customer`.

## Uso

1. Arranca los dos servidores MCP (ver [README.md](../README.md) raíz):

   ```bash
   python -m backend.mcp.mcp_supabase
   python -m backend.mcp.mcp_logistics
   ```

2. Asegúrate de tener `OPENAI_API_KEY` en tu `.env`.

3. Ejecuta el demo:

   ```bash
   python -m agente3ConMCP.agente_resolucion
   ```

   ⚠️ A diferencia del demo de solo lectura del Agente 1, este demo usa un importe por
   debajo del umbral HITL, así que **ejecuta las tools de verdad**: crea un registro
   real en `return_requests` (Supabase), un PDF en `generated_labels/` y una línea en
   `generated_labels/notifications_log.jsonl`.

### Variables de entorno opcionales

| Variable | Por defecto | Descripción |
|---|---|---|
| `MCP_SUPABASE_URL` | `http://localhost:8001/mcp` | URL del servidor MCP de datos y políticas |
| `MCP_LOGISTICS_URL` | `http://localhost:8002/mcp` | URL del servidor MCP de logística |
| `AGENTE3_MODEL` | `openai:gpt-4o-mini` | Modelo LLM, en formato `<provider>:<model>` |
| `HITL_THRESHOLD_EUR` | `100` | Importe (€) a partir del cual se deriva a un administrador |

### Uso programático

```python
from agente3ConMCP.agente_resolucion import ResolutionRequest, run_agent_resolucion

request = ResolutionRequest(
    order_id="...",
    customer_id="...",
    customer_email="cliente@email.com",
    reason="Llegó roto",
    reason_category="defective",
    refund_amount=34.99,
    products=[{"order_item_id": "...", "quantity": 1, "condition": "unopened", "name": "..."}],
)
output = await run_agent_resolucion(request)

if output.requires_human_approval:
    ...  # avisar al panel de Admin/HITL
else:
    ...  # mostrar output.tracking_number / output.label_path al cliente
```

## Tests

Tests unitarios con `pytest` + `pytest-asyncio`. No requieren servidores MCP ni API
key real: el cliente MCP y el agente se sustituyen por dobles de prueba.

```bash
pip install -r requirements.txt
pytest agente3ConMCP/tests -v
```

Ver también [`readMeTestAgente3.md`](readMeTestAgente3.md) para una guía paso a paso
de cómo probarlo, incluida la prueba real contra los servidores MCP.
