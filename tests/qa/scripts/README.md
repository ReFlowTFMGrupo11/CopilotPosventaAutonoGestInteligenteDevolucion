# tests/qa/scripts — qué hace cada script

Scripts de soporte para QA y evaluación del agente de devoluciones. Se
ejecutan siempre desde la **raíz del repo** con `python -m`, no directamente
con `python tests/qa/scripts/archivo.py` (usan imports relativos al paquete
`backend`).

```bash
.venv/Scripts/python.exe -m tests.qa.scripts.<nombre_del_script> [opciones]
```

## Índice de scripts

| Script | Para qué | Requiere LLM/red |
|---|---|---|
| `create_qa_testing_excel.py` | Genera el Excel coloreado de los 24 casos manuales (`qa_manual_testing_cases_v2.xlsx`) a partir del CSV curado. | No |
| `generate_mixed_qa_kit.py` | Genera el kit de pruebas de pedidos **mixtos** (varios productos/categorías en un mismo pedido): un `.xlsx` y un seed `.sql`. | No |
| `evaluate_rag.py` | Evaluador **local** de `policy_evaluator_agent` contra los 480 casos golden (`data/qa/eval_cases.csv`). Calcula precisión/recall/F1 y escribe el informe en `tests/qa/results/*.json` y `*.md`. | Solo si no usas `--dry-run` |
| `migrate_eval_cases_to_langfuse.py` | Sube los 480 casos golden a Langfuse como **Dataset** (`policy-eval-golden-set`), reutilizando el mismo CSV que `evaluate_rag.py`. | No (solo escribe en Langfuse) |
| `run_langfuse_experiment.py` | Ejecuta `policy_evaluator_agent` contra el dataset de Langfuse y sube los resultados como **Experiment Run**, con evaluación automática por item (`label_match`) y agregada (`accuracy`). Es el equivalente a `evaluate_rag.py` pero con historial y comparación entre ejecuciones en la UI de Langfuse en vez de ficheros locales. | Solo si no usas `--dry-run` |

---

## Guía: golden dataset + experimentos en Langfuse

Esto documenta el flujo que estamos siguiendo para pasar de "evaluación
local con ficheros JSON/MD" (`evaluate_rag.py`) a "evaluación en Langfuse"
(dataset + experiment runs comparables en la UI).

### Requisitos previos

- Langfuse corriendo en local (`langfuse_docker/`, ver su README) y accesible
  en `localhost:3000`.
- `.env` de la raíz del repo con `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`,
  `LANGFUSE_HOST` ya rellenos (los usa `langfuse_docker/tracing.py` para el
  tracing normal de la app; los mismos valores sirven aquí).
- Para los pasos con LLM real: `OPENAI_API_KEY` en `.env`.

### Paso 1 — Subir el golden dataset a Langfuse

```bash
# Prueba pequeña primero (gratis, no llama al LLM, solo escribe en Langfuse)
.venv/Scripts/python.exe -m tests.qa.scripts.migrate_eval_cases_to_langfuse --limit 5

# Si todo se ve bien en la UI, sube el resto (o usa --force para re-subir)
.venv/Scripts/python.exe -m tests.qa.scripts.migrate_eval_cases_to_langfuse
```

Qué hace: lee `data/qa/eval_cases.csv` (480 filas) y crea, por cada fila, un
**dataset item** en el dataset `policy-eval-golden-set`:

- `input` → las columnas que necesita el agente (categoría, plazo, importe,
  motivo, historial de devoluciones, etc.)
- `expected_output` → la etiqueta correcta (`valid` / `invalid` /
  `human_review`)
- `metadata` → `case_id`, `category` y `rationale` (el "por qué" de cada
  caso, para poder leerlo directamente en la UI)

Es **idempotente**: si vuelves a ejecutarlo, salta los `case_id` que ya
existen (usa `--force` para subirlos de nuevo igualmente).

**Verificar en la UI**: `localhost:3000` → proyecto → *Datasets* →
`policy-eval-golden-set` → deberías ver los items con sus columnas
Input / Expected Output / Metadata.

> ⚠️ **No uses también el botón "Upload CSV" de la UI de Langfuse sobre
> este mismo dataset.** Ese botón vuelca las columnas del CSV tal cual
> (sin el mapeo a `input`/`expected_output`/`metadata` que hace este
> script), así que mezclarlo con `migrate_eval_cases_to_langfuse.py`
> genera items duplicados con dos formas distintas para el mismo
> `case_id`. Si el número de items del dataset crece por su cuenta entre
> ejecuciones del script (nos pasó: 5 → 121 → 378), es la señal de que
> alguien ha usado "Upload CSV" en paralelo. Comprueba el estado real
> antes de lanzar un Experiment:
> ```bash
> .venv/Scripts/python.exe -c "
> from dotenv import load_dotenv; load_dotenv(override=True)
> from langfuse import Langfuse
> ds = Langfuse().get_dataset('policy-eval-golden-set')
> ids = [it.metadata.get('case_id') for it in ds.items if it.metadata]
> print('total items:', len(ds.items), '| case_ids únicos:', len(set(ids)))
> "
> ```
> Si `total items` no coincide con `case_ids únicos`, hay duplicados que
> limpiar (borra el dataset desde la UI — icono "···" junto a "New item"
> — y vuelve a migrar solo con este script) antes de pasar al paso 2.

### Paso 2 — Correr un Experiment contra el dataset

```bash
# Dry-run: reglas deterministas, SIN LLM, gratis — valida que el
# pipeline (dataset → task → evaluador → Langfuse) funciona de punta a punta
.venv/Scripts/python.exe -m tests.qa.scripts.run_langfuse_experiment --dry-run --limit 5

# Smoke test con el LLM real, pocos casos (consume tokens de OpenAI)
.venv/Scripts/python.exe -m tests.qa.scripts.run_langfuse_experiment --limit 20

# Run completo: los 480 casos con el LLM real (gpt-5-mini) — tiene coste,
# ejecútalo cuando quieras un número serio de accuracy/F1
.venv/Scripts/python.exe -m tests.qa.scripts.run_langfuse_experiment
```

Qué hace, por cada item del dataset:

1. Reconstruye el estado mínimo del agente a partir del `input` guardado
   (misma lógica que `evaluate_rag.py::_build_state` / `_build_mock_policy`,
   sin necesidad de Supabase real).
2. Ejecuta `policy_evaluator_agent` (o, en `--dry-run`, la réplica
   determinista de las reglas de negocio, sin LLM).
3. Compara la etiqueta predicha con `expected_output` mediante el evaluator
   `label_match_evaluator` (1.0 / 0.0 por item, con comentario si falla).
4. Al final, `accuracy_run_evaluator` agrega la accuracy de todo el run.

Todo queda registrado como un **Dataset Run** en Langfuse, vinculado a las
trazas individuales de cada ejecución del agente.

**Verificar en la UI**: *Datasets* → `policy-eval-golden-set` → pestaña
**Experiments** (junto a "Items", arriba de la tabla; en versiones antiguas
de Langfuse se llamaba "Runs") → abre el run más reciente → verás la
accuracy agregada y, entrando en cada item, la traza completa del agente
para ese caso.

> 💡 Si añades más evaluadores de nivel-run (`run_evaluators=[...]`), ten en
> cuenta que `item_results[i].evaluations` son objetos `Evaluation`
> (atributos `.name` / `.value`), **no** dicts — `ev.name`, no
> `ev.get("name")`. Nos pilló en el primer dry-run (`AttributeError:
> 'Evaluation' object has no attribute 'get'`).

### Por qué esto y no solo `evaluate_rag.py`

`evaluate_rag.py` sigue siendo útil para CI (`--dry-run`, sin red, exit code
según accuracy). La diferencia de pasar por Langfuse:

- **Historial comparable**: cada run queda guardado; puedes comparar
  accuracy entre una versión del prompt y otra sin diffear ficheros MD.
- **Traza por caso**: para cada item fallado puedes abrir directamente la
  traza del LLM (qué vio, qué respondió) en vez de solo un `case_id` en un
  JSON.
- **Base para Evaluators/LLM-as-a-Judge**: una vez el dataset vive en
  Langfuse, se pueden añadir evaluadores adicionales (p. ej. calidad del
  `response_to_customer`, no solo la etiqueta) sin tocar estos scripts.
