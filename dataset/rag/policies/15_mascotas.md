# Política de Devoluciones — Mascotas

**Documento:** POL-CAT-015 | **Categoría interna:** `mascotas`
**Complementa a:** [00_marco_general_devoluciones.md](00_marco_general_devoluciones.md)

## 1. Plazo y condiciones generales

Alimento para mascotas, accesorios (correas, comederos, transportines),
juguetes para mascotas, camas y productos de higiene animal disponen de un
plazo de **21 días naturales** desde la entrega.

- **Embalaje original obligatorio**: sí, el envase de pienso o snacks debe
  estar sellado y sin abrir.
- **Estados aceptados**: `unopened`, `defective`, `wrong_item`.
- **Recargo de reposición**: 0%.

## 2. Casuística específica

- **Alimento seco o húmedo para mascotas**: una vez abierto el envase, queda
  **excluido del desistimiento por cambio de opinión**, tanto por motivos de
  conservación como porque no puede garantizarse su correcto almacenamiento
  tras la apertura. Se acepta devolución de alimento abierto únicamente por
  `defective` (por ejemplo, presencia de moho, insectos o cuerpos extraños),
  con fotografía obligatoria.
- **Cambio de dieta no tolerada por la mascota**: si la mascota rechaza el
  alimento o presenta molestias digestivas tras probarlo, esto **no se
  considera un defecto de fabricación** y no da derecho a devolución del
  envase abierto salvo que se demuestre un problema de calidad del lote
  (en cuyo caso se deriva a revisión humana y posible aviso a control de
  calidad del proveedor).
- **Transportines y jaulas**: se acepta probarlos montándolos en casa; el uso
  con la mascota dentro durante un trayecto real (pelos, arañazos, olor) se
  considera uso más allá de la prueba razonable.
- **Camas y textiles para mascotas**: si se han usado con la mascota (pelos,
  manchas, olor), quedan excluidas del cambio de opinión por motivos de
  higiene, aceptándose solo por `defective`.
- **Collares, correas y arneses de seguridad**: si presentan un defecto de
  cierre o enganche que pueda suponer riesgo de fuga o accidente para el
  animal, se tratan con prioridad alta como `defective` con posible aviso de
  seguridad al resto de clientes que compraron el mismo lote.

## 3. Casos que activan revisión humana (HITL)

- Reclamaciones de calidad de alimento con síntomas en la mascota
  (`allergic_reaction` / `defective`), por la sensibilidad del caso y la
  posible necesidad de contactar al proveedor.
- Reclamaciones de defecto de seguridad en collares, correas o arneses.
- `refund_amount` > 100 €, posible en jaulas grandes, transportines
  homologados para viaje o packs grandes de alimento premium.

## 4. Ejemplos ilustrativos

- **Claramente válida**: transportín entregado hace 5 días con el cierre roto
  de fábrica (`defective`), foto aportada → aprobación automática si el
  importe es ≤100 €.
- **Claramente inválida**: saco de pienso de 15 kg abierto y usado durante 3
  semanas, motivo `changed_mind` (a la mascota no le gustó el sabor) →
  rechazo automático, alimento abierto excluido del desistimiento.
- **Ambigua (HITL)**: pienso abierto tras el cual el cliente reporta que su
  perro tuvo vómitos ocasionales, sin informe veterinario ni fotos del
  producto → revisión humana para valorar si procede reembolso por posible
  problema de calidad del lote.
