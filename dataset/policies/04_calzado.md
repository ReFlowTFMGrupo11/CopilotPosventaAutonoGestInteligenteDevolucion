# Política de Devoluciones — Calzado

**Documento:** POL-CAT-004 | **Categoría interna:** `calzado`
**Complementa a:** [00_marco_general_devoluciones.md](00_marco_general_devoluciones.md)

## 1. Plazo y condiciones generales

Zapatos, zapatillas deportivas, botas, sandalias y calzado infantil disponen de
**30 días naturales** desde la entrega para su devolución o cambio de talla.

- **Embalaje original obligatorio**: sí, incluyendo la **caja del calzado**, que
  se considera parte del producto (no un simple embalaje de envío). Una caja
  muy deteriorada, rota o con cinta adhesiva directamente sobre el calzado
  puede motivar un pequeño recargo o rechazo si impide la reventa.
- **Estados aceptados**: `unopened`, `wrong_size`, `defective`, `wrong_item`.
- **Recargo de reposición**: 0%, siempre que las suelas no muestren signos de
  haber sido usadas en el exterior.

## 2. Prueba del calzado

Se permite probar el calzado **en interior, sobre superficie limpia** (como se
haría en una tienda física) para comprobar talla y comodidad. Las suelas con
marcas de suciedad, desgaste o uso en exterior se consideran indicio de uso
más allá de la prueba razonable y motivan revisión humana para valorar un
posible recargo o rechazo parcial.

## 3. Casuística específica

- **Calzado deportivo técnico** (running, trail, fútbol con tacos): además de la
  prueba en interior, se permite un uso de prueba muy breve en superficie
  interior o césped artificial cubierto; el uso en competición o exterior
  invalida la devolución por cambio de opinión.
- **Calzado infantil**: dado el rápido cambio de talla en niños, se admite un
  plazo de cambio de talla ampliado a 45 días si el motivo es `wrong_size`.
- **Plantillas ortopédicas o personalizadas**: excluidas del desistimiento por
  cambio de opinión al ser un producto confeccionado a medida.
- **Pares incompletos o de tallas distintas por error de almacén**: se
  clasifican como `wrong_item_shipped`, con reposición prioritaria y sin coste.

## 4. Casos que activan revisión humana (HITL)

- `refund_amount` > 100 €, habitual en botas técnicas y calzado de marca premium.
- Devoluciones con caja dañada o ausente pero calzado en perfecto estado.
- Suelas con desgaste visible en solicitudes de `wrong_size` o `changed_mind`.
- Solicitudes en el día 27–30 (o 43–45 en calzado infantil).

## 5. Ejemplos ilustrativos

- **Claramente válida**: zapatillas de running devueltas a los 4 días, probadas
  solo en casa, caja intacta, motivo `wrong_size` → aprobación automática.
- **Claramente inválida**: botas de montaña devueltas a los 50 días con suela
  visiblemente desgastada y barro seco, motivo `changed_mind` → rechazo
  automático (plazo superado y evidencia de uso en exterior).
- **Ambigua (HITL)**: zapatillas de 130 €, devueltas en el día 28, caja algo
  deteriorada por el transporte, suelas limpias, motivo `wrong_size` →
  revisión humana por importe y proximidad al límite del plazo.
