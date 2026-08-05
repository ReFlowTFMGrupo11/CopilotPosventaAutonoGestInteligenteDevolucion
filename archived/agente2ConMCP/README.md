# Agente 2: Evaluador de Políticas

Implementa el **Agente Evaluador de Políticas** descrito en [`doc/guia.md`](../doc/guia.md)
(Épica 2, US 2.3): el auditor del flujo de devoluciones de ReFlow. Recibe el caso que
el Agente 1 (Triaje) ya extrajo del cliente (`order_id`, `reason`, `reason_category`) y
decide si la devolución es **`valid`** (aprobación automática), **`invalid`** (rechazo
automático) o **`human_review`** (revisión manual, HITL), aplicando de forma
determinista la sección 5 de
[`dataset/policies/00_marco_general_devoluciones.md`](../dataset/policies/00_marco_general_devoluciones.md).

Construido con LangChain 1.x (`create_agent`, sobre LangGraph) y
[`langchain-mcp-adapters`](https://github.com/langchain-ai/langchain-mcp-adapters), igual
que [`agente1ConMCP`](../agente1ConMCP) y [`agente3ConMCP`](../agente3ConMCP), conectando
al servidor MCP de Supabase (puerto 8001):

| Tool | Uso |
|---|---|
| `get_order_details` | Pedido, cliente, productos y fecha de entrega |
| `search_return_policy` | Plazo máximo de devolución (`max_return_days`) de la categoría |
| `get_customer_return_history` | Devoluciones aprobadas del cliente (detección de abuso) |

## El LLM transcribe, Python decide

Igual que el Agente 3 recalcula `refund_amount`/`requires_human_approval` en vez de
confiar en lo que "recuerde" el modelo, aquí el LLM **solo** llama a las tres tools y
transcribe los hechos que devuelven (pedido, productos, categoría, fecha de entrega,
plazo de la política, devoluciones aprobadas). **Nunca decide el veredicto**: eso lo
calcula `_classify_return`, una función Python pura, después de la llamada al LLM,
sobrescribiendo siempre `decision`, `eligible`, `refund_amount`, `rationale` y
`response_to_customer` en la salida (`run_agent_evaluacion`).

`_classify_return` es una réplica reducida de `classify_case()` en
[`dataset/generate_dataset.py`](../dataset/generate_dataset.py), el mismo generador que
produjo el "golden dataset" ([`dataset/eval_cases.csv`](../dataset/eval_cases.csv), 480
casos etiquetados) — validado 1:1 contra ese dataset en
[`tests/test_agente_evaluacion.py`](tests/test_agente_evaluacion.py).

### Reglas aplicadas (sección 5 de la política general)

- **`invalid`**: el plazo se ha superado por más de 5 días.
- **`human_review`**: el importe a reembolsar supera 100 € (`HITL_THRESHOLD_EUR`), la
  solicitud cae en zona frontera del plazo, el motivo es sensible
  (`allergic_reaction`, `counterfeit_suspicion`), el cliente tiene más de
  `FREQUENT_RETURNER_THRESHOLD` (3) devoluciones aprobadas, o los productos del pedido
  pertenecen a más de una categoría.
- **`valid`**: ninguna de las anteriores — dentro de plazo e importe ≤ 100 €.

### Simplificación de alcance (documentada)

El Agente 1 no captura hoy el estado físico del artículo (`condition`) ni evidencia
fotográfica, así que esta versión **no** reproduce las ramas de "estado no admitido" ni
"exclusión de higiene/perecederos" de `classify_case` (dependen de esos datos): se asume
el estado más favorable (`unopened`, admitido por las 16 categorías del dataset).
Tampoco distingue devoluciones aprobadas en los últimos 90 días del historial completo,
porque `get_customer_return_history` no filtra por fecha. El resto de reglas sí está
validado contra el golden dataset.

## Alcance

- Solo usa `get_order_details`, `search_return_policy` y `get_customer_return_history`
  (no `create_return_record`, que pertenece al Agente 3).
- No ejecuta ninguna acción (no crea registros ni etiquetas): solo evalúa y devuelve un
  veredicto. Si `decision == "valid"`, la salida (`EvaluationOutput`) trae ya
  `customer_id`, `customer_email`, `customer_name`, `customer_address`, `refund_amount`
  y `products` — los mismos datos que necesita `ResolutionRequest` del Agente 3 para
  ejecutar la devolución.

## Uso

1. Arranca el servidor MCP de Supabase (ver [README.md](../README.md) raíz):

   ```bash
   python -m backend.mcp.mcp_supabase
   ```

2. Asegúrate de tener `OPENAI_API_KEY` en tu `.env`.

3. Ejecuta el demo:

   ```bash
   python -m agente2ConMCP.agente_evaluacion
   ```

### Variables de entorno opcionales

| Variable | Por defecto | Descripción |
|---|---|---|
| `MCP_SUPABASE_URL` | `http://localhost:8001/mcp` | URL del servidor MCP de datos y políticas |
| `AGENTE2_MODEL` | `openai:gpt-4o-mini` | Modelo LLM, en formato `<provider>:<model>` |
| `HITL_THRESHOLD_EUR` | `100` | Importe (€) a partir del cual se deriva a revisión humana |
| `FREQUENT_RETURNER_THRESHOLD` | `3` | Devoluciones aprobadas a partir de las cuales se sospecha abuso |

### Uso programático

```python
from agente2ConMCP.agente_evaluacion import EvaluationRequest, run_agent_evaluacion

request = EvaluationRequest(
    order_id="...",
    reason="Ya no lo quiero",
    reason_category="changed_mind",
)
output = await run_agent_evaluacion(request)

if output.eligible:
    ...  # construir ResolutionRequest para el Agente 3 con output.products, etc.
elif output.decision == "human_review":
    ...  # avisar al panel de Admin/HITL
else:
    ...  # mostrar output.response_to_customer (rechazo)
```

Encadenado con el Agente 1 y el Agente 3, ver
[`demo_flujo_completo.py`](../demo_flujo_completo.py) en la raíz del repo.

## Tests

Tests unitarios con `pytest` + `pytest-asyncio`. No requieren servidor MCP ni API key
real: el cliente MCP y el agente se sustituyen por dobles de prueba. Incluyen una
comprobación 1:1 de `_classify_return` contra las 408 filas de
`dataset/eval_cases.csv` cuya etiqueta no depende de `condition`.

```bash
pip install -r requirements.txt
pytest agente2ConMCP/tests -v
```

Ver también [`readMeTestAgente2.md`](readMeTestAgente2.md) para una guía paso a paso,
incluida la prueba real contra el servidor MCP.
