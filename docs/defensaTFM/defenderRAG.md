# Defensa de la Arquitectura RAG

## 1. ¿Qué es RAG y por qué lo usamos?

**Retrieval-Augmented Generation (RAG)** combina búsqueda semántica con generación de texto. En vez de meter todas las políticas de devolución en el prompt del LLM (costoso, limitado por contexto), buscamos solo las políticas relevantes y se las inyectamos como contexto.

### Alternativas descartadas

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Todas las políticas en el prompt | 17 documentos × ~2000 tokens = 34k tokens por llamada. Caro y supera el contexto útil |
| Fine-tuning del modelo | Requiere reentrenar con cada cambio de política. No viable para políticas que cambian frecuentemente |
| Búsqueda por keywords (TF-IDF) | No entiende sinónimos ni contexto semántico. "producto roto" no matchearía "artículo defectuoso" |
| Base de reglas hardcodeada | No escala a 16 categorías × N motivos. Rígido ante cambios |

**Decisión**: RAG con pgvector permite actualizar políticas editando Markdown, sin tocar código ni reentrenar modelos.

---

## 2. ¿Por qué pgvector en Supabase y no un vector store externo?

| Opción | Ventajas | Desventajas |
|--------|----------|-------------|
| **pgvector (elegido)** | Ya tenemos PostgreSQL, cero infra adicional, SQL nativo, joins con tablas de negocio | Menos optimizado que stores especializados para millones de vectores |
| Pinecone / Weaviate | Optimizados para búsqueda vectorial a escala | Servicio externo, coste adicional, latencia de red, vendor lock-in |
| ChromaDB | Simple, open-source | En memoria por defecto, requiere infra separada para persistencia |
| FAISS | Muy rápido, Facebook Research | Solo local, sin persistencia nativa, no serverless |

**Decisión**: Con ~102 chunks de política, pgvector es más que suficiente y evita un servicio externo. Mantener embeddings en la misma base de datos que los datos transaccionales permite hacer joins nativos entre chunks recuperados y filas de `return_policies` en una sola query, sin round-trips adicionales.

---

## 3. Pipeline de indexación

```
data/policies/*.md
        │
        ▼  _split_into_sections()  → divide por encabezados ## (4-6 secciones/doc)
        │
        ▼  _chunk_section()        → agrupa párrafos en 200-500 tokens sin partir frases
        │                             cada chunk incluye el encabezado de su sección
        │                             → 102 chunks totales (12 marco general + 5-6/categoría)
        ▼
    OpenAI text-embedding-3-small (1536 dimensiones)
    — una sola llamada API por fichero (batch), no una por chunk —
        │
        ▼
    INSERT INTO policy_embeddings
      { policy_id, chunk_text, embedding, metadata }

    metadata = {
        "source_doc":      "14_alimentacion.md",
        "chunk_index":     2,
        "category":        "alimentacion",   ← permite filtrar en el RPC sin JOIN
        "policy_version":  "2026-08"         ← invalida chunks si la política cambia
    }
```

### Decisión de chunking: por sección vs. tamaño fijo

Dividir por secciones (`## ...`) es superior a chunks de tamaño fijo porque:
- Cada sección cubre un **tema semántico completo** (plazos, exclusiones legales, HITL, ejemplos)
- El LLM recibe fragmentos con coherencia temática, no texto cortado a la mitad de una frase
- El encabezado prefijado en cada chunk le da contexto suficiente para leerlo de forma aislada

### Modelo de embedding elegido

| Modelo | Dimensiones | Coste | Rendimiento |
|--------|-------------|-------|-------------|
| `text-embedding-3-small` ✅ | 1536 | $0.02/1M tokens | Buen balance calidad/coste |
| `text-embedding-3-large` | 3072 | $0.13/1M tokens | Mejor calidad, 6x más caro |
| `text-embedding-ada-002` | 1536 | $0.10/1M tokens | Generación anterior, 5x más caro |

**Decisión**: `text-embedding-3-small` ofrece rendimiento comparable a `ada-002` a 1/5 del coste. Crítico: se usa el **mismo modelo** tanto al indexar como al consultar — si difirieran, las distancias coseno carecerían de significado.

---

## 4. Búsqueda en runtime: RPC sobre PostgreSQL

La búsqueda semántica se ejecuta como una **función PostgreSQL nativa** (`match_policy_embeddings`) invocada vía RPC sobre la API REST de Supabase. Esto permite que el cálculo de distancia coseno y el índice IVFFlat de pgvector corran dentro del motor de base de datos, sin mover los 1536 vectores al proceso Python.

### ¿Cómo funciona el índice IVFFlat?

El índice **IVFFlat (Inverted File Flat)** con `lists = 10` es un mecanismo de búsqueda aproximada en bases de datos vectoriales que divide el espacio de embeddings en 10 clústeres mediante K-Means. Al realizar una consulta, el sistema filtra y busca únicamente dentro de los clústeres más cercanos, en lugar de comparar el vector contra toda la base de datos.

Con solo 102 chunks repartidos en 10 clústeres (~10 vectores por clúster), el filtrado apenas descarta candidatos: el coste de comparar dentro de 1-2 clústeres cercanos es prácticamente el mismo que comparar contra toda la tabla. Es decir, el mecanismo ya está en su sitio y configurado correctamente, pero a este volumen no aporta una ganancia de velocidad medible frente a un escaneo exacto — su valor real se hará notar si el corpus de políticas crece a miles de chunks, momento en el que evitar comparar contra el 100% de los vectores sí supone una diferencia de rendimiento significativa.

### ¿RPC o REST?

Son el mismo transporte HTTP, con semántica diferente:

| Tipo | URL | Cuándo usarlo |
|------|-----|---------------|
| REST table | `GET /rest/v1/return_policies` | Leer/escribir recursos (CRUD) |
| **RPC** | `POST /rest/v1/rpc/match_policy_embeddings` | Llamar una función con lógica propia |

`match_policy_embeddings` no encaja en REST porque no devuelve un recurso — ejecuta un cálculo vectorial y devuelve resultados ordenados por similitud. Por eso Supabase lo expone bajo `/rpc/`.

### Función SQL (migration 013)

```sql
CREATE OR REPLACE FUNCTION match_policy_embeddings(
    query_embedding  VECTOR(1536),
    match_threshold  FLOAT  DEFAULT 0.7,
    match_count      INT    DEFAULT 5,
    filter_category  TEXT   DEFAULT NULL   -- ← añadido en v2
)
RETURNS TABLE (id UUID, policy_id UUID, chunk_text TEXT, similarity FLOAT)
AS $$
    SELECT pe.id, pe.policy_id, pe.chunk_text,
           1 - (pe.embedding <=> query_embedding) AS similarity
    FROM policy_embeddings pe
    WHERE 1 - (pe.embedding <=> query_embedding) > match_threshold
      AND (
          filter_category IS NULL
          OR pe.metadata->>'category' = filter_category
          OR pe.metadata->>'category' = 'general'  -- marco general: aplica a todas
      )
    ORDER BY pe.embedding <=> query_embedding
    LIMIT match_count;
$$;
```

### Por qué se añadió `filter_category`

Sin este filtro, una query para `alimentacion` podría devolver chunks de `mascotas` o `drogueria_salud` con mayor similitud (las tres son categorías de higiene sensible con texto casi idéntico). El filtro garantiza que el agente solo recibe fragmentos de la política de **su** categoría, más los del marco general que aplica a todas.

### Parámetros de búsqueda

| Parámetro | Valor | Justificación |
|-----------|-------|----------------|
| `match_threshold` | 0.5 (`Settings.rag_match_threshold`, configurable vía `RAG_MATCH_THRESHOLD`) | Calibrado contra similitud real medida en 32 ejecuciones (16 categorías × 2 motivos) — ver §4.1 |
| `match_count` | 5 | Suficiente contexto sin saturar el prompt del Evaluador |
| Distancia | Coseno (`<=>`) | Estándar para embeddings de texto, invariante a la magnitud |

---

## 4.1. Investigación: el umbral 0.7 dejaba el RAG sin devolver nada en uso real

### El síntoma

Inspeccionando una traza real en Langfuse (`score_rag_similarity`, ver `backend/services/observability.py`), una búsqueda real —pedido de perfumería, motivo "ya no lo necesito", artículo sin abrir— devolvía `semantic_results: []` y `similarity: 0.0`. No era un caso aislado: **con `match_threshold=0.7`, la inmensa mayoría de búsquedas reales devuelven 0 chunks**, enmascarado en producción porque `policy_rules.py` no depende del RAG para decidir elegibilidad (solo aporta contexto narrativo adicional al LLM) — el sistema seguía funcionando, pero el Evaluador razonaba "a ciegas" respecto al contenido específico de cada política de categoría.

### Por qué pasa

`text-embedding-3-small` compara una query corta orientada al **caso del cliente** (motivo + estado del artículo, registro conversacional) contra párrafos de un documento de política largo, en **registro normativo/formal**. Ese contraste de registro limita la similitud coseno alcanzable, con independencia de que el contenido sea semánticamente correcto.

### Intento anterior (revertido) y por qué no era suficiente

El 30/08 se bajó `rag_match_threshold` a 0.35 tras medir similitud real en 4 categorías (commit `0b8221e`). Se revirtió 31 minutos después (commit `9e06e4c`) con el argumento correcto: *"0.35 se elegía con datos de pocas categorías y una única orden de verificación — insuficiente para fijar un valor de producción."* La infraestructura (umbral configurable vía env, `condition` incluida en la query) se mantuvo; el número concreto no.

### Metodología de esta investigación

Para no repetir el mismo error, se midió la similitud coseno real (consultando `match_policy_embeddings` directamente contra la BD, con `match_threshold=0` para observar el valor crudo) en **las 16 categorías completas del catálogo, con 2 motivos distintos cada una (`defective`/`defective` y `changed_mind`/`unopened`) = 32 ejecuciones reales**, no simuladas ni mockeadas.

### Hallazgo 1 — la query importa más que el umbral

Reformular la query de "motivo+estado del cliente" (registro conversacional) a "pregunta sobre la política de la categoría" (registro documental) sube la similitud media de forma consistente:

| Estilo de query | Ejemplo | Similitud media (mejor chunk) |
|---|---|---|
| **Anterior** — `f"devolución {reason_category} {condition} {reason}"` | `"devolución no_longer_needed unopened he cambiado de opinión"` | ~0.47 (nunca cerca de 0.7) |
| **Nueva** — pregunta de política + motivo/estado como desambiguador | `"política de devolución en cosmetica_perfumeria: motivo ya no lo necesita, estado del producto sin abrir"` | ~0.68 |

Se mantienen `reason_category`/`condition` en la query nueva (no el texto libre `reason` del cliente) para conservar la especificidad del caso — una query puramente genérica de categoría, sin motivo ni estado, no recuperaba en el top-5 el chunk de "reacciones alérgicas" de cosmética; añadir el motivo sí lo recupera, a cambio de una similitud levemente menor (0.61-0.67 en vez de 0.70-0.74) pero suficiente.

### Hallazgo 2 — cuántos chunks sobreviven a cada umbral candidato (32 ejecuciones reales)

| `match_threshold` | Chunks devueltos (de 5) | Casos con 0 chunks |
|---|---|---|
| 0.45 | min=5, media=5.00 | 0/32 |
| **0.50 (elegido)** | **min=4, media=4.97** | **0/32** |
| 0.55 | min=2, media=4.41 | 0/32 |
| 0.60 | min=1, media=3.16 | 0/32 |
| 0.65 | min=0, media=1.62 | 2/32 |
| 0.70 (anterior) | min=0, media=0.09 | **29/32 (91%)** |

**0.5** es el punto con margen de seguridad más amplio antes de perder cobertura: garantiza al menos 4 de los 5 chunks en el peor caso observado, sin ningún fallo en las 32 pruebas, y queda claramente por debajo del "peor mejor-chunk" real (0.6444, categoría `alimentacion`).

### Hallazgo 3 — traducir los motivos/estados a castellano ayuda, pero de forma menor

`reason_category`/`condition` viajan en inglés en el código (`defective`, `changed_mind`, `unopened`...). Traducirlos *solo dentro de la query RAG* (sin tocar la lógica de negocio, que sigue comparando contra los valores en inglés) elimina el último anglicismo de una query ya mayoritariamente en castellano:

| | EN (`defective`, `unopened`...) | ES (`defectuoso`, `sin abrir`...) |
|---|---|---|
| Similitud media (8 categorías × 2 motivos) | 0.6723 | 0.6832 |
| Mejora | — | **+0.0109** (positiva en 15/16 comparaciones) |

Efecto real pero modesto — se incluye porque el coste de implementarlo es un diccionario de traducción de ~10 valores (`_REASON_CATEGORY_ES`/`_CONDITION_ES` en `evaluator.py`), no una reformulación estructural.

### Decisión final

1. **Query** (`evaluator.py::_build_rag_query`): registro documental (`"política de devolución en {category}: motivo {reason_es}, estado del producto {condition_es}"`) con motivo/estado traducidos al castellano.
2. **Umbral** (`Settings.rag_match_threshold`): **0.5**, con evidencia de 32 ejecuciones reales sin ningún fallo — corrige el "insuficiente para producción" del intento revertido con 8× más puntos de datos y las 16 categorías completas, no una muestra parcial.
3. Verificado end-to-end contra la BD real (no solo mocks): el caso original que devolvía `semantic_results: []` ahora devuelve 5 chunks con similitud 0.61-0.67. Suite completa (101 tests) y `evaluate_evaluator_agent.py --dry-run` (480 casos, accuracy 87.3%) sin regresiones — ambos aíslan el RAG mockeándolo, así que no podían haber detectado este problema en primer lugar; es un recordatorio de que un dry-run/mock en verde no implica que el sistema real funcione.

---

## 5. Búsqueda híbrida: semántica + estructurada

```python
# 1. Búsqueda semántica: chunks relevantes por significado (RPC)
#    — filtra por categoría para evitar cross-contamination entre políticas —
rpc_params = {
    "query_embedding": query_embedding,
    "match_threshold": get_settings().rag_match_threshold,  # 0.5 por defecto (ver §4.1)
    "match_count": 5,
    "filter_category": category or None,
}
results = await client.rpc("match_policy_embeddings", rpc_params).execute()

# 2. Filtro estructurado: política exacta de la categoría (REST)
policy_info = await client.table("return_policies")
    .eq("category", category)
    .eq("active", True)
```

Los dos se complementan:
- Los **chunks RAG** aportan contexto narrativo (casos especiales, ejemplos, excepciones legales)
- La **fila estructurada** garantiza los datos exactos (plazo máximo, `allowed_conditions`, recargo) que las reglas deterministas necesitan para su lógica

---

## 6. ¿Por qué el LLM decide y no solo un motor de reglas?

El Agente Evaluador combina ambos:

| Dato | Fuente | Tipo de decisión |
|------|--------|-----------------|
| ¿Dentro de plazo? | `calculate_days_since_delivery()` vs `max_return_days` | Determinista |
| ¿Condición permitida? | `condition` vs `allowed_conditions` | Determinista |
| ¿Historial sospechoso? | `approved > 5` en 6 meses | Determinista |
| ¿Importe > 100€? | `refund_amount` vs umbral HITL | Determinista |
| ¿Caso ambiguo? (descripción difusa, motivo sensible, zona frontera) | LLM con contexto RAG | Razonamiento |

El LLM recibe los datos ya calculados (días desde entrega, historial) y las políticas relevantes (RAG). Su trabajo es **sintetizar** la decisión y generar una explicación auditable, no inventar reglas.

---

## 7. Corpus de políticas: ¿por qué 17 documentos Markdown?

| Decisión | Justificación |
|----------|---------------|
| Markdown (no JSON/YAML) | Legible por humanos, fácil de editar, buen chunking por secciones |
| 1 doc por categoría | Permite actualizaciones granulares sin re-indexar todo |
| Marco general separado (`00_marco_general`) | Reglas comunes (14 días legales, umbral HITL 100€) aplicables a todas las categorías. Se ingesta con `policy_id = NULL` y `category = "general"` — el filtro de categoría siempre lo incluye |
| 16 categorías específicas | Cubren el catálogo de la tienda ficticia "Mercadia" con reglas diferenciadas |
| `policy_version` en metadata | Permite detectar chunks obsoletos si las políticas se actualizan |

### Ejemplo de chunk resultante

```
## 3. Casuística específica

- **Alimentación no perecedera sellada**: se acepta devolución por cambio de
  opinión únicamente si el envase original está intacto, sin abrir, y con al
  menos 2 meses de vigencia hasta su fecha de consumo preferente...
```

Cada chunk incluye el encabezado de su sección, por lo que el LLM puede leerlo en aislamiento total y entender de qué trata sin necesitar el resto del documento.

---

## 8. Evaluación del RAG

El fichero `data/eval_cases.csv` contiene un golden dataset con la decisión esperada para cada caso:

```csv
case_id, category, reason_category, days_since_delivery, refund_amount, expected_label, rationale
...,     alimentacion, defective,   5,                   29.99,          valid,          "Dentro de plazo..."
...,     juguetes,     quality_issue, 1,                 55.98,          invalid,        "Condición no admitida..."
...,     electrodomesticos, defective, 16,               289.99,         human_review,   "Importe >100€..."
```

**480 casos** con distribución: 27% válido · 28% inválido · 45% revisión humana.

Esto permite medir **precisión del sistema completo** (RAG + reglas deterministas + LLM Evaluador) de forma automática, sin depender de evaluación humana subjetiva.

---

## 9. Librerías LLM/RAG: qué se usa y qué no, y por qué

Pregunta habitual en la defensa: *"¿por qué no usáis LangChain para todo, incluido el RAG?"*. Esta sección lo deja explícito.

### Qué se usa y para qué

| Librería | Se usa en | Para qué |
|----------|-----------|----------|
| `langgraph` | `backend/agents/graph.py` | Orquesta el grafo de agentes (`StateGraph`, aristas condicionales, checkpointer sobre Postgres) |
| `langchain` / `langchain-core` | `backend/agents/nodes/*.py` | Abstracción de mensajes (`HumanMessage`, `AIMessage`) y tool-calling que consume LangGraph |
| `langchain-openai` | `triage.py`, `evaluator.py`, `resolution.py` | `ChatOpenAI` para las llamadas al LLM de los tres agentes |
| `langchain-mcp-adapters` | `backend/agents/infra/mcp_client.py` | Traduce las tools de los servers MCP (Supabase, Logística) al formato de tool-calling que entiende LangGraph |
| `openai` (SDK oficial, sin envoltorio LangChain) | `data/rag/ingest_policy_embeddings.py` y `search_return_policy()` en `supabase_service.py` | Genera los embeddings, tanto al indexar las políticas como al resolver cada consulta |

### Qué NO se usa y por qué

| Librería | Por qué se descarta |
|----------|----------------------|
| `langchain-community` | Es una colección de *wrappers* (vector stores, document loaders, retrievers de terceros) pensada para no escribir tú la llamada a la API. Aquí la llamada a embeddings es una única línea (`client.embeddings.create(...)`, ver §3) y la búsqueda ya es una función SQL nativa (`match_policy_embeddings`, ver §4) — envolver eso en un `VectorStore` de LangChain añadiría una capa de indirección sobre dos líneas de código, a cambio de un paquete grande con dependencias de decenas de integradores que no se usan en este proyecto. |
| `faiss-cpu` | Ya descartado frente a pgvector en la tabla de la §2, pero el motivo de fondo es de arquitectura de procesos: ReFlow corre **tres procesos Python separados** (API FastAPI, MCP Supabase, MCP Logística — ver `start_all.sh`) que pueden necesitar los embeddings. FAISS construye un índice en memoria/disco **local a un único proceso**; usarlo obligaría a cargarlo por duplicado en cada proceso y a sincronizarlo a mano cada vez que cambian las políticas. pgvector vive dentro de Supabase, así que los tres procesos consultan la **misma** tabla por SQL/RPC sin ningún paso de sincronización adicional. |

### Decisión

Se usa LangChain/LangGraph donde aporta valor real — orquestación con estado, checkpointing, tool-calling entre agentes y servers MCP —, pero no como capa universal para todo lo que toca a un LLM. Para el RAG en concreto, ir directo a `openai` + una función SQL en Postgres es menos código, menos dependencias que mantener actualizadas, y aprovecha que Supabase ya es la única fuente de datos compartida entre los tres servicios, sin necesidad de un vector store adicional que sincronizar.
