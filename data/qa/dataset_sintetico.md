# Resumen del Dataset Sintético de Pruebas — ReFlow

## 1. Propósito

En su revisión de la propuesta ([`AnotacionesProfesorSobreTFM.md`](../AnotacionesProfesorSobreTFM.md)),
el profesor recomendó concretar pronto el dataset de prueba —pedidos, productos,
políticas de devolución, importes, estados logísticos y casos límite— e incluir
explícitamente tres tipos de ejemplo: devoluciones **claramente válidas**,
**claramente no válidas** y **casos ambiguos que activen el Human-in-the-Loop
(HITL)**.

Este documento resume el dataset construido para cubrir ese encargo y explica
la lógica que hay detrás de él. El detalle técnico completo (cómo regenerarlo,
qué contiene cada fichero) está en [`data/README.md`](../data/README.md);
aquí se explica el **razonamiento** — qué se decidió generar, por qué y cómo se
etiqueta cada caso.

No se usó ningún generador externo de datos sintéticos (no había disponible
ningún servidor MCP de ese tipo); todo se produce con un script Python propio,
determinista y sin dependencias (`data/generate_dataset.py`), lo que permite
regenerarlo, ampliarlo o ajustar su distribución en cualquier momento con un
solo comando.

## 2. Qué modela el dataset y por qué

Se planteó la tienda como un comercio generalista tipo Amazon/Costco ("se
vende de todo"), porque un dataset centrado en 3-4 categorías (como el
`seed.sql` original con electrónica, moda, electrodomésticos y libros)
no permite probar la variedad de reglas de negocio que un sistema de
devoluciones real necesita: exclusiones legales por higiene, productos
perecederos, personalización, garantía legal frente a devolución comercial,
recogida a domicilio de mercancía voluminosa, etc.

Por eso el dataset cubre **16 categorías de producto**, cada una con su propia
política de devolución (plazo, embalaje, recargo, estados aceptados) y su
propia casuística legal:

| Categoría | Plazo | Rasgo distintivo que aporta al dataset |
|---|---|---|
| Electrónica e Informática | 30 días | Garantía legal (3 años) vs. devolución comercial (30 días) |
| Electrodomésticos | 30 días | Recogida a domicilio, instalación, empotrados a medida |
| Moda y Complementos | 30 días | Ropa interior/bañadores excluidos por higiene |
| Calzado | 30 días | Caja como parte del producto, prueba solo en interior |
| Joyería y Relojería | 15 días | Plazo corto, piezas personalizadas, riesgo de fraude |
| Hogar y Decoración | 30 días | Artículos frágiles, lotes/sets |
| Muebles | 14 días | Plazo corto, colchones (higiene), montaje |
| Jardinería y Bricolaje | 30 días | Plantas vivas y químicos: exclusión legal de perecederos |
| Juguetes | 30 días (60 en Navidad) | Estacionalidad, seguridad infantil |
| Bebé y Puericultura | 30 días | Sillas de coche tras accidente, biberones/chupetes |
| Deportes y Aire Libre | 30 días | Bicicletas con revisión técnica obligatoria |
| Cosmética y Perfumería | 21 días | Exclusión legal de higiene "de libro" (precinto roto) |
| Droguería, Higiene y Salud | 21 días | Igual que cosmética + dispositivos médicos (garantía) |
| Alimentación y Gran Consumo | 14 días | Perecederos excluidos por ley, alérgenos |
| Mascotas | 21 días | Alimento abierto no reembolsable |
| Libros, Papelería y Oficina | 21 días | Contenido digital canjeado, consumibles abiertos |

Estas 16 políticas están redactadas como documentos markdown extensos
(~700-1100 palabras cada una) en [`data/policies/`](../data/policies/),
más un documento de marco general
([`00_marco_general_devoluciones.md`](../data/policies/00_marco_general_devoluciones.md))
con el fundamento legal común: derecho de desistimiento de 14 días naturales
(TRLGDCU / Directiva 2011/83/UE), las excepciones legales tasadas del
artículo 103 (higiene, perecederos, personalización, contenido digital), y las
reglas de decisión que debe seguir el Agente Evaluador (sección 5, ver punto 4
de este resumen). En conjunto son ~15.000 palabras: suficiente volumen para
que trocearlas en chunks de ~300-500 tokens y vectorizarlas en
`policy_embeddings` tenga sentido real, en vez de un texto simbólico de una
sola frase por categoría.

Estos mismos documentos son el contenido literal que se inserta en
`return_policies.policy_text`, de modo que la documentación "fuente" (legible,
versionada en git) y el dato cargado en Supabase para el RAG son siempre
idénticos.

## 3. Volumen generado

| Entidad | Cantidad |
|---|---|
| Clientes | 320 |
| Productos (16 categorías) | 196 |
| Pedidos | 1.100 |
| Líneas de pedido | ~2.400 |
| Solicitudes de devolución | 480 |
| Líneas de devolución | ~540 |
| Clientes marcados como "devolvedores frecuentes" | 16 |
| Conversaciones de chat sintéticas (`chat_sessions`) | 140 (765 mensajes) |

Las cifras exactas de la última ejecución están en
[`data/GENERATION_STATS.md`](../data/GENERATION_STATS.md).

## 4. La explicación clave: cómo se etiqueta cada devolución

Esto es lo más importante del dataset y responde directamente a la petición
del profesor. Cada una de las 480 solicitudes de devolución no recibe una
etiqueta al azar: se genera con parámetros aleatorios (categoría, motivo,
estado del artículo, días desde la entrega, importe) y **después se clasifica
aplicando el mismo razonamiento que debería seguir el futuro Agente Evaluador
de Políticas**, siguiendo la sección 5 del documento de marco general:

1. **`invalid` (rechazo automático)** si ocurre cualquiera de:
   - El plazo se ha superado por **más de 5 días** sobre el máximo de la
     categoría (p. ej. un mueble devuelto a los 40 días con plazo de 14).
   - El artículo se devuelve por cambio de opinión, en una categoría sujeta a
     exclusión legal de higiene o perecederos (cosmética, droguería, bebé,
     alimentación, mascotas), habiendo roto el precinto o consumido el
     producto — con independencia de que falten muchos días para el límite.
   - El estado del artículo no está entre los admitidos por la política y el
     motivo es imputable al cliente (no a Mercadia).

2. **`human_review` (HITL obligatorio)** si, no siendo inválido, ocurre
   cualquiera de:
   - El **importe a reembolsar supera 100 €** — el umbral fijo de la
     plataforma que ya recoge `doc/guia.md` (Épica 2, US 2.5).
   - La solicitud cae en la **zona frontera del plazo** (entre 2 días antes y
     5 días después del límite de la categoría).
   - El motivo es especialmente sensible: `allergic_reaction` o
     `counterfeit_suspicion`.
   - El cliente pertenece al grupo de "devolvedores frecuentes" (posible
     patrón de abuso / *wardrobing*).
   - Falta evidencia fotográfica exigible para el motivo declarado.

3. **`valid` (aprobación automática)** en el resto de casos: dentro de plazo,
   estado admitido, importe ≤ 100 € y sin motivo sensible.

Esta lógica está implementada en la función `classify_case()` de
[`data/generate_dataset.py`](../data/generate_dataset.py) y es la razón
por la que el dataset es útil como *golden dataset*: cada fila trae ya la
decisión "correcta" esperada y la justificación en texto (`rationale`), lista
para comparar contra lo que decida el agente real cuando se implemente.

Distribución resultante (realista, no forzada a tercios iguales):

| Etiqueta | % aprox. | Lectura |
|---|---|---|
| `valid` | ~27% | Aprobación automática |
| `invalid` | ~28% | Rechazo automático |
| `human_review` | ~45% | Deriva a HITL |

Que casi la mitad de los casos legítimos acabe en revisión humana no es un
defecto del dataset: es el reflejo honesto de que, con un umbral fijo de
100 € y categorías de precio medio-alto (electrónica, muebles,
electrodomésticos, deportes), buena parte de las devoluciones reales
necesitaría ese HITL — que es exactamente el comportamiento que el TFM quiere
demostrar y evaluar.

## 5. El golden dataset para evaluación (`eval_cases.csv`)

[`data/eval_cases.csv`](../data/eval_cases.csv) recoge las 480 solicitudes
en formato tabular: `order_number`, `category`, `reason_category`,
`max_return_days`, `days_since_delivery`, `refund_amount`, `expected_label`
(`valid` / `invalid` / `human_review`) y `rationale`. Sirve para:

- Medir la precisión de la lógica determinista del futuro Agente Evaluador
  comparando su decisión contra `expected_label`.
- Ampliar el "Golden Dataset de 15 consultas" que `doc/guia.md` prevé en la
  Épica 5 (evaluación RAGAS / faithfulness) — aquí hay 480 casos en vez de 15;
  se puede tomar un subconjunto representativo (p. ej. 3-4 por categoría,
  cubriendo las tres etiquetas) para ese golden dataset reducido.

Cada `return_requests.notes` generado lleva además un prefijo
`[CASE:VALID]` / `[CASE:INVALID]` / `[CASE:HUMAN_REVIEW]` seguido de la misma
justificación, de forma que el dataset es auto-explicativo consultando
directamente la tabla en Supabase, sin tener que cruzar con el CSV.

## 6. Conversaciones sintéticas y texto libre variado

Dos mejoras añadidas en una segunda pasada sobre el texto libre del dataset,
tras descartar el uso de un generador externo (ver más abajo):

- **Motivos de devolución con redacción variada**: en vez de una única frase
  fija por `reason_category`, hay entre 4 y 8 redacciones distintas por
  motivo (formal, coloquial, con alguna errata deliberada), elegidas al azar.
- **140 conversaciones sintéticas** (`chat_sessions`/`chat_messages`, 765
  mensajes) sobre una muestra aleatoria del 29% de las devoluciones (no todas
  a propósito: el valor de una conversación es mostrar el patrón de diálogo,
  no repetir 480 veces variaciones casi idénticas del mismo patrón),
  simulando el flujo Triaje → Evaluador → Resolución de `doc/guia.md`, con el
  veredicto real de cada caso en el mensaje de cierre del asistente. Cada
  sesión guarda en `metadata` el `return_request_id`, `order_number` y
  `expected_label` de la fila que ilustra, para poder cruzarlas sin
  ambigüedad. El detalle completo de qué cubre y qué no (distribución exacta
  por etiqueta, patrones de conversación no modelados) está en la sección
  "Qué queda fuera de este dataset" de
  [`data/README.md`](../data/README.md).

Se intentó primero usar el servidor MCP `awslabs.syntheticdata-mcp-server`
para esta ampliación, pero no fue posible conectarlo de forma estable en
Windows y, sobre todo, la propia documentación de AWS Labs indica que el
paquete está deprecado porque un asistente de IA ya cubre esa función.
También se revisaron datasets de Kaggle sobre devoluciones de e-commerce (con
la API real, usando credenciales), pero resultaron ser datasets tabulares de
Machine Learning (5 categorías, 4 motivos, sin texto de política alguno) más
limitados que lo que ya había en este proyecto. Por eso ambas mejoras se
implementaron directamente en `generate_dataset.py`.

## 7. Cómo usarlo

```bash
# Regenerar el dataset (determinista, misma semilla = mismos recuentos)
python data/generate_dataset.py
```

El resultado (`supabase/seed_synthetic.sql`) se carga como **complemento** a
`supabase/seed.sql` (no lo sustituye) sobre una base de datos ya migrada.
Detalle completo de carga y validaciones realizadas (integridad de claves
foráneas, fechas, unicidad, roles de `chat_messages`) en
[`data/README.md`](../data/README.md).
