# Política de Devoluciones — Electrónica e Informática

**Documento:** POL-CAT-001 | **Categoría interna:** `electronica_informatica`
**Complementa a:** [00_marco_general_devoluciones.md](00_marco_general_devoluciones.md)

## 1. Plazo y condiciones generales

Los productos de electrónica e informática (portátiles, sobremesa, monitores,
tablets, smartphones, auriculares, altavoces, componentes, periféricos, cámaras,
drones, televisores y pequeña electrónica) pueden devolverse en un plazo de
**30 días naturales** desde la fecha de entrega (`delivered_at`).

- **Embalaje original obligatorio**: sí, incluyendo caja, espuma protectora,
  cables, manuales y todos los accesorios originales. La ausencia de algún
  accesorio menor (por ejemplo, un cable USB) no invalida la devolución, pero
  puede aplicar un descuento proporcional al valor de mercado del accesorio
  faltante sobre el `refund_amount`.
- **Estados aceptados** (`allowed_conditions`): `unopened`, `opened_tested`,
  `defective`, `wrong_item`, `damaged_in_transit`.
- **Recargo de reposición**: 15% sobre el precio del artículo cuando se devuelve
  por cambio de opinión (`changed_mind`) habiéndose abierto el precinto y probado
  el dispositivo. Este recargo **no se aplica nunca** si el motivo es
  `defective`, `wrong_item_shipped` o `damaged_in_transit`, ni si el artículo se
  devuelve `unopened` con el precinto intacto.

## 2. Garantía legal frente a devolución comercial

Es fundamental distinguir dos conceptos que los clientes suelen confundir:

- **Devolución comercial** (esta política): plazo de 30 días para desistir de la
  compra o solicitar el cambio, con o sin defecto.
- **Garantía legal de conformidad**: 3 años desde la entrega (art. 120 TRLGDCU
  para bienes de consumo) para defectos de fabricación que aparezcan durante ese
  periodo. Transcurridos los 30 días de devolución comercial, un defecto de
  fabricación **no se gestiona como devolución** sino como **incidencia de
  garantía**, con reparación, sustitución o reembolso según corresponda, y no
  está sujeto al umbral de 100 € de revisión humana descrito en la política
  general, sino a un flujo de garantía independiente (fuera del alcance del
  Agente de Resolución de devoluciones en este MVP).

## 3. Casuística específica

- **Software y licencias desprecintadas**: las licencias de software en caja
  física con precinto de seguridad, códigos de activación de videojuegos o
  tarjetas de contenido digital canjeadas quedan **excluidas del derecho de
  desistimiento** en cuanto se accede al código o se activa la licencia,
  conforme a la excepción legal de contenido digital iniciado con consentimiento
  previo del consumidor.
- **Baterías y dispositivos con batería integrada**: se aceptan devoluciones,
  pero si el motivo es `changed_mind` y la batería presenta signos de ciclos de
  carga superiores a los razonables para una prueba de producto (uso intensivo
  de varias semanas), el caso se deriva a revisión humana para valorar un
  recargo de reposición superior al estándar.
- **Auriculares intraauditivos y productos que entran en contacto con el oído**:
  quedan excluidos del desistimiento por cambio de opinión una vez retirado el
  precinto de higiene, salvo defecto de fabricación demostrado.
- **Productos reacondicionados o de segunda mano certificada**: mismo plazo de
  30 días, pero el recargo de reposición por cambio de opinión se eleva al 20%
  dado el menor margen de reventa.
- **Televisores y monitores de gran formato**: requieren fotografía del panel
  encendido mostrando cualquier píxel defectuoso o daño antes de aprobar la
  devolución por `defective`; el transporte de recogida debe programarse con
  transportista especializado en mercancía voluminosa.
- **Incompatibilidad técnica** (`incompatible`): frecuente en componentes de
  informática (RAM, tarjetas gráficas, fuentes de alimentación). Se acepta como
  motivo válido asimilable a `wrong_item` si el cliente aporta las
  especificaciones de su equipo y estas contradicen la ficha técnica publicada;
  en caso contrario, se trata como `changed_mind` con recargo de reposición.

## 4. Casos que activan revisión humana (HITL)

- Cualquier devolución de electrónica con `refund_amount` > 100 €, lo que en la
  práctica incluye la mayoría de portátiles, televisores, tablets de gama media
  y smartphones.
- Sospecha de `counterfeit_suspicion` en accesorios de marcas reconocidas
  vendidos por vendedores externos del marketplace.
- Solicitudes en el día 27–30 del plazo (zona de frontera).
- Clientes con más de 2 devoluciones de electrónica de alto valor en 90 días.

## 5. Ejemplos ilustrativos

- **Claramente válida**: portátil entregado hace 10 días, el cliente indica que
  la pantalla tiene una línea vertical desde el primer encendido (`defective`),
  aporta foto, embalaje original conservado → aprobación automática si el
  importe es ≤100 €, revisión humana si es superior (caso habitual en portátiles).
- **Claramente inválida**: solicitud de devolución de un smartphone entregado
  hace 65 días por cambio de opinión, sin defecto ni error de Mercadia → rechazo
  automático por superar ampliamente el plazo.
- **Ambigua (HITL)**: auriculares inalámbricos devueltos en el día 29 de 30,
  `opened_tested`, el cliente alega que "el sonido no le convence" (más cercano
  a `quality_issue`/`changed_mind` que a un defecto objetivo) → revisión humana
  por proximidad al límite del plazo y ambigüedad del motivo.
