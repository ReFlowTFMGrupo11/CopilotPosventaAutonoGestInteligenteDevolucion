# Política de Devoluciones — Electrodomésticos

**Documento:** POL-CAT-002 | **Categoría interna:** `electrodomesticos`
**Complementa a:** [00_marco_general_devoluciones.md](00_marco_general_devoluciones.md)

## 1. Plazo y condiciones generales

Grandes electrodomésticos (frigoríficos, lavadoras, lavavajillas, hornos,
congeladores) y pequeño electrodoméstico (batidoras, tostadoras, aspiradoras,
cafeteras, planchas, freidoras de aire) disponen de **30 días naturales** desde
la entrega para su devolución.

- **Embalaje original obligatorio**: sí. En grandes electrodomésticos, además,
  el producto debe estar **desinstalado** y en condiciones de ser transportado
  de forma segura (sin restos de agua, sin conexiones eléctricas o de gas
  activas) en el momento de la recogida.
- **Estados aceptados**: `unopened`, `defective`, `wrong_item`,
  `damaged_in_transit`, `missing_parts`.
- **Recargo de reposición**: 10% del precio si se devuelve por cambio de
  opinión habiéndose desprecintado y probado el aparato. No se aplica si el
  motivo es `defective`, `wrong_item_shipped`, `damaged_in_transit` o
  `missing_parts`.

## 2. Garantía legal vs. devolución comercial

Al igual que en electrónica, los electrodomésticos tienen una **garantía legal
de conformidad de 3 años** independiente del plazo comercial de devolución de
30 días. Una avería que aparece en el mes 8 de uso no se gestiona como
devolución sino como incidencia de garantía (reparación o sustitución por el
fabricante o servicio técnico autorizado), fuera del flujo de devoluciones
automatizado.

## 3. Casuística específica

- **Instalación y montaje**: Mercadia ofrece instalación opcional de pago para
  grandes electrodomésticos (encimeras, hornos empotrados). Si el
  electrodoméstico fue instalado por un técnico de Mercadia y el defecto se
  detecta durante la propia instalación, el motivo se clasifica como
  `defective` con responsabilidad de Mercadia y sin recargo, incluso si han
  pasado más de 30 días desde la entrega física original (se toma como
  referencia la fecha de instalación).
- **Electrodomésticos empotrables o a medida**: si el cliente solicitó cortes
  o adaptaciones específicas para su cocina, el producto se considera
  personalizado y **queda excluido** del derecho de desistimiento por cambio de
  opinión, aceptándose devolución solo por `defective` o `wrong_item_shipped`.
- **Higiene en pequeño electrodoméstico de cocina**: aparatos que entran en
  contacto directo con alimentos (batidoras, robots de cocina, freidoras)
  aceptan devolución por cambio de opinión solo si están `unopened`; una vez
  usados para cocinar, solo se aceptan por `defective` o `wrong_item`.
- **Consumo eléctrico y pruebas de funcionamiento**: probar un electrodoméstico
  durante un ciclo completo razonable (por ejemplo, un lavado de prueba) no
  invalida la devolución; un uso continuado de varias semanas sí puede
  considerarse uso indebido y derivar a revisión humana.
- **Recogida a domicilio**: obligatoria para electrodomésticos de gran formato;
  el cliente debe estar presente en la franja horaria acordada. Una recogida
  fallida por ausencia injustificada del cliente en 2 ocasiones puede conllevar
  el cierre de la solicitud sin reembolso hasta nueva gestión.

## 4. Casos que activan revisión humana (HITL)

- `refund_amount` > 100 €, habitual en frigoríficos, lavadoras, hornos y
  aspiradoras robot de gama alta.
- Devoluciones de electrodomésticos con `missing_parts` en pedidos de más de
  300 € (posible pieza de alto coste, como un compresor o motor).
- Solicitudes entre el día 26 y 30 del plazo.
- Clientes con 2 o más devoluciones de electrodomésticos de gran formato en
  6 meses (coste logístico elevado, requiere validación humana).

## 5. Ejemplos ilustrativos

- **Claramente válida**: aspiradora robot entregada hace 5 días que no carga
  ni enciende desde el primer uso (`defective`), con vídeo demostrativo,
  embalaje conservado → aprobación (revisión humana si supera 100 €, que es lo
  habitual en este tipo de producto).
- **Claramente inválida**: solicitud de devolución de una freidora de aire
  entregada hace 90 días, usada a diario, motivo `changed_mind` → rechazo
  automático, plazo ampliamente superado.
- **Ambigua (HITL)**: lavadora entregada hace 29 días, el cliente indica que
  "hace más ruido de lo esperado" sin poder acreditar avería objetiva, aparato
  ya instalado y usado varias veces → revisión humana por proximidad al límite
  del plazo y motivo subjetivo no verificable automáticamente.
