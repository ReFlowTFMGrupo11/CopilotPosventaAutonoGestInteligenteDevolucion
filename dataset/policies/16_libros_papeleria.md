# Política de Devoluciones — Libros, Papelería y Oficina

**Documento:** POL-CAT-016 | **Categoría interna:** `libros_papeleria`
**Complementa a:** [00_marco_general_devoluciones.md](00_marco_general_devoluciones.md)

## 1. Plazo y condiciones generales

Libros, cómics, material de papelería, agendas, material de oficina y
consumibles de impresión disponen de un plazo de **21 días naturales** desde
la entrega.

- **Embalaje original**: no es obligatorio conservar el envoltorio de envío,
  pero el artículo debe estar en condiciones de reventa (sin subrayados,
  anotaciones ni páginas dañadas).
- **Estados aceptados**: `unopened`, `wrong_item`, `defective`.
- **Recargo de reposición**: 0%.

## 2. Casuística específica

- **Libros con código digital o contenido descargable incluido**: si el
  código de acceso al contenido digital (audiolibro, material complementario
  online) ha sido canjeado, el libro físico puede devolverse pero **sin
  derecho a reembolso de la parte correspondiente al contenido digital ya
  consumido**, calculado proporcionalmente sobre el precio de venta.
- **Defectos de imprenta** (`defective`): páginas en blanco, duplicadas,
  desordenadas o encuadernación defectuosa. Se acepta devolución con
  reembolso íntegro o sustitución por un ejemplar correcto, sin necesidad de
  aportar foto en casos evidentes de fallo de imprenta conocido (edición con
  errata masiva reportada por el proveedor).
- **Prensa, revistas y publicaciones periódicas**: excluidas del derecho de
  desistimiento por su propia naturaleza editorial, conforme a la excepción
  legal correspondiente; no se aceptan devoluciones salvo ejemplar dañado en
  el transporte.
- **Material de oficina consumible** (tóner, cartuchos de tinta, papel):
  se acepta devolución solo si el envase no ha sido abierto, dado que no
  puede garantizarse la integridad de un consumible ya manipulado.
- **Agendas y planificadores con fecha** (por ejemplo, agenda del curso
  2026/2027): pasado el año o curso de vigencia, pierden su utilidad
  comercial; Mercadia no acepta devoluciones por cambio de opinión una vez
  superado el 50% del periodo de vigencia de la agenda, aunque esté dentro
  del plazo general de 21 días.
- **Material escolar personalizado** (cuadernos con nombre grabado): excluido
  del desistimiento por cambio de opinión al ser un producto personalizado.

## 3. Casos que activan revisión humana (HITL)

- Reclamaciones de defecto de imprenta en tiradas ya identificadas como
  defectuosas (para evitar duplicar la revisión de casos ya conocidos, se
  revisa el primer lote y luego se automatiza).
- `refund_amount` > 100 €, poco frecuente pero posible en packs de material de
  oficina para empresas o colecciones completas de libros.
- Solicitudes de devolución de agendas o planificadores fechados cerca del
  50% de su periodo de vigencia.

## 4. Ejemplos ilustrativos

- **Claramente válida**: novela entregada hace 4 días con 40 páginas en
  blanco por error de encuadernación (`defective`) → aprobación automática,
  reembolso o sustitución.
- **Claramente inválida**: cartucho de tinta abierto y parcialmente usado,
  motivo `changed_mind` → rechazo automático, consumible abierto excluido.
- **Ambigua (HITL)**: pack de libros de texto de 130 €, devuelto en el día 20,
  uno de los libros presenta una anotación a lápiz que el cliente asegura
  venía de fábrica → revisión humana por importe y por duda sobre el estado
  real del artículo.
