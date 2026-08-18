# Política de Devoluciones — Deportes y Aire Libre

**Documento:** POL-CAT-011 | **Categoría interna:** `deportes_aire_libre`
**Complementa a:** [00_marco_general_devoluciones.md](00_marco_general_devoluciones.md)

## 1. Plazo y condiciones generales

Bicicletas, equipamiento de fitness, ropa técnica deportiva, tiendas de
campaña, material de camping, patinetes y equipamiento de pesca disponen de
**30 días naturales** desde la entrega.

- **Embalaje original obligatorio**: sí, incluyendo herramientas de montaje
  suministradas y manuales.
- **Estados aceptados**: `unopened`, `opened_tested`, `defective`,
  `wrong_item`.
- **Recargo de reposición**: 5% en devoluciones por cambio de opinión de
  artículos montados y probados (bicicletas, máquinas de fitness).

## 2. Casuística específica

- **Bicicletas**: se envían parcialmente montadas o en kit según el modelo. Se
  permite un montaje básico y una prueba de rodaje corta (uso "de
  comprobación") sin invalidar la devolución; un uso prolongado en ruta
  (desgaste de neumáticos, frenos, cadena engrasada por uso) se considera uso
  extendido. Toda devolución de bicicleta pasa por una **revisión técnica
  obligatoria** a su recepción para verificar que no se han modificado
  componentes de seguridad (frenos, dirección).
- **Ropa y calzado técnico deportivo**: sigue las reglas específicas de Moda y
  Calzado en cuanto a etiquetas e higiene, con la particularidad de que el uso
  en competición oficial (control antidopaje, marca de dorsal cosida) invalida
  la devolución por cambio de opinión.
- **Material de camping usado en una acampada real** (tienda de campaña con
  barro seco, saco de dormir con olor a humo de hoguera): se considera uso
  más allá de la prueba razonable y activa revisión humana para valorar
  recargo o rechazo parcial.
- **Equipamiento de fitness con contacto corporal directo** (esterillas,
  guantes de boxeo, protectores bucales): excluidos del cambio de opinión una
  vez usados, por motivos de higiene, salvo defecto.
- **Patinetes y monopatines eléctricos**: siguen además las reglas de batería
  de la categoría de Electrónica.

## 3. Casos que activan revisión humana (HITL)

- Todas las devoluciones de bicicletas, por la revisión técnica de seguridad
  obligatoria.
- `refund_amount` > 100 €, habitual en bicicletas, máquinas de fitness y
  patinetes eléctricos.
- Material de camping con evidencia de uso en exterior real.
- Solicitudes en el día 27–30 del plazo.

## 4. Ejemplos ilustrativos

- **Claramente válida**: cinta de correr entregada hace 9 días que no alcanza
  la velocidad máxima anunciada (`defective`), vídeo aportado → elegible,
  revisión humana si el importe supera 100 € (caso habitual en este producto).
- **Claramente inválida**: tienda de campaña devuelta a los 60 días con barro
  seco y olor a humo, motivo `changed_mind` → rechazo automático.
- **Ambigua (HITL)**: bicicleta devuelta en el día 26, con ligero desgaste en
  los neumáticos consistente con una prueba de rodaje moderada, motivo
  `changed_mind` → revisión humana (obligatoria además por la política de
  revisión técnica de bicicletas).
