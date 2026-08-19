# Política de Devoluciones — Juguetes

**Documento:** POL-CAT-009 | **Categoría interna:** `juguetes`
**Complementa a:** [00_marco_general_devoluciones.md](00_marco_general_devoluciones.md)

## 1. Plazo y condiciones generales

Juguetes, juegos de mesa, puzles, figuras coleccionables y videoconsolas de
juguete disponen de **30 días naturales** desde la entrega.

- **Campaña de Navidad**: los productos comprados entre el **1 de noviembre y
  el 24 de diciembre** disponen de un plazo ampliado hasta el **6 de enero**
  del año siguiente, para permitir la devolución de regalos navideños abiertos
  el día de Reyes.
- **Embalaje original obligatorio**: sí, incluyendo caja, instrucciones y
  todos los accesorios/piezas.
- **Estados aceptados**: `unopened`, `defective`, `wrong_item`,
  `not_as_described`.
- **Recargo de reposición**: 0%.

## 2. Casuística específica

- **Pilas y baterías incluidas**: si el juguete incluye pilas de fábrica y
  estas se han usado, las pilas **no se reembolsan** ni se sustituyen, aunque
  el juguete en sí sí sea devuelto con normalidad.
- **Juguetes electrónicos e interactivos**: siguen además las reglas de
  compatibilidad de electrónica (posibilidad de reinicio a valores de fábrica
  antes de la devolución si tienen memoria o perfiles guardados).
- **Seguridad infantil**: cualquier reclamación relacionada con un posible
  riesgo de seguridad (piezas pequeñas sueltas, astillas, olores químicos
  fuertes) se marca automáticamente con prioridad alta y se deriva a revisión
  humana, con independencia del importe, por la posible necesidad de retirar
  el lote de venta.
- **Juegos de mesa y puzles**: se aceptan devoluciones solo si todas las piezas
  están presentes; la falta de una pieza (`missing_parts`) declarada por el
  propio cliente no impide la devolución pero se registra para seguimiento de
  calidad del proveedor.
- **Figuras coleccionables selladas o de edición limitada**: si el precinto se
  retira, se considera "abierto" a efectos de reventa y puede aplicar un
  descuento sobre el valor de colección en el `refund_amount`, gestionado
  siempre mediante revisión humana.
- **Peluches y juguetes textiles**: se aceptan devoluciones por cambio de
  opinión salvo que se aprecien manchas o suciedad evidente de uso.

## 3. Casos que activan revisión humana (HITL)

- Cualquier reclamación de seguridad infantil, con independencia del importe.
- `refund_amount` > 100 €, habitual en videoconsolas de juguete y sets grandes
  de construcción.
- Devoluciones de figuras de colección desprecintadas.
- Solicitudes entre el 27 de diciembre y el 6 de enero (pico estacional que
  requiere revisión de volumen).

## 4. Ejemplos ilustrativos

- **Claramente válida**: set de construcción entregado el 15 de diciembre,
  devuelto el 3 de enero por no ser lo que el niño quería (`changed_mind`),
  caja intacta, piezas completas → aprobación automática (dentro del plazo
  ampliado de Navidad).
- **Claramente inválida**: peluche devuelto a los 70 días con manchas y olor a
  uso, motivo `changed_mind` → rechazo automático, plazo muy superado.
- **Ambigua (HITL)**: figura de colección de edición limitada devuelta en el
  día 25, precinto retirado "solo para comprobar el contenido", sin daños →
  revisión humana para valorar recargo por pérdida de valor de colección.
