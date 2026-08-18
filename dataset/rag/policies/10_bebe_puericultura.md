# Política de Devoluciones — Bebé y Puericultura

**Documento:** POL-CAT-010 | **Categoría interna:** `bebe_puericultura`
**Complementa a:** [00_marco_general_devoluciones.md](00_marco_general_devoluciones.md)

## 1. Plazo y condiciones generales

Cochecitos, sillas de coche, cunas, tronas, biberones, chupetes, sacaleches y
ropa de bebé disponen de **30 días naturales** desde la entrega.

- **Embalaje original obligatorio**: sí, incluyendo manuales de instalación y
  todos los accesorios.
- **Estados aceptados**: `unopened`, `defective`, `wrong_item`.
- **Recargo de reposición**: 0%.

## 2. Exclusiones de higiene

Por motivos de salud pública, los siguientes artículos quedan **excluidos del
derecho de desistimiento por cambio de opinión** en cuanto se retira el
precinto de higiene, aceptándose devolución únicamente si están `unopened` o
por `defective`/`wrong_item_shipped`:

- Biberones, tetinas y chupetes.
- Sacaleches y accesorios de lactancia que entren en contacto directo con el
  cuerpo.
- Bañeras y orinales de bebé una vez usados.
- Ropa interior y bodies de bebé sin etiqueta higiénica.

## 3. Casuística específica

- **Sillas de coche**: es la casuística más sensible de esta categoría. Una
  silla de coche **involucrada en un accidente de tráfico**, aunque sea leve,
  **no puede devolverse ni revenderse** por motivos de seguridad, ya que su
  estructura interna puede haberse debilitado de forma no visible; en su
  lugar se gestiona como incidencia de seguro, fuera del flujo estándar de
  devoluciones. Si no ha habido accidente, siguen la regla general de 30 días.
- **Cochecitos y sillas de paseo**: se permite montarlos y probarlos en casa;
  el uso en exterior (ruedas con barro, desgaste de tapicería) más allá de una
  prueba puntual se considera uso extendido y puede derivar a revisión humana.
- **Cunas y muebles infantiles**: siguen además las reglas de montaje de la
  categoría de Muebles en lo relativo al desmontaje para la recogida.
- **Alimentación infantil** (leches de fórmula, potitos): se rige por la
  política de Alimentación (ver documento correspondiente), con plazo reducido
  y exigencia de sellado intacto.
- **Ropa de bebé de tallas muy pequeñas (recién nacido)**: dado el rápido
  cambio de talla, se admite cambio de talla incluso con la prenda lavada una
  vez, siempre que se conserve en buen estado.

## 4. Casos que activan revisión humana (HITL)

- `refund_amount` > 100 €, habitual en cochecitos, sillas de coche y cunas.
- Cualquier mención de accidente de tráfico en relación con una silla de coche.
- Cochecitos devueltos con desgaste visible de uso en exterior.
- Solicitudes en el día 27–30 del plazo.

## 5. Ejemplos ilustrativos

- **Claramente válida**: trona entregada hace 7 días con el mecanismo de
  reclinado roto de fábrica (`defective`), foto aportada → elegible, revisión
  humana si el importe supera 100 €.
- **Claramente inválida**: chupete devuelto sin el precinto de higiene,
  motivo `changed_mind` → rechazo automático por exclusión de higiene,
  independientemente del plazo.
- **Ambigua (HITL)**: silla de coche devuelta en el día 20, el cliente
  menciona de forma ambigua "un pequeño golpe con el coche" al explicar el
  motivo → revisión humana obligatoria para descartar que haya existido un
  accidente que invalide la reventa por seguridad.
