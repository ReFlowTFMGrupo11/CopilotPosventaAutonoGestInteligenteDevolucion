# Política de Devoluciones — Cosmética y Perfumería

**Documento:** POL-CAT-012 | **Categoría interna:** `cosmetica_perfumeria`
**Complementa a:** [00_marco_general_devoluciones.md](00_marco_general_devoluciones.md)

## 1. Plazo y condiciones generales

Perfumes, maquillaje, cremas, cuidado facial y corporal, y productos de
peluquería disponen de un plazo de **21 días naturales** desde la entrega,
reducido respecto a otras categorías por el carácter perecedero relativo de
las fórmulas cosméticas una vez abiertas.

- **Embalaje original obligatorio**: sí, incluyendo el **precinto de higiene o
  celofán original intacto**.
- **Estados aceptados**: `unopened`, `defective`, `wrong_item`.
- **Recargo de reposición**: 0%.

## 2. Exclusión legal de higiene

Este es uno de los ejemplos más claros de la excepción legal del artículo 103
TRLGDCU: los productos de cosmética y perfumería **pierden el derecho de
desistimiento por cambio de opinión en el mismo momento en que se retira el
precinto de higiene**, con independencia de que falten muchos días para el
límite del plazo de 21 días. Esto incluye:

- Perfumes con el precinto de celofán retirado (aunque no se haya pulverizado
  el producto).
- Maquillaje testado directamente sobre la piel (labiales, máscaras de
  pestañas, bases de maquillaje).
- Cremas y productos en tarro cuyo precinto interior se haya retirado.

Solo se aceptan devoluciones de productos desprecintados por motivo
`defective` (por ejemplo, una crema que llega separada o con mal olor de
fábrica, un perfume cuyo pulverizador no funciona) o `wrong_item_shipped`.

## 3. Casuística específica

- **Reacciones alérgicas** (`allergic_reaction`): es un motivo frecuente y
  sensible en esta categoría. Una reacción alérgica **no se considera un
  defecto de fabricación** por sí sola (salvo que el producto no cumpla su
  composición declarada), por lo que, si el producto está desprecintado, la
  devolución no es automáticamente elegible bajo la política comercial
  estándar; sin embargo, se deriva **siempre a revisión humana** para valorar
  el caso desde una perspectiva de atención al cliente y posible incidencia de
  seguridad de producto, especialmente si el cliente aporta un informe médico
  o fotografías de la reacción cutánea.
- **Productos de edición limitada o descatalogados**: si el motivo es
  `defective` o `wrong_item_shipped`, se acepta devolución incluso sin
  posibilidad de reposición del stock, gestionándose como reembolso íntegro.
- **Sets de regalo con varios productos**: si uno de los productos del set
  está desprecintado y otro no, solo se puede rechazar/aceptar la devolución
  del set completo según el criterio más restrictivo (se trata como
  desprecintado a efectos de higiene).
- **Muestras y miniaturas de regalo incluidas en el pedido**: no tienen valor
  de reembolso individual y no es necesario devolverlas.

## 4. Casos que activan revisión humana (HITL)

- Cualquier reclamación de `allergic_reaction`, con independencia del importe.
- Productos desprecintados devueltos por `defective` sin fotografía clara del
  defecto.
- `refund_amount` > 100 €, frecuente en sets de perfumería premium.
- Solicitudes en el día 19–21 del plazo.

## 5. Ejemplos ilustrativos

- **Claramente válida**: crema facial entregada hace 5 días, precinto intacto,
  el cliente cambió de opinión (`changed_mind`) → aprobación automática (no
  desprecintado, sin problema de higiene).
- **Claramente inválida**: perfume desprecintado y usado durante 10 días,
  motivo `changed_mind` ("no me gusta el olor") → rechazo automático por
  exclusión legal de higiene.
- **Ambigua (HITL)**: crema corporal desprecintada, el cliente reporta
  enrojecimiento en la piel al segundo uso (`allergic_reaction`), sin informe
  médico pero con fotos → revisión humana obligatoria por tratarse de una
  posible incidencia de seguridad de producto.
