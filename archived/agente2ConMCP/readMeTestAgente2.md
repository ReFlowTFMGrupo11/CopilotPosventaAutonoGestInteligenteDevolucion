# Cómo probar el Agente 2 (Evaluador de Políticas)

Guía rápida para probar `agente2ConMCP` en local, tanto con tests unitarios (sin
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

## 1. Tests unitarios (rápido, sin servidor ni API key)

Usan dobles de prueba para el cliente MCP y el agente, así que no necesitan nada más
levantado. Incluyen una comprobación de `_classify_return` contra el golden dataset
(`dataset/eval_cases.csv`):

```bash
python -m pytest agente2ConMCP/tests -v
```

## 2. Prueba real end-to-end (con LLM y MCP de verdad)

Necesitas:
- `OPENAI_API_KEY`, `SUPABASE_URL` y `SUPABASE_SERVICE_KEY` en `.env`.
- La base de datos sembrada con `supabase/seed.sql` (solo lectura: el Agente 2 no
  escribe nada).

### 2.1. Levantar el servidor MCP de Supabase

```bash
python -m backend.mcp.mcp_supabase
```

### 2.2. Ejecutar el demo incluido

```bash
python -m agente2ConMCP.agente_evaluacion
```

Usa el pedido `ORD-2026-00163` de Laura Fernández (`supabase/seed.sql`), que tiene dos
productos de categorías distintas (una batidora `home_appliances` y un libro `books`).
Como `get_order_details` devuelve todos los productos del pedido y el Agente 2 deriva a
revisión humana cualquier devolución con productos de más de una categoría (ver
`_apply_deterministic_decision` en `agente_evaluacion.py`), el resultado esperado es
`decision='human_review'` con ese motivo, **con independencia de la fecha en la que
ejecutes el demo**. Para ver el corte por plazo superado (`decision='invalid'`) o por
importe (`decision='human_review'` por importe), usa los casos simulados de
[`demo_flujo_completo.py`](../demo_flujo_completo.py) o la sección 2.3 de abajo.

### 2.3. Probar con tu propio caso

**Git Bash:**
```bash
python -c "
import asyncio
from agente2ConMCP.agente_evaluacion import EvaluationRequest, run_agent_evaluacion

request = EvaluationRequest(
    order_id='c9d0e1f2-a3b4-5678-cdef-789012345678',
    reason='Ya no lo quiero, cambie de opinion',
    reason_category='changed_mind',
)
output = asyncio.run(run_agent_evaluacion(request))
print(output.model_dump())
"
```

**PowerShell:**
```powershell
python -c "import asyncio; from agente2ConMCP.agente_evaluacion import EvaluationRequest, run_agent_evaluacion; r = EvaluationRequest(order_id='c9d0e1f2-a3b4-5678-cdef-789012345678', reason='Ya no lo quiero, cambie de opinion', reason_category='changed_mind'); print(asyncio.run(run_agent_evaluacion(r)).model_dump())"
```

Este pedido (`ORD-2026-00142` de María García, portátil de 899,99 €) debería devolver
`decision='human_review'` por dos motivos independientes: el importe supera los 100 €
del umbral HITL, y (dependiendo de cuándo lo ejecutes) puede caer además en zona
frontera del plazo de 15 días de la categoría `electronics`.

### 2.4. Probar el flujo completo (Agente 1 → Agente 2 → Agente 3)

Ver [`demo_flujo_completo.py`](../demo_flujo_completo.py) en la raíz del repo: encadena
los tres agentes, incluido un caso simulado (sin tocar la base de datos real) que
demuestra el camino `valid` hasta la creación de la etiqueta de transporte.

## Variables de entorno relevantes (`.env`)

| Variable | Por defecto | Descripción |
|---|---|---|
| `MCP_SUPABASE_URL` | `http://localhost:8001/mcp` | URL del servidor MCP de datos y políticas |
| `AGENTE2_MODEL` | `openai:gpt-4o-mini` | Modelo LLM, en formato `<provider>:<model>` |
| `HITL_THRESHOLD_EUR` | `100` | Importe (€) a partir del cual se deriva a revisión humana |
| `FREQUENT_RETURNER_THRESHOLD` | `3` | Devoluciones aprobadas a partir de las cuales se sospecha abuso |
| `OPENAI_API_KEY` | — | Necesaria para que `create_agent` invoque el modelo |

## Problemas comunes

- **Acentos rotos en la consola**: es la consola de Windows en cp1252, no un problema
  de datos. El demo (`__main__`) ya fuerza UTF-8 con `sys.stdout.reconfigure`.
- **`decision` distinto al esperado en la sección 2.2/2.3**: revisa cuántos días han
  pasado desde `delivered_at` en el momento en que ejecutas el demo — los ejemplos de
  `supabase/seed.sql` tienen fechas de entrega fijas de 2026, así que el resultado
  determinista cambia con el paso del tiempo real (esto es esperado, no un bug).
- **No conecta al MCP**: comprueba que el servidor de la sección 2.1 sigue levantado
  (`netstat -ano | grep ":8001"`).
