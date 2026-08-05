# Política de Devoluciones — Muebles

**Documento:** POL-CAT-007 | **Categoría interna:** `muebles`
**Complementa a:** [00_marco_general_devoluciones.md](00_marco_general_devoluciones.md)

## 1. Plazo y condiciones generales

Sofás, mesas, sillas, armarios, camas, colchones y muebles de exterior disponen
de un plazo de **14 días naturales** desde la entrega, coincidente con el
mínimo legal de desistimiento, dado el elevado coste logístico de la recogida
a domicilio de mercancía voluminosa.

- **Embalaje original obligatorio**: sí, siempre que sea posible reutilizarlo
  para el transporte de vuelta; en caso de mueble ya montado, debe desmontarse
  siguiendo el manual original antes de la recogida.
- **Estados aceptados**: `unopened`, `defective`, `damaged_in_transit`,
  `wrong_item`.
- **Recargo de reposición**: 10% en devoluciones por cambio de opinión que
  requieran recogida a domicilio de un mueble ya montado, para cubrir el coste
  logístico de recogida especializada. No se aplica si el motivo es
  `defective`, `damaged_in_transit` o `wrong_item_shipped`.

## 2. Colchones: excepción de higiene

Los **colchones y almohadas** siguen una regla especial dentro de esta
categoría: se aceptan devoluciones por cambio de opinión únicamente si
conservan la funda protectora de plástico original **sin retirar**. Una vez
retirada la funda protectora y usado el colchón, el artículo queda excluido
del desistimiento por cambio de opinión por motivos de higiene, salvo defecto
de fabricación demostrado (deformación, muelles rotos, etc.), en cuyo caso sí
se acepta con foto o vídeo del defecto.

## 3. Casuística específica

- **Montaje ya realizado**: el hecho de que el cliente haya montado el mueble
  para comprobarlo no invalida por sí solo la devolución, pero incrementa el
  coste logístico y por ello activa el recargo del 10% salvo que el motivo sea
  imputable a Mercadia.
- **Muebles a medida o con tapicería personalizada**: excluidos del
  desistimiento por cambio de opinión al ser productos confeccionados según
  especificaciones del cliente (color de tela, dimensiones especiales).
- **Daños estructurales detectados tras el montaje** (por ejemplo, una pata de
  mesa que se rompe al primer uso normal): se clasifican como `defective`,
  incluso si el defecto no era visible en el embalaje.
- **Muebles de exterior/jardín**: si se han usado en exterior expuestos a la
  intemperie (lluvia, sol directo prolongado) antes de solicitar la
  devolución, se considera uso más allá de lo razonable y se deriva a revisión
  humana.
- **Recogida fallida**: si el transportista no puede acceder al domicilio
  (mueble ya montado que no cabe por hueco de escalera/ascensor), el caso se
  deriva a revisión humana para acordar una solución alternativa (desmontaje
  guiado, compensación parcial, etc.).

## 4. Casos que activan revisión humana (HITL)

- `refund_amount` > 100 €, lo que incluye prácticamente cualquier mueble
  relevante (sofás, camas, mesas de comedor).
- Colchones sin funda protectora y sin defecto claramente demostrado.
- Solicitudes en el día 12–14 del plazo (ventana muy estrecha, similar a
  joyería).
- Incidencias de recogida fallida o acceso al domicilio.

## 5. Ejemplos ilustrativos

- **Claramente válida**: silla de oficina entregada hace 6 días con el
  mecanismo de altura roto de fábrica (`defective`), vídeo aportado →
  elegible, revisión humana si el importe supera 100 € (habitual en este tipo
  de producto).
- **Claramente inválida**: sofá devuelto a los 45 días, usado a diario,
  motivo `changed_mind` → rechazo automático, plazo muy superado.
- **Ambigua (HITL)**: colchón devuelto en el día 13, funda protectora retirada
  pero el cliente asegura no haber dormido en él más de una noche de prueba →
  revisión humana por la excepción de higiene y proximidad al límite del
  plazo.
