# Política General de Devoluciones — Mercadia

**Documento:** POL-GEN-001
**Ámbito:** Aplicable a todos los pedidos realizados en Mercadia (España y Portugal), salvo excepciones específicas recogidas en la política de cada categoría de producto.
**Última revisión:** 2026-01-15
**Idioma original:** Español (ES)

Este documento describe las reglas comunes que rigen cualquier devolución en Mercadia,
con independencia de la categoría del artículo. Las políticas específicas de cada
categoría (electrónica, moda, alimentación, muebles, etc.) **añaden o restringen**
estas reglas generales; en caso de conflicto entre este documento y la política de
categoría, prevalece siempre la política de categoría por ser más específica, salvo
que sea menos favorable que el mínimo legal, en cuyo caso prevalece el mínimo legal
descrito en la sección 1.

## 1. Marco legal: derecho de desistimiento

Mercadia opera como plataforma de venta a distancia y, como tal, está sujeta al
Real Decreto Legislativo 1/2007, de 16 de noviembre, por el que se aprueba el texto
refundido de la Ley General para la Defensa de los Consumidores y Usuarios (TRLGDCU),
y a la normativa europea de protección al consumidor en ventas a distancia
(Directiva 2011/83/UE).

En virtud de este marco legal, todo cliente que actúe como consumidor tiene derecho a
**desistir del contrato durante 14 días naturales** desde la recepción del producto,
**sin necesidad de justificar el motivo** y sin más coste que el de la devolución
del producto (salvo que Mercadia asuma ese coste como mejora comercial, ver sección 4).
Este derecho de desistimiento legal es un **mínimo irrenunciable**: ninguna política de
categoría puede ofrecer un plazo inferior a 14 días naturales para clientes que
compren como consumidores finales dentro de la Unión Europea, salvo las excepciones
legales tasadas del artículo 103 TRLGDCU, que se detallan en la sección 2.

Mercadia **amplía comercialmente** este mínimo legal en la mayoría de categorías,
ofreciendo plazos de devolución de entre 14 y 30 días naturales según el tipo de
producto, tal y como se recoge en la tabla resumen de la sección 6 y en el documento
específico de cada categoría. Esta ampliación es una política comercial voluntaria y,
por tanto, Mercadia puede establecer condiciones adicionales (embalaje original,
estado del producto, recargo de reposición) que no se exigen para el ejercicio del
derecho de desistimiento legal estricto durante los primeros 14 días, siempre que esas
condiciones no vacíen de contenido el derecho legal (por ejemplo, no se puede denegar
un reembolso dentro de los 14 días solo por haber retirado el envoltorio exterior para
inspeccionar el producto, algo expresamente permitido por la ley).

## 2. Excepciones legales al derecho de desistimiento (art. 103 TRLGDCU)

Determinados productos están **excluidos por ley** del derecho de desistimiento, o
lo pierden en cuanto se rompe su precinto de seguridad o se manipulan de una forma
determinada. Estas excepciones se aplican con independencia de la política comercial
de Mercadia y se detallan por categoría, pero las más habituales son:

- Bienes precintados que no sean aptos para ser devueltos por razones de protección
  de la salud o de higiene y que hayan sido desprecintados tras la entrega
  (cosmética, perfumería, ropa interior, bañadores, artículos de puericultura como
  biberones o chupetes, auriculares intraauditivos, etc.).
- Bienes que puedan deteriorarse o caducar con rapidez (alimentación fresca,
  perecederos, plantas vivas).
- Bienes confeccionados conforme a especificaciones del consumidor o claramente
  personalizados (grabados, tallas especiales bajo pedido, muebles a medida).
- Contenido digital suministrado en soporte no material cuya ejecución haya
  comenzado con el acuerdo previo del consumidor (descargas de software, códigos
  digitales canjeados, licencias activadas).
- Precintos de seguridad de audio, vídeo o software informático que hayan sido
  desprecintados por el consumidor tras la entrega.
- Suministro de prensa, publicaciones periódicas o revistas.
- Bienes que, por su naturaleza, se mezclen de forma indisociable con otros
  artículos tras su entrega.

Estas exclusiones aparecen reflejadas de forma explícita en la ficha de cada
producto afectado y en la política de la categoría correspondiente.

## 3. Datos y evidencias necesarios para tramitar una devolución

Para iniciar cualquier devolución, Mercadia solicita:

1. **Número de pedido** (`order_number`) o identificador de pedido.
2. **Motivo de la devolución**, seleccionado de una lista cerrada de categorías de
   motivo (`reason_category`): `defective` (producto defectuoso), `wrong_item_shipped`
   (se envió un artículo distinto al pedido), `wrong_size` (talla o medida
   incorrecta), `not_as_described` (el producto no coincide con la descripción o
   fotos), `damaged_in_transit` (llegó dañado por el transporte), `missing_parts`
   (faltan piezas o accesorios), `changed_mind` (cambio de opinión, sin defecto),
   `duplicate_order` (pedido duplicado por error), `arrived_late` (llegó fuera de
   plazo y ya no se necesita), `better_price_found` (encontró mejor precio),
   `allergic_reaction` (reacción alérgica o intolerancia, típico en cosmética,
   droguería o alimentación), `quality_issue` (percepción de baja calidad sin
   defecto objetivo), `assembly_issue` (problemas de montaje o instalación),
   `incompatible` (incompatibilidad técnica con otro dispositivo o sistema) y
   `counterfeit_suspicion` (sospecha de producto no original).
3. **Estado físico del artículo** (`condition`): `unopened` (precintado, sin abrir),
   `opened_unused` (abierto pero sin usar), `opened_tested` (abierto y probado sin
   deterioro), `used` (usado más allá de lo razonable para comprobar su
   funcionamiento), `defective` (con un defecto de fabricación), `damaged`
   (dañado, típicamente por el transporte o mal uso) o `missing_parts` (incompleto).
4. **Fotografías** del defecto o daño cuando el motivo sea `defective`,
   `damaged_in_transit`, `not_as_described` o `missing_parts`.
5. Conservar el **embalaje original** cuando la categoría lo exija (ver columna
   `requires_original_packaging` en la tabla resumen de la sección 6).

La ausencia de fotografías cuando son exigibles, o la falta de embalaje original en
categorías que lo requieren, no impide **iniciar** la solicitud, pero sí puede motivar
que el caso se derive a **revisión manual** (ver sección 5) en lugar de resolverse de
forma automática.

## 4. Costes de la devolución y recargos de reposición (*restocking fee*)

- Cuando la devolución se debe a **causa imputable a Mercadia o al vendedor**
  (`defective`, `wrong_item_shipped`, `damaged_in_transit`, `missing_parts`,
  `not_as_described` cuando se verifica objetivamente), Mercadia **asume el coste
  íntegro del transporte de vuelta** y **no aplica ningún recargo de reposición**,
  reembolsando el 100% del importe pagado por los artículos afectados, incluidos los
  gastos de envío originales si el pedido completo se devuelve.
- Cuando la devolución se debe a **cambio de opinión del cliente**
  (`changed_mind`, `wrong_size` sin error de Mercadia, `better_price_found`,
  `quality_issue` sin defecto objetivo), el coste del transporte de vuelta corre a
  cargo del cliente salvo que la categoría indique lo contrario, y puede aplicarse
  el **recargo de reposición** (`restocking_fee_percent`) indicado en la política de
  categoría, siempre que el producto se devuelva abierto pero en condiciones
  razonables de reventa. Un producto devuelto en su embalaje original, sin abrir y
  con el precinto intacto, nunca lleva recargo de reposición.
- El recargo de reposición **nunca se aplica durante los primeros 14 días naturales**
  si el motivo demuestra un incumplimiento de Mercadia; solo se aplica a devoluciones
  voluntarias por cambio de opinión, y siempre debe quedar reflejado de forma clara
  en el importe final de reembolso (`refund_amount`) y en las notas del caso.

## 5. Aprobación automática, rechazo automático y revisión humana (HITL)

El sistema de agentes de Mercadia evalúa cada solicitud de forma determinista contra
la política de la categoría correspondiente. De forma orientativa:

- **Aprobación automática**: la solicitud cumple el plazo (`max_return_days`), el
  estado del artículo es uno de los permitidos (`allowed_conditions`) y, si se
  requiere embalaje original, este se conserva. El importe a reembolsar
  (`refund_amount`) es **igual o inferior a 100 €**.
- **Revisión humana obligatoria (Human-in-the-Loop, HITL)**: con independencia de
  que la solicitud sea, en principio, elegible, se deriva **siempre** a un
  administrador humano cuando ocurra cualquiera de estos supuestos:
  - El **importe a reembolsar supera los 100 €** (umbral fijo de la plataforma).
  - La fecha de entrega está **a menos de 3 días de distancia del límite del plazo**
    de devolución (caso límite / frontera), por ejemplo, una devolución solicitada
    el día 28 o 29 sobre una política de 30 días.
  - El cliente tiene un **historial de devoluciones inusualmente alto**: más de 3
    devoluciones aprobadas en los últimos 90 días, o una tasa de devolución superior
    al 50% de sus pedidos (posible indicio de *wardrobing* o uso indebido).
  - El motivo es `counterfeit_suspicion`, `allergic_reaction` con síntomas graves
    declarados, o cualquier incidente que pueda implicar responsabilidad de
    producto o riesgo para la salud.
  - Falta evidencia exigida (fotos de un defecto, embalaje original en una
    categoría que lo requiere) y el propio agente evaluador no puede determinar con
    certeza razonable si el caso es elegible.
  - El producto pertenece a una categoría con **excepciones legales de desistimiento**
    (sección 2) y existe duda razonable sobre si el precinto de higiene o seguridad
    se rompió antes o después de la entrega.
- **Rechazo automático**: el plazo se ha superado ampliamente (más de 5 días por
  encima del máximo permitido, es decir, fuera de cualquier zona de ambigüedad), el
  producto pertenece a una categoría/condición excluida por ley o por política
  (por ejemplo, alimentación perecedera consumida, cosmética desprecintada por
  cambio de opinión, ropa interior sin etiqueta higiénica) y no existe defecto
  objetivo demostrado, o el artículo devuelto no se corresponde con el pedido
  original.

Este umbral de 100 € y los criterios de frontera descritos arriba son los que debe
usar el Agente de Resolución para decidir cuándo pausar el flujo automático y generar
un caso pendiente de aprobación manual en el panel de administración.

## 6. Tabla resumen de plazos y condiciones por categoría

| Categoría | Plazo (días naturales) | Embalaje original obligatorio | Recargo de reposición | Notas breves |
|---|---|---|---|---|
| Electrónica e Informática | 30 | Sí | 15% si abierto y no defectuoso | Software desprecintado excluido |
| Electrodomésticos | 30 | Sí | 10% | Garantía legal 3 años aparte |
| Moda y Complementos | 30 | No | 0% | Ropa interior/bañadores excluidos si sin etiqueta higiénica |
| Calzado | 30 | Sí (caja) | 0% | Solo probado en interior |
| Joyería y Relojería | 15 | Sí | 0% | Piezas personalizadas/pendientes excluidos |
| Hogar y Decoración | 30 | No | 0% | — |
| Muebles | 14 | Sí | 10% si recogida a domicilio | Montado ≠ defectuoso |
| Jardinería y Bricolaje | 30 | Sí | 5% | Plantas vivas y químicos abiertos excluidos |
| Juguetes | 30 (60 en Navidad) | Sí | 0% | Pilas usadas no se reembolsan |
| Bebé y Puericultura | 30 | Sí | 0% | Biberones/chupetes/sacaleches excluidos si desprecintados |
| Deportes y Aire Libre | 30 | Sí | 5% | Bicicletas: revisión técnica obligatoria |
| Cosmética y Perfumería | 21 | Sí | 0% | Excluido si precinto roto sin defecto |
| Droguería, Higiene y Salud | 21 | Sí | 0% | Excluido si precinto roto sin defecto |
| Alimentación y Gran Consumo | 14 | Sí | 0% | Solo no perecedero sellado y no caducado |
| Mascotas | 21 | Sí | 0% | Alimento abierto excluido |
| Libros, Papelería y Oficina | 21 | No | 0% | Códigos digitales canjeados excluidos |

## 7. Reembolsos: plazos y método

- Una vez Mercadia recibe y verifica el artículo devuelto (o, en devoluciones
  aprobadas sin necesidad de devolver el producto físico, desde la aprobación),
  el reembolso se emite en un plazo máximo de **14 días naturales**, en
  cumplimiento del artículo 108 TRLGDCU.
- El reembolso se realiza siempre por el **mismo medio de pago** utilizado en la
  compra, salvo que el cliente acepte expresamente un vale o saldo a favor.
- En devoluciones parciales de un pedido con gastos de envío únicos, los gastos de
  envío solo se reembolsan si se devuelve el pedido completo o si el motivo es
  imputable a Mercadia.

## 8. Historial de devoluciones y prevención de abuso

Mercadia registra el historial completo de devoluciones de cada cliente
(`get_customer_return_history`) para que el Agente Evaluador pueda contextualizar
cada nueva solicitud. Patrones que activan una señal de alerta (no un rechazo
automático, sino un motivo adicional para revisión humana):

- Más de 3 devoluciones aprobadas en 90 días.
- Devoluciones recurrentes del mismo `reason_category` en pedidos distintos del
  mismo cliente (indicio de uso temporal del producto, *wardrobing*).
- Solicitudes de devolución de artículos de alto valor inmediatamente después de
  un evento (boda, viaje, evento deportivo) inferido por la fecha de compra y
  la categoría del producto.

## 9. Vigencia y versión de este documento

Esta política puede actualizarse sin previo aviso para adaptarse a cambios
normativos o comerciales. La versión vigente en el momento de realizar el pedido
es la aplicable a esa compra. Este documento y los documentos de categoría
asociados constituyen la base de conocimiento indexada en la tabla
`policy_embeddings` para su recuperación mediante búsqueda semántica (RAG).
