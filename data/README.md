# Dataset sintético de prueba — ReFlow

Este directorio contiene un dataset sintético **grande, variado y realista** para
iterar con el RAG de políticas de devolución y con el futuro sistema
multi-agente (Épica 2 de [`doc/guia.md`](../doc/guia.md)), atendiendo a la
recomendación del profesor en
[`AnotacionesProfesorSobreTFM.md`](../AnotacionesProfesorSobreTFM.md):

> "También concretaría pronto el dataset de prueba: pedidos, productos,
> políticas de devolución, importes, estados logísticos y casos límite. Sería
> interesante incluir ejemplos donde la devolución sea claramente válida,
> claramente no válida y casos ambiguos que activen el Human-in-the-Loop."

No se ha usado ningún generador externo de datos sintéticos: se probó a
conectar el servidor MCP `awslabs.syntheticdata-mcp-server` (AWS Labs), pero
resultó imposible de estabilizar en Windows y, más importante, la propia
documentación de AWS Labs señala que ese paquete está **deprecado** porque
"la funcionalidad principal ya la puede cubrir un asistente de IA moderno".
También se exploraron datasets de Kaggle sobre devoluciones de e-commerce
(con la API oficial, usando credenciales reales), pero resultaron ser
datasets tabulares para Machine Learning (5 categorías, 4 motivos, sin ningún
texto de política) — más limitados que lo que ya teníamos, así que no se
incorporó nada de ahí. En su lugar, todo el dataset se genera con un script
Python determinista y reproducible (`generate_dataset.py`, solo librería
estándar, sin llamadas a APIs).

## Qué contiene

```
data/
  policies/                       16 políticas de categoría + 1 marco general (markdown)
  generate_dataset.py             Script generador (reproducible, seed fija)
  ingest_policy_embeddings.py     Trocea policies/*.md y genera sus embeddings en policy_embeddings (RAG)
  eval_cases.csv                  Golden dataset etiquetado para evaluar al Agente Evaluador
  GENERATION_STATS.md             Estadísticas de la última generación (recuento, distribución)
  README.md                       Este documento
supabase/
  seed_synthetic.sql              INSERTs generados (customers, products, orders, order_items,
                                   return_policies, return_requests, return_items,
                                   chat_sessions, chat_messages)
```

### 1. Documentación de políticas (`data/policies/`)

17 documentos markdown que constituyen la base de conocimiento a vectorizar
para el RAG (`policy_embeddings` / `match_policy_embeddings`):

- [`00_marco_general_devoluciones.md`](policies/00_marco_general_devoluciones.md):
  marco legal común (derecho de desistimiento de 14 días naturales, TRLGDCU y
  Directiva 2011/83/UE, excepciones legales del art. 103, umbral fijo de
  **100 € para Human-in-the-Loop**, reglas de aprobación/rechazo automático,
  tabla resumen de las 16 categorías).
- Un documento por categoría (`01_...md` a `16_...md`), cada uno de
  ~700-1100 palabras, con: plazo y condiciones, exclusiones legales
  específicas (higiene, perecederos, personalización), casuística detallada
  (defectos, montaje, garantía legal vs. comercial, fraude/abuso) y ejemplos
  ilustrativos explícitamente etiquetados como **claramente válido**,
  **claramente inválido** y **ambiguo (HITL)**.

El conjunto son ~15.000 palabras de documentación realista — suficiente
volumen para justificar el chunking y la indexación vectorial (cada documento
produce varios chunks de ~300-500 tokens al trocearlo para
`policy_embeddings`).

Estos mismos ficheros son los que se insertan **tal cual** (contenido íntegro)
en `return_policies.policy_text` al generar el SQL, de modo que la
documentación "fuente" (markdown, legible y versionable en git) y el dato
cargado en Supabase para el RAG son siempre idénticos.

### 2. Catálogo de productos (16 categorías, ~196 SKUs)

Para cubrir un catálogo tipo "Amazon/Costco" (de todo), se generan productos
ficticios (marcas inventadas, sin usar marcas reales) en 16 categorías:

`electronica_informatica`, `electrodomesticos`, `moda_ropa`, `calzado`,
`joyeria_relojes`, `hogar_decoracion`, `muebles`, `jardineria_bricolaje`,
`juguetes`, `bebe_puericultura`, `deportes_aire_libre`, `cosmetica_perfumeria`,
`drogueria_salud`, `alimentacion`, `mascotas`, `libros_papeleria`.

Cada categoría tiene su propia configuración de política (plazo en días,
si exige embalaje original, recargo de reposición, estados aceptados) que
coincide exactamente con lo redactado en su documento markdown.

### 3. Clientes, pedidos y líneas de pedido

- 320 clientes ficticios (nombre, email, teléfono y dirección españoles
  realistas, repartidos en 20 ciudades).
- 1.100 pedidos entre hace ~14 meses y hoy, con `status` variado (`delivered`,
  `shipped`, `processing`, `cancelled`, `returned`) y ~2.400 líneas de pedido.
- 16 clientes marcados internamente como "devolvedores frecuentes" para
  generar el patrón de abuso que el Agente Evaluador debe detectar vía
  `get_customer_return_history` (más devoluciones de lo habitual,
  concentradas en esos clientes).

### 4. Solicitudes de devolución con etiqueta esperada (golden dataset)

480 `return_requests` (con sus `return_items`), generadas variando
deliberadamente: categoría, motivo (`reason_category`: 15 valores distintos,
desde `defective` hasta `allergic_reaction` o `counterfeit_suspicion`),
estado físico del artículo, días transcurridos desde la entrega (con sesgo
hacia cuatro zonas: muy dentro de plazo, frontera antes del límite, frontera
justo después del límite, y muy fuera de plazo) e importe.

El texto libre del motivo (`return_requests.reason`) no es una única frase
fija por `reason_category`: hay entre 4 y 8 redacciones distintas por motivo
(formal, coloquial, con alguna errata deliberada, con o sin el nombre del
producto), elegidas al azar en cada caso (`REASON_TEXT_VARIANTS` en
`generate_dataset.py`) — pensado para que el futuro Agente de Triaje se
enfrente a texto de cliente real y variado, no a una plantilla repetida.

Cada caso se clasifica automáticamente, aplicando **exactamente las reglas de
la sección 5 del documento general** (no es una etiqueta aleatoria), en:

- **`valid`** — el Agente Evaluador debería poder aprobarlo automáticamente
  (dentro de plazo, estado admitido, importe ≤ 100 €, sin motivo sensible).
- **`invalid`** — debería poder rechazarlo automáticamente (plazo superado
  con más de 5 días de margen, o exclusión legal de higiene/perecederos con
  el precinto roto por cambio de opinión).
- **`human_review`** — debe derivarse a revisión humana (HITL): importe > 100 €,
  solicitud en zona frontera del plazo, motivo sensible (`allergic_reaction`,
  `counterfeit_suspicion`), cliente con historial de devoluciones elevado, o
  falta de evidencia fotográfica exigible.

Distribución obtenida en la última generación (ver
[`GENERATION_STATS.md`](GENERATION_STATS.md) para el detalle y el desglose
por categoría): **~27% valid / ~28% invalid / ~45% human_review** — un
resultado deliberadamente realista: con un umbral fijo de 100 € y categorías
con precio medio alto (electrónica, muebles, electrodomésticos, deportes),
una parte importante de los casos legítimos igualmente requiere revisión
humana, que es precisamente el comportamiento que el TFM quiere demostrar.

El fichero [`eval_cases.csv`](eval_cases.csv) es este golden dataset en
formato tabular (`case_id`, `order_number`, `category`, `reason_category`,
`days_since_delivery`, `refund_amount`, `expected_label`, `rationale`, ...),
pensado para:

- Evaluar la precisión de la lógica determinista del Agente Evaluador
  (comparar su decisión contra `expected_label`).
- Servir de base ampliada para el "Golden Dataset" de 15 consultas que
  `doc/guia.md` (Épica 5, US 5.2) prevé para evaluar RAGAS/faithfulness —
  aquí hay 480 casos en vez de 15, pero se puede tomar un subconjunto
  representativo (por ejemplo, 3-4 por categoría cubriendo los tres labels).

Cada `return_requests.notes` generado incluye además un prefijo
`[CASE:VALID]`, `[CASE:INVALID]` o `[CASE:HUMAN_REVIEW]` seguido de la
justificación (`rationale`) en español, referenciando la regla concreta de la
política aplicada — pensado para trazabilidad y para depurar visualmente el
dataset directamente en la tabla `return_requests` sin tener que cruzar con
el CSV.

### 5. Conversaciones sintéticas (`chat_sessions` / `chat_messages`)

140 conversaciones (765 mensajes) que simulan el flujo de tres agentes
descrito en `doc/guia.md` (Triaje → Evaluador → Resolución), asociadas a un
subconjunto de las 480 devoluciones: saludo del cliente, petición del número
de pedido, el cliente explica el motivo (reutilizando la misma variedad de
texto libre de la sección 4), el asistente confirma que va a revisar la
política de la categoría, y cierra con el veredicto real del caso (aprobado
con importe de reembolso, rechazado con el motivo concreto, o derivado a
revisión humana). Los casos `human_review` añaden además un mensaje de
`role = 'system'` registrando el `return_request_id` derivado a HITL.

Pensado para dar contenido conversacional real (no solo filas tabulares) con
el que probar el futuro Agente de Triaje y para tener ejemplos de uso del RAG
en contexto de chat.

## Cómo regenerar el dataset

```bash
python data/generate_dataset.py
```

Es determinista (semilla fija `SEED = 20260730` en el propio script): la
misma versión del script siempre produce el mismo número de filas y la misma
distribución de casos (los UUID sí cambian en cada ejecución, ya que se usan
como claves primarias y no aportan valor fijarlos). Regenera:

- `supabase/seed_synthetic.sql`
- `data/eval_cases.csv`
- `data/GENERATION_STATS.md`

Para ajustar el volumen o la mezcla de casos, editar las constantes al
principio de `main()` (`n_customers`, `n_orders`, `target_returns`,
`n_frequent_returners`) o los pesos de `DAY_BUCKETS` / `pick_reason_and_condition`.

## Cómo cargar el dataset en Supabase

Este fichero es **adicional** a [`supabase/seed.sql`](../supabase/seed.sql)
(el seed pequeño de 3 clientes / 5 productos que usan los tests de
`tests/test_mcp_supabase.py`), no lo sustituye. Para un entorno de desarrollo
o de pruebas de RAG dedicado a este dataset grande, se recomienda:

1. Aplicar las migraciones (`supabase/migrations/*.sql` o `supabase/run_all.sql`
   sin la sección de seed) sobre una base de datos limpia.
2. Cargar `supabase/seed_synthetic.sql` con `psql` o el SQL Editor de Supabase
   (esto crea, entre otras, las 16 filas de `return_policies`, una por categoría).
3. Trocear los documentos de `data/policies/*.md` y generar sus embeddings
   con `text-embedding-3-small` (el mismo modelo que ya usa
   `search_return_policy` en `backend/services/supabase_service.py`) para
   poblar `policy_embeddings`:

   ```bash
   python -m dataset.ingest_policy_embeddings
   ```

   Requiere `OPENAI_API_KEY` y las credenciales de Supabase en `.env`, y que
   el paso 2 ya se haya ejecutado (cada documento de categoría se enlaza a su
   fila de `return_policies` por `category`; si falta, ese documento se salta
   con un aviso en vez de fallar todo el script). El marco general
   (`00_marco_general_devoluciones.md`) no está atado a ninguna categoría, se
   ingesta con `policy_id = NULL` — el RAG lo encuentra igual porque
   `match_policy_embeddings` busca por similitud de embedding, no por
   `policy_id`. El script trocea por secciones (`## ...`) en chunks de
   ~300-500 tokens sin partir párrafos (ver
   `data/ingest_policy_embeddings.py` para el detalle) y es idempotente:
   volver a ejecutarlo reemplaza los chunks existentes de cada política en
   vez de duplicarlos. `--dry-run` trocea y cuenta sin llamar a OpenAI ni a
   Supabase; `--category <slug>` limita la ingesta a una sola categoría (más
   el marco general).

Si se carga en la misma base que ya tiene `seed.sql`, no hay colisión de
claves (los emails, SKUs y `order_number` son distintos). `seed.sql` usa la
misma taxonomía en español que este dataset (`electronica_informatica`,
`moda_ropa`, `electrodomesticos`, `libros_papeleria`) y su INSERT de
`return_policies` lleva `ON CONFLICT (category) WHERE active DO NOTHING`:
si esta base ya tiene una política activa para esa categoría (p. ej. cargada
desde este dataset o desde la ingesta de `data/rag/policies/`), el INSERT de
`seed.sql` no hace nada y esos 5 productos quedan cubiertos por la política
real en vez de por una fila huérfana en inglés sin RAG detrás.

## Qué queda fuera de este dataset (decisión deliberada)

- **`chat_sessions`/`chat_messages` es una muestra ilustrativa, no una
  cobertura exhaustiva.** Cubre 140 de las 480 devoluciones (~29%), elegidas
  con muestreo aleatorio uniforme sobre el conjunto completo — no filtrado
  por categoría ni por etiqueta, así que la mezcla de la muestra reproduce
  aproximadamente la del dataset entero. En la última generación:

  | Etiqueta | Conversaciones | % de la muestra | % de esa etiqueta cubierto |
  |---|---|---|---|
  | `valid` | 33 | 23.6% | 25.2% de las 131 `valid` |
  | `invalid` | 42 | 30.0% | 31.1% de las 135 `invalid` |
  | `human_review` | 65 | 46.4% | 30.4% de las 214 `human_review` |

  (cifras exactas de la última ejecución en la tabla correspondiente de
  [`GENERATION_STATS.md`](GENERATION_STATS.md)). Es decir, aproximadamente
  **1 de cada 3 devoluciones de cada etiqueta** tiene una conversación
  asociada; las otras ~2 de cada 3 solo existen como fila de
  `return_requests` + `return_items`, sin traza de chat.

  **Por qué no se generó una conversación por cada una de las 480**: el
  valor añadido de una conversación es demostrar el *patrón* de diálogo
  (saludo → petición de nº de pedido → motivo del cliente → confirmación →
  veredicto), no producir 480 variaciones casi idénticas de ese mismo patrón
  para casos que ya son estructuralmente equivalentes (p. ej. dos
  devoluciones `valid` de calzado por `wrong_size` con importes parecidos
  generarían conversaciones casi calcadas). El texto libre del cliente ya
  varía por sí solo vía `REASON_TEXT_VARIANTS` (sección 4); las
  conversaciones añaden el envoltorio narrativo completo encima de eso para
  un subconjunto representativo, no para el 100%.

  **Qué SÍ hay para trazar cada conversación con su devolución**: cada
  `chat_sessions.metadata` (JSONB) incluye `return_request_id`,
  `order_number` y `expected_label`, por ejemplo:

  ```json
  {"return_request_id": "946c611c-...", "order_number": "ORD-2026-00369",
   "expected_label": "invalid", "source": "synthetic_dataset"}
  ```

  Esto permite hacer `JOIN`/filtrar en Supabase entre `chat_sessions` y
  `return_requests` sin ambigüedad, y usar el par (conversación, fila
  tabular) como caso de prueba conjunto cuando exista.

  **Qué patrones de conversación NO cubre esta muestra** (limitación real,
  no solo de volumen): cada conversación tiene exactamente un turno de
  veredicto final y no modela ida y vuelta — no hay casos donde el cliente
  insiste tras un rechazo, pide hablar con una persona, aporta una foto a
  mitad de conversación, se equivoca primero de número de pedido, o donde un
  administrador retoma la conversación para resolver un `human_review` (ese
  cierre por parte del admin no existe en ningún mensaje: la conversación
  del cliente termina en "pendiente de revisión" y ahí se corta). Todos esos
  patrones son contenido válido para ampliar más adelante, pero no están
  generados aquí.

  **Cómo ampliar la cobertura** si hiciera falta más adelante: subir
  `n_chat_conversations` en `main()` de `generate_dataset.py` (hoy en 140)
  hasta el máximo de 480, o añadir nuevas plantillas en `CLOSING_BY_LABEL` /
  turnos adicionales en `build_chat_sessions()` para cubrir los patrones de
  ida y vuelta mencionados arriba.

- **Nuances muy finas de cada política** (por ejemplo, la excepción de
  colchones sin funda protectora en `muebles`, o el accidente de tráfico en
  sillas de coche de `bebe_puericultura`) están descritas en los documentos
  markdown pero no todas están mecánicamente forzadas en el generador — el
  generador cubre los patrones principales (plazo, higiene/perecederos,
  importe > 100 €, motivos sensibles, abuso) de forma sistemática; los casos
  más específicos sirven como contenido de prueba para el RAG (se puede
  preguntar por ellos) aunque no haya necesariamente una fila de
  `return_requests` que los ejemplifique exactamente.
