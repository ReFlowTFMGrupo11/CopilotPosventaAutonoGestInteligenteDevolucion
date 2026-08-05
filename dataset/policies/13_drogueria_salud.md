# Política de Devoluciones — Droguería, Higiene y Salud

**Documento:** POL-CAT-013 | **Categoría interna:** `drogueria_salud`
**Complementa a:** [00_marco_general_devoluciones.md](00_marco_general_devoluciones.md)

## 1. Plazo y condiciones generales

Productos de limpieza del hogar, higiene personal, cuidado bucodental,
parafarmacia (vitaminas, suplementos, primeros auxilios, ortopedia básica) y
pequeños dispositivos de salud (termómetros, tensiómetros) disponen de un
plazo de **21 días naturales** desde la entrega.

- **Embalaje original obligatorio**: sí, incluyendo precinto de seguridad e
  interior sellado cuando exista.
- **Estados aceptados**: `unopened`, `defective`, `wrong_item`.
- **Recargo de reposición**: 0%.

## 2. Exclusión legal de higiene

Al igual que en cosmética, la mayoría de productos de esta categoría entran en
contacto directo con la piel, mucosas o el cuerpo, por lo que **pierden el
derecho de desistimiento por cambio de opinión en cuanto se retira el precinto
de higiene**, con independencia del tiempo restante hasta el límite de 21
días. Esto incluye de forma destacada:

- Cepillos de dientes, cabezales de cepillo eléctrico y productos de higiene
  bucal desprecintados.
- Productos de higiene íntima.
- Termómetros y dispositivos que se insertan o aplican directamente sobre el
  cuerpo, una vez usados.
- Suplementos y vitaminas en frascos con precinto de seguridad retirado (por
  razones sanitarias, no se revenden productos de ingesta una vez
  manipulados).

Se aceptan devoluciones de productos desprecintados solo por `defective`
(por ejemplo, un tensiómetro que no enciende) o `wrong_item_shipped`.

## 3. Casuística específica

- **Productos de limpieza del hogar** (detergentes, lejía, desinfectantes): si
  el envase se abre y se usa parcialmente, se excluye del cambio de opinión;
  se acepta `unopened` o por `defective`/`wrong_item_shipped`. Los envases de
  productos químicos dañados durante el transporte que hayan derramado su
  contenido sobre otros artículos del pedido generan además una reclamación
  adicional por los artículos afectados.
- **Dispositivos médicos de uso doméstico** (tensiómetros, básculas de
  bioimpedancia, termómetros digitales): siguen además las reglas de garantía
  legal de 3 años de electrónica para defectos que aparezcan tras el plazo de
  devolución comercial.
- **Productos con caducidad corta** (algunos suplementos, cremas
  dermatológicas): si el producto llega con una fecha de caducidad inferior a
  3 meses desde la entrega sin haberlo indicado en la ficha, se acepta como
  `not_as_described` con reembolso íntegro, incluso si el precinto se ha
  retirado para comprobar la fecha.
- **Reacciones alérgicas** (`allergic_reaction`) a productos de higiene o
  parafarmacia: mismo tratamiento que en cosmética, siempre a revisión
  humana.

## 4. Casos que activan revisión humana (HITL)

- Cualquier reclamación de `allergic_reaction`.
- Productos desprecintados devueltos por `defective` sin evidencia clara.
- Reclamaciones de caducidad corta no indicada en la ficha del producto.
- `refund_amount` > 100 €, poco frecuente en esta categoría pero posible en
  packs grandes de parafarmacia o dispositivos médicos.

## 5. Ejemplos ilustrativos

- **Claramente válida**: tensiómetro entregado hace 4 días que no enciende
  (`defective`), precinto retirado solo para probarlo, foto/vídeo aportado →
  aprobación automática si el importe es ≤100 €.
- **Claramente inválida**: cepillo de dientes eléctrico devuelto tras 2
  semanas de uso, motivo `changed_mind` → rechazo automático por exclusión de
  higiene.
- **Ambigua (HITL)**: suplemento vitamínico desprecintado, el cliente reporta
  molestias digestivas leves (`allergic_reaction`) sin especificar más
  síntomas → revisión humana para valorar la incidencia y, en su caso,
  escalar a control de calidad del proveedor.
