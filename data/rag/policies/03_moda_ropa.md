# Política de Devoluciones — Moda y Complementos

**Documento:** POL-CAT-003 | **Categoría interna:** `moda_ropa`
**Complementa a:** [00_marco_general_devoluciones.md](00_marco_general_devoluciones.md)

## 1. Plazo y condiciones generales

Ropa, camisetas, pantalones, vestidos, abrigos, complementos textiles (bufandas,
gorros, guantes), bolsos y mochilas disponen de **30 días naturales** desde la
entrega para su devolución o cambio de talla.

- **Embalaje original**: no es obligatorio conservar la bolsa o caja de envío,
  pero la prenda **debe conservar todas sus etiquetas originales** (etiqueta de
  composición y, cuando exista, precinto o etiqueta higiénica) y no debe
  presentar signos de haber sido lavada, planchada o llevada en la calle.
- **Estados aceptados**: `unopened`, `wrong_size`, `wrong_item`,
  `not_as_described`, `defective`.
- **Recargo de reposición**: 0%. Mercadia no aplica recargo de reposición en
  moda salvo deterioro evidente de la prenda no declarado por el cliente, en
  cuyo caso el caso se deriva a revisión humana para valorar un descuento sobre
  el reembolso.

## 2. Cambios de talla y color

El cambio de talla o color (`wrong_size`) es el motivo más habitual en esta
categoría y se gestiona de forma prioritaria: si hay stock disponible de la
talla o color solicitado, se ofrece cambio directo sin coste; si no hay stock,
se tramita como devolución con reembolso íntegro.

## 3. Casuística específica

- **Ropa interior, bañadores y ropa de baño**: quedan **excluidos del derecho de
  desistimiento por cambio de opinión** una vez retirada la etiqueta higiénica
  o el precinto de higiene, por motivos de salud pública. Se aceptan
  devoluciones de estos artículos solo si están `unopened` (etiqueta higiénica
  intacta) o por `defective`/`wrong_item_shipped`.
- **Prendas con etiqueta de "venta final" o de colecciones outlet/clearance**:
  algunas prendas en liquidación se marcan explícitamente como no devolvibles
  salvo defecto; esta condición debe figurar en la ficha del producto en el
  momento de la compra.
- **Prendas a medida o personalizadas** (grabado, bordado con nombre): excluidas
  del desistimiento por cambio de opinión, solo se aceptan por `defective` o
  error de confección respecto a lo solicitado.
- **Olor a perfume, humo o desodorante en la prenda devuelta**: se considera
  indicio de uso y puede motivar la aplicación de un recargo o el rechazo de la
  devolución si es muy intenso; se deriva a revisión humana para valorar el
  caso caso por caso.
- **Calidad percibida** (`quality_issue`, por ejemplo "la tela es más fina de lo
  que esperaba"): se admite como devolución por cambio de opinión dentro del
  plazo general, no como defecto, salvo que el cliente aporte evidencia de un
  defecto de confección objetivo (costuras rotas, tinte que mancha, etc.).

## 4. Casos que activan revisión humana (HITL)

- `refund_amount` > 100 €, frecuente en abrigos, chaquetas de piel/cuero y
  conjuntos completos.
- Prendas devueltas con signos de uso evidente (olor, manchas, deformación)
  cuyo motivo declarado es `wrong_size` o `changed_mind`.
- Clientes con una tasa de devolución superior al 50% de las prendas
  compradas en los últimos 90 días (patrón de *wardrobing*: comprar, usar una
  vez y devolver).
- Solicitudes en el día 28–30 del plazo.

## 5. Ejemplos ilustrativos

- **Claramente válida**: vestido de talla M devuelto a los 6 días, etiquetas
  puestas, sin usar, motivo `wrong_size` (pide talla S) → aprobación
  automática, cambio de talla o reembolso íntegro, importe bajo.
- **Claramente inválida**: bañador devuelto a los 20 días sin la etiqueta
  higiénica, motivo `changed_mind` → rechazo automático por exclusión legal de
  higiene, con independencia del plazo.
- **Ambigua (HITL)**: chaqueta de cuero de 220 €, devuelta en el día 29, con
  ligero olor a perfume, motivo declarado `wrong_size` → revisión humana por
  importe superior a 100 €, proximidad al límite del plazo e indicio leve de
  uso.
