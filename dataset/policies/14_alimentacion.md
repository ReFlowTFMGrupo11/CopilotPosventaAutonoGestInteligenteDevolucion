# Política de Devoluciones — Alimentación y Gran Consumo

**Documento:** POL-CAT-014 | **Categoría interna:** `alimentacion`
**Complementa a:** [00_marco_general_devoluciones.md](00_marco_general_devoluciones.md)

## 1. Plazo y condiciones generales

Productos de alimentación no perecedera y gran consumo (conservas, pasta,
arroz, aceite, bebidas, snacks, productos de despensa, lotes de gran formato
tipo "gran consumo") disponen de un plazo **reducido de 14 días naturales**
desde la entrega, el más corto junto con muebles, dado el carácter
perecedero relativo incluso de productos envasados de larga duración.

- **Embalaje original obligatorio**: sí, el envase debe estar **sellado y sin
  abrir**, y el producto no debe haber superado su fecha de consumo
  preferente o caducidad en el momento de la devolución.
- **Estados aceptados**: `unopened`, `defective`, `wrong_item`.
- **Recargo de reposición**: 0%.

## 2. Exclusión legal de perecederos

Los alimentos **frescos, refrigerados o congelados** (frutas, verduras,
carnes, pescados, lácteos frescos, productos de panadería del día) están
**excluidos por completo del derecho de desistimiento**, al tratarse de
bienes que se deterioran o caducan con rapidez. Estos productos **solo
admiten reclamación** por:

- `defective` / `damaged_in_transit`: el producto llega en mal estado,
  fuera de cadena de frío, con el envase roto o con signos evidentes de
  descomposición. Requiere fotografía obligatoria tomada en el momento de la
  recepción o dentro de las 24 horas siguientes.
- `wrong_item_shipped`: se envió un producto distinto al pedido.

No se admite en ningún caso la devolución de alimentos frescos por
`changed_mind`, ni la devolución física del producto una vez abierto o
parcialmente consumido; en estos casos se gestiona, si procede, como
reembolso sin necesidad de devolución física, dado que no tiene sentido
logístico ni sanitario recuperar el artículo.

## 3. Casuística específica

- **Alimentación no perecedera sellada**: se acepta devolución por cambio de
  opinión únicamente si el envase original está intacto, sin abrir, y con al
  menos 2 meses de vigencia hasta su fecha de consumo preferente en el
  momento de la devolución.
- **Lotes de gran consumo** (packs multiunidad tipo "ahorro"): se puede
  devolver el lote completo sin abrir; si una sola unidad del lote está
  defectuosa, se gestiona la reposición o reembolso de esa unidad sin
  necesidad de devolver el resto.
- **Bebidas alcohólicas**: siguen la regla general de no perecederos, con el
  requisito adicional de verificación de mayoría de edad ya realizada en el
  momento de la compra; no se aceptan devoluciones de botellas abiertas salvo
  defecto (corcho roto, oxidación evidente).
- **Alérgenos e intolerancias** (`allergic_reaction`): si el etiquetado de
  alérgenos era incorrecto o incompleto respecto a la normativa de
  información alimentaria, se acepta como `not_as_described` con reembolso
  íntegro sin necesidad de devolución física del producto, dado el riesgo
  sanitario de su manipulación. Se deriva siempre a revisión humana para
  documentar la incidencia y notificar, si procede, al proveedor.
- **Errores de picking en supermercado online** (`wrong_item_shipped`):
  frecuentes en pedidos de gran consumo con muchas referencias; se gestionan
  con reposición prioritaria en el siguiente pedido o reembolso, sin
  necesidad de devolver el producto erróneo si es perecedero.

## 4. Casos que activan revisión humana (HITL)

- Cualquier reclamación de `allergic_reaction` vinculada a etiquetado de
  alérgenos.
- Reclamaciones de productos frescos en mal estado notificadas más de 24
  horas después de la entrega (mayor dificultad para verificar la causa).
- `refund_amount` > 100 €, posible en pedidos grandes de gran consumo o
  bebidas premium.
- Sospecha de manipulación indebida de la cadena de frío por parte del propio
  cliente antes de la reclamación.

## 5. Ejemplos ilustrativos

- **Claramente válida**: pack de 12 latas de conservas entregado hace 3 días,
  sellado, el cliente decide que no lo necesita (`changed_mind`), fecha de
  consumo preferente a más de un año → aprobación automática.
- **Claramente inválida**: solicitud de devolución de fruta fresca por
  cambio de opinión, entregada hace 5 días → rechazo automático, categoría de
  perecedero excluida por ley del desistimiento.
- **Ambigua (HITL)**: lote de yogures refrigerados que, según el cliente,
  llegaron "a temperatura ambiente" pero la reclamación se envía 4 días
  después de la entrega, sin foto del momento de recepción → revisión humana
  por dificultad de verificar la causa real del posible corte de la cadena de
  frío.
