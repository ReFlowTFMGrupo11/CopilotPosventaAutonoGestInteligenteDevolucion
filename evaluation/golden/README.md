# evaluation/golden — evaluación automática del Agente Evaluador

Kit de evaluación **100% automático, sin UI**: llama a `evaluator_agent()`
directamente en Python contra 480 casos golden y calcula precisión/recall/F1.
Para el kit de pruebas manuales (24 casos, UI de Streamlit), ver
[`../manual/README.md`](../manual/README.md).

Los scripts se ejecutan siempre desde la **raíz del repo** con `python -m`, no
directamente con `python evaluation/golden/scripts/archivo.py` (usan imports
relativos al paquete `backend`).

```bash
.venv/Scripts/python.exe -m evaluation.golden.scripts.<nombre_del_script> [opciones]
```

## Índice de scripts

| Script | Para qué | Requiere LLM/red |
|---|---|---|
| `evaluate_evaluator_agent.py` | Evaluador de `evaluator_agent` contra los 480 casos golden (`eval_cases.csv`, en esta misma carpeta). Calcula precisión/recall/F1 (task success) + tool accuracy + contains + costo + latencia por caso, y manda todo como `score` a LangFuse (por caso y agregado en la traza raíz) — no escribe ningún fichero local; sin LangFuse configurado, solo el exit code (accuracy) y el log de consola son el resultado. Pese a su nombre histórico ("evaluate_rag"), **no** ejecuta ninguna búsqueda vectorial real — mockea `search_return_policy()` a propósito para aislar la calidad de la decisión (LLM + reglas) de la calidad del retrieval. El test real del RAG (chunking/ingesta) vive en `tests/unit/test_ingest_policy_embeddings.py`. | Solo si no usas `--dry-run` |
| `migrate_eval_cases_to_langfuse.py` | Sube los 480 casos golden a Langfuse como **Dataset** (`policy-eval-golden-set`), reutilizando el mismo CSV que `evaluate_evaluator_agent.py`. | No (solo escribe en Langfuse) |
| `run_langfuse_experiment.py` | Ejecuta `evaluator_agent` contra el dataset de Langfuse y sube los resultados como **Experiment Run**, con evaluación automática por item (`label_match`) y agregada (`accuracy`). Es el equivalente a `evaluate_evaluator_agent.py` pero con historial y comparación entre ejecuciones en la UI de Langfuse en vez de ficheros locales. | Solo si no usas `--dry-run` |
| `evaluate_live_rag.py` | Evaluación independiente y opcional del índice RAG real (Supabase/pgvector + OpenAI embeddings), con juicios de evidencia en `live_rag_cases.json`. Puede añadir accuracy del evaluador con LLM real; no mockea ni la búsqueda ni la consulta de políticas. | Solo con `--live` |

### Evaluación del RAG real (fuera de CI)

```bash
python -m evaluation.golden.scripts.evaluate_live_rag                 # valida las evidencias locales sin red
python -m evaluation.golden.scripts.evaluate_live_rag --live          # embeddings + RPC reales
python -m evaluation.golden.scripts.evaluate_live_rag --live --with-llm --limit 5
```

`--live` requiere `OPENAI_API_KEY`, `SUPABASE_URL` y `SUPABASE_SERVICE_KEY` configurados; consume créditos de OpenAI y consulta la BD real. No ejecuta acciones de devolución ni escribe en `llm_usage`; la instrumentación opcional de Langfuse puede registrar trazas. Se debe haber ejecutado la ingesta de políticas: el script rechaza resultados cuyo texto ya no coincida con el corpus local. No incluirlo en CI ni publicar secretos.

La ingesta y la búsqueda comparten `RAG_EMBEDDING_MODEL` en `backend/config.py`;
si se cambia, reingesta el índice antes de evaluar (ver `data/README.md`).

Los cuatro juicios iniciales señalan **un fragmento de evidencia concreto** de los documentos de políticas. `hit@5` indica si ese fragmento aparece entre los cinco resultados; `MRR@5` pondera su posición. Son medidas de **evidencia designada**, no precisión/recall exhaustivos del RAG. Amplía los juicios con revisión humana y categorías diversas antes de extraer conclusiones globales. El modo `--with-llm` compara la etiqueta de enrutamiento con el golden, indica si el LLM marcó elegible cada artículo y muestra la explicación para revisión humana: **no** mide automáticamente fidelidad de las explicaciones. Omite los casos cuyo plazo, condiciones admitidas o recargo difieren de la política activa. La política estructurada le proporciona además el texto completo al LLM; una decisión correcta no demuestra que la recuperación haya causado el acierto. El CSV golden es sintético y pueden persistir otras divergencias de reglas.

---

## Cobertura de métricas de evaluación

De las 6 categorías habituales de una tabla de métricas de evaluación
(task success, tool accuracy, contains, LLM-as-judge, costo, latencia),
`evaluate_evaluator_agent.py` cubre 5 (ver el docstring del propio script
para el detalle exacto de cómo se calcula cada una y sus límites):

| Métrica | ¿Implementada? | Cómo |
|---|---|---|
| Task success | ✅ | accuracy/precision/recall/F1 por clase (la métrica original del script) |
| Tool accuracy | ✅ | ¿llamó a `search_return_policy()` solo cuando el pre-check determinista no resolvía el caso él solo? (derivado de `expected_label`, sin columna nueva en el CSV) |
| Contains | ✅ (acotado) | solo para casos `invalid` por plazo — palabra "plazo" en `eligibility_reason`, texto 100% determinista de `policy_rules.py` |
| Costo | ✅ | tokens/modelo reales capturados mockeando `usage_service.log_llm_usage()` (nunca escribe en la BD real) |
| Latencia | ✅ | tiempo real de cada llamada a `evaluator_agent()`, por caso |
| LLM-as-judge | ❌ (decisión consciente) | las `expected_label` salen de reglas Python deterministas (`classify_case()`), no del juicio de otro LLM — para tener un ground truth reproducible byte a byte, no un segundo modelo cuyo propio error se mezclaría con el del agente evaluado |

Solo aplica con LLM real (`--dry-run` no llama a `evaluator_agent()` ni a
los mocks, así que estas 5 métricas quedan a `None`/0 en ese modo — task
success sigue disponible siempre, vía `_deterministic_label()`).

## Guía: golden dataset + experimentos en Langfuse

Esto documenta el flujo que estamos siguiendo para pasar de "evaluación
local, un run suelto sin historial" (`evaluate_evaluator_agent.py`, que ya
manda sus métricas a LangFuse como scores pero sin comparación entre
ejecuciones) a "evaluación en Langfuse Datasets/Experiments" (dataset +
experiment runs comparables en la UI, con historial entre versiones).

### Requisitos previos

- `.env` de la raíz del repo con `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`
  de tu proyecto en [Langfuse Cloud](https://cloud.langfuse.com) (los mismos
  valores que usa `backend/services/observability.py` para el tracing normal
  de la app).
- Para los pasos con LLM real: `OPENAI_API_KEY` en `.env`.

### Paso 1 — Subir el golden dataset a Langfuse

```bash
# Prueba pequeña primero (gratis, no llama al LLM, solo escribe en Langfuse)
.venv/Scripts/python.exe -m evaluation.golden.scripts.migrate_eval_cases_to_langfuse --limit 5

# Si todo se ve bien en la UI, sube el resto (o usa --force para re-subir)
.venv/Scripts/python.exe -m evaluation.golden.scripts.migrate_eval_cases_to_langfuse
```

Qué hace: lee `eval_cases.csv` (480 filas, en esta misma carpeta) y crea, por
cada fila, un **dataset item** en el dataset `policy-eval-golden-set`:

- `input` → las columnas que necesita el agente (categoría, plazo, importe,
  motivo, historial de devoluciones, etc.)
- `expected_output` → la etiqueta correcta (`valid` / `invalid` /
  `human_review`)
- `metadata` → `case_id`, `category` y `rationale` (el "por qué" de cada
  caso, para poder leerlo directamente en la UI)

Es **idempotente**: si vuelves a ejecutarlo, salta los `case_id` que ya
existen (usa `--force` para subirlos de nuevo igualmente).

**Verificar en la UI**: [cloud.langfuse.com](https://cloud.langfuse.com) → proyecto → *Datasets* →
`policy-eval-golden-set` → deberías ver los items con sus columnas
Input / Expected Output / Metadata.

> ⚠️ **No uses también el botón "Upload CSV" de la UI de Langfuse sobre
> este mismo dataset.** Ese botón vuelca las columnas del CSV tal cual
> (sin el mapeo a `input`/`expected_output`/`metadata` que hace este
> script), así que mezclarlo con `migrate_eval_cases_to_langfuse.py`
> genera items duplicados con dos formas distintas para el mismo
> `case_id`. Si el número de items del dataset crece por su cuenta entre
> ejecuciones del script (nos pasó: 5 → 121 → 378, y también una vez con
> 480 items de un CSV desactualizado que no tenía `condition`/
> `allowed_conditions` — ver git history de este fichero), es la señal de
> que algo se subió sin pasar por este script. Comprueba el estado real
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
.venv/Scripts/python.exe -m evaluation.golden.scripts.run_langfuse_experiment --dry-run --limit 5

# Smoke test con el LLM real, pocos casos (consume tokens de OpenAI)
.venv/Scripts/python.exe -m evaluation.golden.scripts.run_langfuse_experiment --limit 20

# Run completo: los 480 casos con el LLM real (gpt-5-mini) — tiene coste,
# ejecútalo cuando quieras un número serio de accuracy/F1
.venv/Scripts/python.exe -m evaluation.golden.scripts.run_langfuse_experiment
```

Qué hace, por cada item del dataset:

1. Reconstruye el estado mínimo del agente a partir del `input` guardado
   (misma lógica que `evaluate_evaluator_agent.py::_build_state` /
   `_build_mock_policy`, sin necesidad de Supabase real).
2. Ejecuta `evaluator_agent` (o, en `--dry-run`, la réplica
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

### Por qué esto y no solo `evaluate_evaluator_agent.py`

`evaluate_evaluator_agent.py` sigue siendo útil para CI (`--dry-run`, sin red,
exit code según accuracy). La diferencia de pasar por Langfuse:

- **Historial comparable**: cada run queda guardado; puedes comparar
  accuracy entre una versión del prompt y otra sin diffear ficheros MD.
- **Traza por caso**: para cada item fallado puedes abrir directamente la
  traza del LLM (qué vio, qué respondió) en vez de solo un `case_id` en un
  JSON.
- **Base para Evaluators/LLM-as-a-Judge**: una vez el dataset vive en
  Langfuse, se pueden añadir evaluadores adicionales (p. ej. calidad del
  `response_to_customer`, no solo la etiqueta) sin tocar estos scripts.
