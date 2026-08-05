# Agente 1: Triaje y Empatía

Implementa el **Agente de Triaje y Empatía** descrito en [`doc/guia.md`](../doc/guia.md)
(Épica 2, US 2.2): el primer punto de contacto del flujo de devoluciones de ReFlow.
Atiende al cliente, entiende el motivo de su insatisfacción y extrae el `order_id` de
forma conversacional, verificándolo mediante la tool MCP `get_order_details` del
servidor `backend/mcp/mcp_supabase.py` (puerto 8001).

Construido con LangChain 1.x (`create_agent`, sobre LangGraph) y
[`langchain-mcp-adapters`](https://github.com/langchain-ai/langchain-mcp-adapters) para
consumir la tool vía MCP en lugar de reimplementarla.

## Alcance

- Sólo usa la tool `get_order_details` (no `create_return_record`,
  `update_return_status`, etc., que pertenecen a los Agentes 2 y 3).
- No decide elegibilidad de la devolución ni consulta políticas: eso es
  responsabilidad del Agente Evaluador.
- Devuelve una salida estructurada (`TriageOutput`) lista para pasar al siguiente
  agente de la cadena: `order_id`, `reason`, `reason_category`,
  `ready_for_evaluation` y `response_to_customer`.

## Uso

1. Arranca el servidor MCP de Supabase (ver [README.md](../README.md) raíz):

   ```bash
   python -m backend.mcp.mcp_supabase
   ```

2. Asegúrate de tener `OPENAI_API_KEY` en tu `.env` (usado por
   `langchain-openai` a través de `create_agent(model="openai:...")`).

3. Ejecuta el demo:

   ```bash
   python -m agente1ConMCP.agente_triaje
   ```

### Variables de entorno opcionales

| Variable | Por defecto | Descripción |
|---|---|---|
| `MCP_SUPABASE_URL` | `http://localhost:8001/mcp` | URL del servidor MCP de datos y políticas |
| `AGENTE1_MODEL` | `openai:gpt-4o-mini` | Modelo LLM, en formato `<provider>:<model>` |

### Uso programático

```python
from agente1ConMCP.agente_triaje import run_agent_triaje

output = await run_agent_triaje("Hola, quiero devolver mi pedido a1b2c3d4-..., llegó roto")
print(output.ready_for_evaluation, output.order_id, output.reason_category)
```

Para mantener la conversación entre turnos, construye el agente una vez y reutilízalo:

```python
from agente1ConMCP.agente_triaje import build_triage_agent, run_agent_triaje

agent = await build_triage_agent()
turno1 = await run_agent_triaje("Hola", agent=agent)
turno2 = await run_agent_triaje("Mi pedido es a1b2c3d4-...", agent=agent)
```

## Tests

Tests unitarios con `pytest` + `pytest-asyncio`. No requieren servidor MCP ni API key
real: el cliente MCP y el agente se sustituyen por dobles de prueba.

```bash
pip install -r requirements.txt
pytest agente1ConMCP/tests -v
```
