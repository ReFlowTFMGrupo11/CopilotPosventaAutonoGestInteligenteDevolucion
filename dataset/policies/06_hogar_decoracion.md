# Política de Devoluciones — Hogar y Decoración

**Documento:** POL-CAT-006 | **Categoría interna:** `hogar_decoracion`
**Complementa a:** [00_marco_general_devoluciones.md](00_marco_general_devoluciones.md)

## 1. Plazo y condiciones generales

Menaje de cocina, textil hogar (sábanas, cortinas, alfombras), decoración,
iluminación, vajilla, cristalería y organización del hogar disponen de
**30 días naturales** desde la entrega.

- **Embalaje original**: no es obligatorio conservar la caja de envío, pero el
  artículo debe estar completo, sin roturas ni piezas faltantes, y en
  condiciones de reventa.
- **Estados aceptados**: `unopened`, `opened_unused`, `defective`, `wrong_item`,
  `damaged_in_transit`.
- **Recargo de reposición**: 0%.

## 2. Casuística específica

- **Vajilla, cristalería y artículos frágiles**: los daños detectados en el
  momento de la entrega (`damaged_in_transit`) deben notificarse idealmente en
  las primeras 48 horas, aunque se admite el motivo dentro de todo el plazo de
  30 días si el cliente aporta fotografías del embalaje y del artículo dañado.
- **Textil hogar de higiene íntima** (fundas de almohada, sábanas bajeras):
  aceptan devolución por cambio de opinión solo si están `unopened`, dado el
  carácter de artículo de contacto textil prolongado; una vez lavadas o usadas,
  solo se aceptan por `defective`.
- **Velas, difusores y artículos con fragancia**: si el precinto o film
  protector se retira, se considera "probado" a efectos de aceptación en
  cambio de opinión, aunque no está sujeto a exclusión legal de higiene
  estricta como sí ocurre en cosmética.
- **Muebles pequeños de decoración** (estanterías bajas, mesas auxiliares
  ligeras vendidas en esta categoría y no en "Muebles"): si requieren montaje,
  el hecho de haberlos montado no invalida la devolución por cambio de
  opinión, pero el cliente debe desmontarlos con cuidado para el transporte de
  vuelta; daños producidos durante el desmontaje corren a cargo del cliente.
- **Sets y lotes** (por ejemplo, vajilla de 12 piezas): se puede devolver el
  lote completo o solo las piezas dañadas si el motivo es `defective` o
  `damaged_in_transit`; para `changed_mind` se exige la devolución del lote
  completo tal y como se vendió.

## 3. Casos que activan revisión humana (HITL)

- `refund_amount` > 100 €, frecuente en alfombras grandes, lámparas de diseño y
  sets de menaje premium.
- Reclamaciones de `damaged_in_transit` notificadas cerca del final del plazo
  de 30 días (mayor dificultad para verificar que el daño no es de uso).
- Devoluciones parciales de lotes con más de 90 días desde la compra.

## 4. Ejemplos ilustrativos

- **Claramente válida**: juego de sartenes entregado hace 12 días con una de
  ellas deformada de fábrica (`defective`), foto aportada → aprobación
  automática si el importe es ≤100 €.
- **Claramente inválida**: alfombra devuelta a los 95 días con manchas y olor a
  humedad, motivo `changed_mind` → rechazo automático, plazo muy superado y
  evidencia de uso prolongado.
- **Ambigua (HITL)**: lámpara de diseño de 150 €, devuelta en el día 30 exacto,
  embalaje original ausente pero producto en buen estado, motivo `changed_mind`
  → revisión humana por importe y por ser el último día del plazo.
