# Defensa de los Datos: Dataset Sintético y Golden Dataset de Evaluación

Este documento recoge los argumentos para defender, en la memoria/presentación del TFM,
el pipeline de datos de ReFlow: cómo se genera un dataset sintético realista para poblar
la aplicación, y cómo ese mismo generador produce un **golden dataset** (480 casos con la
decisión correcta ya calculada) para medir automáticamente si el Agente Evaluador decide
bien, sin depender de revisión humana caso por caso.

Cubre dos piezas relacionadas pero distintas, que conviene no confundir en la defensa:

- **Generación de datos** (`data/generate_dataset.py` → `supabase/seed_synthetic.sql`):
  un mundo ficticio y coherente (clientes, productos, pedidos) para poblar la app.
- **Evaluación / golden dataset** (`tests/qa/golden/eval_cases.csv` + los scripts de
  `tests/qa/golden/scripts/`): un examen con las respuestas correctas ya puestas, y las
  herramientas que se lo toman al agente real.

---

## 1. ¿Por qué generar datos sintéticos y no usar un dataset público o datos reales?

El profesor del TFM señaló explícitamente la necesidad de un dataset de prueba:

> "También concretaría pronto el dataset de prueba: pedidos, productos, políticas de
> devolución, importes, estados logísticos y casos límite. Sería interesante incluir
> ejemplos donde la devolución sea claramente válida, claramente no válida y casos
> ambiguos que activen el Human-in-the-Loop."

### Alternativas descartadas

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| MCP server `awslabs.syntheticdata-mcp-server` (AWS Labs) | Imposible de estabilizar en Windows; además, la propia documentación de AWS Labs lo marca como **deprecado** ("la funcionalidad principal ya la puede cubrir un asistente de IA moderno") |
| Datasets de Kaggle sobre devoluciones e-commerce | Tabulares para Machine Learning: solo 5 categorías, 4 motivos, sin ningún texto de política — más limitados que lo que ya se necesitaba |
| Datos reales de producción | No existen (no hay tienda real detrás); y aunque existieran, no permitirían controlar la distribución de casos límite que exige la evaluación (¿cuántos "claramente inválidos" hay de verdad en producción?) |

**Decisión**: generarlo con un script Python determinista y reproducible
(`data/generate_dataset.py`), sin llamadas a APIs externas ni dependencias más allá de la
librería estándar. Esto da control total sobre la distribución de casos — algo que ningún
dataset externo, real o público, puede garantizar.

---

## 2. Arquitectura del pipeline

```
data/generate_dataset.py   (seed fijo: 20260730 — reproducible)
        │
        │  UNA sola ejecución, para que todo case entre sí:
        │  clientes ↔ pedidos ↔ artículos ↔ devoluciones ↔ conversaciones
        │
        ├──► supabase/seed_synthetic.sql     320 clientes, 196 productos,
        │                                    1100 pedidos, 480 devoluciones,
        │                                    140 conversaciones de chat
        │                                    → para poblar Supabase (BD real)
        │
        ├──► tests/qa/golden/eval_cases.csv          480 filas: datos de entrada +
        │                                    expected_label (valid/invalid/
        │                                    human_review) YA CALCULADO
        │                                    → el "examen con respuestas"
        │
        └──► tests/qa/golden/GENERATION_STATS.md     resumen legible (recuentos,
                                              distribución) — solo para que
                                              un humano compruebe de un
                                              vistazo que el dataset generado
                                              tiene sentido; ningún script
                                              lo consume
```

A partir de `eval_cases.csv`, tres scripts en `tests/qa/golden/scripts/` "toman el examen":

```
eval_cases.csv
        │
        ├──► evaluate_evaluator_agent.py                  local: reconstruye el estado,
        │                                      llama a evaluator_agent(),
        │                                      compara vs expected_label,
        │                                      escribe un informe JSON/MD
        │
        └──► migrate_eval_cases_to_langfuse.py   sube las 480 filas como
                       │                          Dataset de Langfuse
                       ▼
             run_langfuse_experiment.py        reutiliza la MISMA lógica
                                                que evaluate_evaluator_agent.py, pero
                                                registra cada run en
                                                Langfuse (historial
                                                comparable entre ejecuciones,
                                                traza por caso)
```

---

## 3. El golden dataset: etiquetas calculadas sin IA

Un detalle que se cuestiona a menudo en la defensa: **¿quién decide que la "respuesta
correcta" de cada caso es correcta?** No es un LLM, ni una opinión subjetiva — es una
función Python pura, `classify_case()` (`data/generate_dataset.py:807`), que aplica
**exactamente las reglas de la sección 5 del marco general de políticas**
(`data/rag/policies/00_marco_general_devoluciones.md`):

| Regla | Resultado |
|-------|-----------|
| Plazo superado > 5 días de margen | `invalid` |
| Categoría con exclusión legal de higiene (Art. 103 TRLGDCU) + motivo de "cambio de opinión" | `invalid` |
| Condición del artículo no admitida para esa categoría, y motivo no imputable a Mercadia | `invalid` |
| Importe > 100 € | `human_review` |
| Zona frontera del plazo (± 5 días del límite) | `human_review` |
| Motivo sensible (`allergic_reaction`, `counterfeit_suspicion`) | `human_review` |
| Cliente con >5 devoluciones aprobadas (posible abuso) | `human_review` |
| Nada de lo anterior | `valid` |

Que sea código puro, no un LLM, es la clave de por qué el golden dataset es fiable: la
"respuesta correcta" de cada caso es **objetivamente verificable leyendo el código**, no
una opinión de otro modelo que también podría equivocarse.

### Distribución obtenida (última generación)

| Etiqueta | Casos | % |
|----------|-------|---|
| `valid` | 131 | 27.3% |
| `invalid` | 135 | 28.1% |
| `human_review` | 214 | 44.6% |

Que casi la mitad de los casos caiga en `human_review` es **deliberado, no un defecto**:
con un umbral HITL fijo de 100 € y categorías de precio medio alto (electrónica, muebles,
electrodomésticos), una parte importante de solicitudes legítimas requiere igualmente
revisión humana — que es exactamente el comportamiento que el TFM quiere demostrar, no
solo "el agente aprueba o rechaza automáticamente casi todo".

---

## 4. Dos caminos de evaluación: local vs Langfuse

| | `evaluate_evaluator_agent.py` | `run_langfuse_experiment.py` |
|---|---|---|
| Dónde queda el resultado | JSON/MD local en `tests/qa/golden/results/` | Dataset Run en Langfuse (UI) |
| Historial entre ejecuciones | No — cada informe se sustituye | Sí — comparable entre versiones de prompt/modelo |
| Traza del LLM por caso fallado | No | Sí — abre la traza completa desde la UI |
| Requiere infraestructura externa | No | Sí — Langfuse corriendo (local o cloud) |
| Lógica de evaluación | Propia (`_build_state`, `_build_mock_policy`) | **Reutiliza la misma** de `evaluate_evaluator_agent.py` (importada directamente) |

No son dos implementaciones paralelas que puedan desincronizarse: `run_langfuse_experiment.py`
importa literalmente `_build_state`/`_build_mock_policy`/`_result_to_label` desde
`evaluate_evaluator_agent.py` — un solo punto de verdad para "cómo se reconstruye el caso", con dos
formas distintas de registrar el resultado.

---

## 5. Un problema real que se encontró y se corrigió: `condition` no se exportaba

Esta sección merece estar en la defensa porque demuestra auditoría real del propio
trabajo, no solo construcción de features.

### El problema

`classify_case()` usa `condition` (¿el artículo está sin abrir? ¿usado? ¿le faltan
piezas?) como ingrediente para calcular `expected_label` — pero el CSV exportado
**no incluía esa columna**. `evaluate_evaluator_agent.py` no podía reconstruir el caso real: en su
lugar, lo **adivinaba** con una regla de solo 2 valores:

```python
# Antes del fix — evaluate_evaluator_agent.py
"condition": "defective" if row["reason_category"] == "defective" else "unopened"
```

Esto significa que, durante un tiempo, el % de accuracy que reportaba `evaluate_evaluator_agent.py`
no medía de forma fiable si el agente decidía bien — medía, en parte, si coincidía por
casualidad con una versión simplificada e inventada del caso.

### El fix

1. `generate_dataset.py` exporta ahora `condition` y `allowed_conditions` (columnas
   nuevas en `eval_cases.csv`), con los mismos valores que usó `classify_case()`.
2. `evaluate_evaluator_agent.py::_build_state` usa la columna real en vez de adivinarla.
3. `_build_mock_policy` recibe `allowed_conditions` específico de cada categoría, en vez
   de una lista fija igual para las 16.
4. `migrate_eval_cases_to_langfuse.py` sube también estas dos columnas (antes se perdían
   al subir el dataset a Langfuse).

Verificado con casos reales tras el fix: `condition` ya no es siempre `unopened`/`defective`
— aparecen `opened_unused`, `wrong_item`, `missing_parts`, etc., reflejando la variedad real
del dataset generado.

---

## 6. Otro gap real, encontrado después: `missing_evidence` existe en el generador, no en el agente

Mismo espíritu que §5 (auditoría real del propio trabajo), encontrado investigando por qué
la accuracy de `evaluate_evaluator_agent.py` no llega al 100% ni siquiera en `--dry-run`
(reglas deterministas puras, sin LLM).

### El problema

`classify_case()` (`data/generate_dataset.py:2270`) incluye un factor adicional que fuerza
`human_review`:

```python
missing_evidence = reason in STORE_FAULT_REASONS and rng.random() < 0.08
```

Es decir: si el motivo es imputable a la tienda (`defective`, `wrong_item_shipped`,
`damaged_in_transit`, `missing_parts`, `not_as_described`) y, con un 8% de probabilidad,
"falta evidencia fotográfica exigible para el motivo declarado" — el caso pasa a revisión
humana. Tiene sentido de negocio: una reclamación de "llegó roto" sin foto es más fácil de
abusar que una con foto.

**El problema**: esta variable **no se exporta a `eval_cases.csv`** (no es una de sus 14
columnas) y **no existe ningún equivalente en el agente real** — ni un campo en
`ReturnState`, ni un parámetro en `deterministic_check()` (`policy_rules.py`), ni una forma
de subir una foto desde el chat de Streamlit. Contando contra las 480 filas:

| | Casos | % |
|---|---|---|
| Con `missing_evidence` como factor (solo o combinado con otro) | 16 | 3.3% |
| **Únicamente** por `missing_evidence` (ningún otro factor ya fuerza `human_review`) | 8 | **1.7%** |

Ese 1.7% es un **techo de accuracy estructural**: el agente real no puede acertar esos 8
casos aunque razone perfectamente, porque el dataset le exige adivinar información
(¿hay foto o no?) que nunca estuvo disponible ni pudo estarlo.

### Por qué se documenta y no se implementa

Se valoró cerrar el gap implementando subida de fotos de verdad (Streamlit
`file_uploader` + Supabase Storage + nueva columna/migración + nuevo parámetro en
`deterministic_check()` + nueva regla `rule_missing_evidence` + ajuste del prompt de
`triage.py` + tests). Se descartó por desproporcionado:

- Cierra solo 1.7 puntos de accuracy sobre 480 casos.
- No es central a la tesis (el foco es la orquestación multi-agente + HITL por importe,
  no la verificación de evidencia fotográfica).
- Añade superficie nueva (subida de ficheros, storage, una regla de negocio más) a pocas
  semanas de la defensa, con el riesgo de introducir bugs nuevos a cambio de un beneficio
  marginal en una métrica (el golden dataset) que además ya tiene otras limitaciones
  conocidas (mockea el RAG real, ver [`defenderRAG.md` §4.1](defenderRAG.md)).

**Decisión**: se documenta como limitación consciente y acotada, no como deuda técnica
pendiente. El techo real de `evaluate_evaluator_agent.py --dry-run` es ~98.3%, no 100% —
y ahora se sabe exactamente por qué.

---

## 7. Conectado a CI: `qa-golden-dataset-dry-run`

`evaluate_evaluator_agent.py` está diseñado para funcionar como gate de CI: en modo `--dry-run`
(sin LLM, sin red) devuelve un exit code según la accuracy obtenida:

```python
sys.exit(0 if accuracy >= 0.70 else 1)   # evaluate_evaluator_agent.py
```

**Corrección respecto a una versión anterior de este documento**: aquí decía *"no existe
ningún pipeline de CI en el repositorio"* — era cierto cuando se escribió esta sección
(27 ago), pero quedó desactualizado el 29 ago al añadirse `.github/workflows/ci.yml` (ver
[`defenderCI.md`](defenderCI.md) para el pipeline completo), y nadie volvió a esta
sección para corregirla. Hoy el job `qa-golden-dataset-dry-run` ejecuta exactamente este
script en cada PR, reutilizando ese mismo exit code sin inventar un umbral nuevo — el
orden real de los hechos fue: corregir primero la fidelidad del input (§5, `condition` no
se exportaba) y solo después conectarlo a CI, para no automatizar una señal poco fiable.

---

## 8. Preguntas frecuentes y objeciones comunes

### Objeción: "¿No es circular evaluar con reglas que se parecen a las que aplica el propio agente (`policy_rules.py`)?"

Es una objeción legítima y hay que reconocer su límite honestamente: `classify_case()`
(en el generador) y `policy_rules.py` (en el agente evaluador — ver
[`defenderAgentes.md` §9](defenderAgentes.md)) son implementaciones **independientes**,
escritas en momentos distintos del proyecto, que no comparten código. Que coincidan en
casos concretos es una señal real de que ambas capturan la misma intención de negocio
documentada en las políticas — no un artefacto circular donde el mismo código se
autoevalúa. El límite real: si ambas comparten el **mismo error de diseño** (p. ej. una
mala interpretación de una política legal), el golden dataset no lo detectaría — para eso
existen los 24 casos manuales curados (`tests/qa/manual/cases/`), revisados por una persona, no
generados por ninguna regla.

### Objeción: "¿Por qué 480 casos y no 15, o 1000?"

15 es el mínimo que planteaba originalmente la guía del proyecto para evaluar
RAGAS/faithfulness; 480 permite además medir precisión/recall/F1 por categoría (16
categorías × ~30 casos de media) con significancia estadística mínima, y sigue siendo
barato de generar (segundos, sin coste de API) al no depender de ningún LLM.

### Objeción: "¿Los datos son realistas o inventados sin criterio?"

Cada categoría tiene su propia configuración de política (plazo, condiciones admitidas,
recargo de reposición) que **coincide exactamente** con lo redactado en su documento
markdown (`data/rag/policies/`) — no son números arbitrarios. El texto libre del motivo
del cliente tampoco es una plantilla única: hay entre 4 y 8 redacciones distintas por
motivo (formal, coloquial, con alguna errata deliberada), para que el Agente de Triaje se
enfrente a texto variado, no a una frase repetida 480 veces.

### Objeción: "¿Por qué los IDs (UUID) cambian cada vez que regeneras el dataset?"

Es deliberado, no un descuido: los UUID son claves primarias sin significado de negocio
(a diferencia de `order_number`, que sí es estable — deterministic, basado en fecha). No
aporta valor fijarlos, y fijarlos obligaría a un generador de UUID con seed propio sin
ningún beneficio real a cambio.

### Objeción: "El dataset contempla evidencia fotográfica (`missing_evidence`) pero el agente no la verifica — ¿no es una inconsistencia?"

Es una limitación real, reconocida en §6, no una inconsistencia oculta. `classify_case()`
modela ese matiz de negocio a propósito (para generar casos `human_review` variados y
realistas), pero implementar la verificación de evidencia en el agente real —subida de
fotos, almacenamiento, nueva regla determinista— es una funcionalidad completa nueva, no
un ajuste, y afecta solo al 1.7% de los 480 casos. Se decidió documentar el techo de
accuracy que esto implica (~98.3%, no 100%) en vez de ampliar el alcance del proyecto
para cerrarlo.

---

## 9. Resumen para la presentación

> "El dataset de ReFlow se genera con un script Python 100% determinista, sin
> dependencias externas ni llamadas a APIs, después de descartar tanto un servidor MCP de
> datos sintéticos (deprecado, inestable en Windows) como datasets públicos de Kaggle
> (demasiado limitados). Una sola ejecución produce a la vez los datos para poblar la
> aplicación (320 clientes, 1100 pedidos) y un golden dataset de 480 casos con la decisión
> correcta ya calculada por código puro — sin IA — aplicando las mismas reglas del marco
> legal de políticas. Ese golden dataset se evalúa con dos herramientas que comparten la
> misma lógica de reconstrucción de casos: una local, para iterar rápido, y otra sobre
> Langfuse, para comparar accuracy entre versiones de prompt o modelo con trazabilidad
> completa. Durante el desarrollo detectamos y corregimos un problema real de fidelidad
> del propio dataset — el CSV no exportaba la condición del artículo que sus etiquetas
> usaban para calcularse — antes de considerar conectar la evaluación a un pipeline de CI."
