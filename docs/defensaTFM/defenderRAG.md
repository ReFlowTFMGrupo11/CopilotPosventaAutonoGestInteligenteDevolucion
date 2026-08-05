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

**Decisión**: Con ~100-200 chunks de política, pgvector es más que suficiente y evita un servicio externo. Además, permite hacer queries híbridas (semántica + filtro por categoría en la misma query SQL).

---

## 3. Pipeline de indexación

```
dataset/policies/*.md
        │
        ▼
    Chunking (por sección del documento)
        │
        ▼
    OpenAI text-embedding-3-small (1536 dimensiones)
        │
        ▼
    INSERT INTO policy_embeddings (chunk_text, embedding, policy_id)
```

### Modelo de embedding elegido

| Modelo | Dimensiones | Coste | Rendimiento |
|--------|-------------|-------|-------------|
| `text-embedding-3-small` ✅ | 1536 | $0.02/1M tokens | Buen balance calidad/coste |
| `text-embedding-3-large` | 3072 | $0.13/1M tokens | Mejor calidad, 6x más caro |
| `text-embedding-ada-002` | 1536 | $0.10/1M tokens | Generación anterior, 5x más caro |

**Decisión**: `text-embedding-3-small` ofrece rendimiento comparable a `ada-002` a 1/5 del coste. Para ~200 chunks de políticas de devolución, la diferencia de calidad con `3-large` es negligible.

---

## 4. Búsqueda en runtime

```sql
-- Función match_policy_embeddings (supabase/migrations/011_create_functions.sql)
SELECT *, 1 - (embedding <=> query_embedding) AS similarity
FROM policy_embeddings
WHERE 1 - (embedding <=> query_embedding) > match_threshold
ORDER BY similarity DESC
LIMIT match_count;
```

### Parámetros elegidos

| Parámetro | Valor | Justificación |
|-----------|-------|---------------|
| `match_threshold` | 0.7 | Filtra resultados irrelevantes sin ser demasiado restrictivo |
| `match_count` | 5 | Suficiente contexto sin saturar el prompt del Evaluador |
| Distancia | Coseno (`<=>`) | Estándar para embeddings de texto, invariante a la magnitud |

### Búsqueda híbrida: semántica + estructurada

```python
# 1. Búsqueda semántica: chunks relevantes por significado
results = await client.rpc("match_policy_embeddings", {...})

# 2. Filtro estructurado: política exacta de la categoría
policy_info = await client.table("return_policies")
    .eq("category", category)  # "electronics", "moda", etc.
    .eq("active", True)
```

Esto es clave: la búsqueda semántica encuentra los fragmentos relevantes (e.g., "productos defectuosos pueden devolverse en 30 días"), pero el filtro estructurado garantiza que siempre tenemos los datos exactos de la categoría (plazo máximo, restocking fee, condiciones permitidas).

---

## 5. ¿Por qué el LLM decide y no un motor de reglas?

El Agente Evaluador combina ambos:

| Dato | Fuente | Tipo de decisión |
|------|--------|-----------------|
| ¿Dentro de plazo? | `calculate_days_since_delivery()` vs `max_return_days` | Determinista |
| ¿Condición permitida? | `condition` vs `allowed_conditions` | Determinista |
| ¿Historial sospechoso? | `approved > 5` en 6 meses | Determinista |
| ¿Caso ambiguo? (descripción difusa, producto sin categoría clara) | LLM con contexto RAG | Razonamiento |

El LLM recibe los datos ya calculados (días desde entrega, historial) y las políticas relevantes (RAG). Su trabajo es **sintetizar** la decisión y generar una explicación auditable, no inventar reglas.

---

## 6. Corpus de políticas: ¿por qué 17 documentos Markdown?

| Decisión | Justificación |
|----------|---------------|
| Markdown (no JSON/YAML) | Legible por humanos, fácil de editar, buen chunking por secciones |
| 1 doc por categoría | Permite actualizaciones granulares sin re-indexar todo |
| Marco general separado (`00_marco_general`) | Reglas comunes (14 días legales, umbral HITL 100€) aplicables a todas las categorías |
| 16 categorías específicas | Cubren el catálogo de la tienda ficticia "Mercadia" con reglas diferenciadas |

### Ejemplo de chunking

```markdown
## 3. Condiciones de devolución          ← Chunk 1: condiciones
Los productos electrónicos defectuosos
pueden devolverse en 30 días...

## 4. Restocking fee                     ← Chunk 2: fees
No se aplica cargo por restock en
productos defectuosos...
```

Cada sección se vectoriza como un chunk independiente, permitiendo que la búsqueda semántica encuentre exactamente el fragmento relevante.

---

## 7. Evaluación del RAG

El fichero `dataset/eval_cases.csv` contiene un golden dataset con la decisión esperada para cada caso:

```csv
case_id, category, reason_category, days_since_delivery, expected_label, rationale
...,     electronics, defective,    5,                    valid,          "Dentro de plazo..."
...,     juguetes,    quality_issue, 1,                   invalid,        "Condición no permitida..."
...,     electrodomesticos, defective, 16,                human_review,   "Importe >100€..."
```

Esto permite medir **precisión del sistema completo** (RAG + Evaluador) de forma automática, sin depender de evaluación humana subjetiva.
