-- =========================================================================
-- Dataset de PRUEBAS - CopilotPosventaAutonomoGestInteligenteDevolucion
-- Casos de prueba específicos para validar el flujo end-to-end del chat
-- =========================================================================
-- Este archivo contiene inserts mínimos pero suficientes para probar:
-- - Devoluciones VÁLIDAS (dentro de plazo, estado correcto, importe <= 100€)
-- - Devoluciones INVÁLIDAS (fuera de plazo, estado prohibido, etc)
-- - Devoluciones QUE REQUIEREN REVISIÓN HUMANA (>100€, motivo sensible, etc)

-- =========================================================================
-- STEP 1: CLIENTES
-- =========================================================================
INSERT INTO customers (id, email, full_name, phone, address) VALUES
('c001', 'juan.garcia@gmail.com', 'Juan García López', '+34612345670',
 '{"street": "Calle Mayor 10", "city": "Madrid", "postal_code": "28013", "country": "ES"}'::jsonb),

('c002', 'maria.lopez@gmail.com', 'María López Martínez', '+34612345671',
 '{"street": "Avenida Diagonal 100", "city": "Barcelona", "postal_code": "08018", "country": "ES"}'::jsonb),

('c003', 'pedro.ruiz@hotmail.com', 'Pedro Ruiz Fernández', '+34612345672',
 '{"street": "Plaza de la Constitución 5", "city": "Valencia", "postal_code": "46002", "country": "ES"}'::jsonb),

('c004', 'anna.silva@yahoo.es', 'Anna Silva García', '+34612345673',
 '{"street": "Paseo de la Paz 20", "city": "Sevilla", "postal_code": "41004", "country": "ES"}'::jsonb),

('c005', 'carlos.frequent@outlook.com', 'Carlos Frequent Returner', '+34612345674',
 '{"street": "Calle Nueva 15", "city": "Bilbao", "postal_code": "48005", "country": "ES"}'::jsonb);

-- =========================================================================
-- STEP 2: PRODUCTOS (2-3 por categoría de prueba)
-- =========================================================================
-- Electrónica e Informática
INSERT INTO products (id, sku, name, description, category, price, weight_kg) VALUES
('p001', 'ELEC-001', 'Nortek UltraBook 14" Ryzen 7', 'Portátil ligero con Ryzen 7', 'electronica_informatica', 749.99, 1.4),
('p002', 'ELEC-002', 'Vionix Smartphone Aurora 128GB', 'Smartphone AMOLED 6.5"', 'electronica_informatica', 399.99, 0.18);

-- Moda y Ropa
INSERT INTO products (id, sku, name, description, category, price, weight_kg) VALUES
('p003', 'MODA-001', 'Urbano Camiseta Algodón Orgánico', 'Camiseta 100% algodón', 'moda_ropa', 14.99, 0.15),
('p004', 'MODA-002', 'Nordic Wear Abrigo Parka', 'Abrigo parka impermeable', 'moda_ropa', 129.99, 1.1);

-- Calzado
INSERT INTO products (id, sku, name, description, category, price, weight_kg) VALUES
('p005', 'CALZ-001', 'StridePro Zapatillas Running', 'Zapatillas de running', 'calzado', 89.99, 0.7),
('p006', 'CALZ-002', 'Caminar Botas de Montaña', 'Botas impermeables', 'calzado', 119.99, 1.1);

-- Electrodomésticos
INSERT INTO products (id, sku, name, description, category, price, weight_kg) VALUES
('p007', 'ELDO-001', 'Frescor Frigorífico Combi 300L', 'Frigorífico No Frost', 'electrodomesticos', 549.99, 65),
('p008', 'ELDO-002', 'HomeLine Lavadora Carga Frontal', 'Lavadora 8kg', 'electrodomesticos', 379.99, 60);

-- Cosméticos (Higiene-sensitivos)
INSERT INTO products (id, sku, name, description, category, price, weight_kg) VALUES
('p009', 'COSM-001', 'Essenza Eau de Parfum Floral 90ml', 'Perfume floral', 'cosmetica_perfumeria', 59.99, 0.3),
('p010', 'COSM-002', 'PureSkin Crema Facial Antiedad', 'Crema con ácido hialurónico', 'cosmetica_perfumeria', 34.99, 0.15);

-- =========================================================================
-- STEP 3: POLÍTICAS DE DEVOLUCIÓN (una por categoría de prueba)
-- =========================================================================
INSERT INTO return_policies (id, category, max_return_days, requires_original_packaging, restocking_fee_percent, allowed_conditions, policy_text) VALUES

('pol001', 'electronica_informatica', 30, TRUE, 15.00,
 ARRAY['unopened', 'opened_tested', 'defective', 'wrong_item', 'damaged_in_transit'],
 'POLÍTICA DE DEVOLUCIÓN - Electrónica e Informática
Plazo: 30 días desde la entrega
Condiciones aceptadas: sin abrir, abierto pero sin usar, defectuoso, artículo equivocado, dañado en tránsito
Embalaje original: OBLIGATORIO
Recargo de reposición: 15% si está abierto
Exclusiones: productos sin usar pero con embalaje de seguridad roto (higiene/garantía)'),

('pol002', 'moda_ropa', 30, FALSE, 0.00,
 ARRAY['unopened', 'wrong_size', 'wrong_item', 'not_as_described', 'defective'],
 'POLÍTICA DE DEVOLUCIÓN - Moda y Ropa
Plazo: 30 días desde la entrega
Condiciones aceptadas: sin abrir, talla equivocada, artículo equivocado, no como se describe, defectuoso
Embalaje original: NO OBLIGATORIO
Recargo de reposición: 0%
Cambios: permitido sin coste si está en perfecto estado'),

('pol003', 'calzado', 30, TRUE, 0.00,
 ARRAY['unopened', 'wrong_size', 'defective', 'wrong_item'],
 'POLÍTICA DE DEVOLUCIÓN - Calzado
Plazo: 30 días desde la entrega
Condiciones aceptadas: sin abrir, talla equivocada, defectuoso, artículo equivocado
Embalaje original: RECOMENDADO
Recargo de reposición: 0%
Nota especial: Si está usado no se acepta'),

('pol004', 'electrodomesticos', 30, TRUE, 10.00,
 ARRAY['unopened', 'defective', 'wrong_item', 'damaged_in_transit', 'missing_parts'],
 'POLÍTICA DE DEVOLUCIÓN - Electrodomésticos
Plazo: 30 días desde la entrega
Condiciones aceptadas: sin abrir, defectuoso, artículo equivocado, dañado en tránsito, piezas faltantes
Embalaje original: OBLIGATORIO (para devolución completa)
Recargo de reposición: 10% si está usado'),

('pol005', 'cosmetica_perfumeria', 21, TRUE, 0.00,
 ARRAY['unopened', 'defective', 'wrong_item'],
 'POLÍTICA DE DEVOLUCIÓN - Cosmética y Perfumería
Plazo: 21 días desde la entrega
Condiciones aceptadas: SOLO sin abrir, defectuoso (defecto de fabricación), artículo equivocado
Embalaje original: OBLIGATORIO
Exclusión legal: Por razones de higiene y salud, NO SE ACEPTAN productos con el embalaje roto/abierto
(Art. 103 TRLGDCU - Protección del consumidor)');

-- =========================================================================
-- STEP 4: PEDIDOS
-- =========================================================================
INSERT INTO orders (id, customer_id, order_number, status, total_amount, shipping_address, ordered_at, delivered_at) VALUES

-- Pedido 1: Cliente c001, 2 productos, delivered hace 10 días
('o001', 'c001', 'ORD-2026-00001', 'delivered', 764.98,
 '{"street": "Calle Mayor 10", "city": "Madrid", "postal_code": "28013", "country": "ES"}'::jsonb,
 '2026-07-25 10:30:00+02', '2026-07-30 15:45:00+02'),

-- Pedido 2: Cliente c002, 1 producto ropa, delivered hace 5 días
('o002', 'c002', 'ORD-2026-00002', 'delivered', 144.98,
 '{"street": "Avenida Diagonal 100", "city": "Barcelona", "postal_code": "08018", "country": "ES"}'::jsonb,
 '2026-08-02 14:20:00+02', '2026-08-05 11:00:00+02'),

-- Pedido 3: Cliente c003, 1 zapato, delivered hace 8 días
('o003', 'c003', 'ORD-2026-00003', 'delivered', 89.99,
 '{"street": "Plaza de la Constitución 5", "city": "Valencia", "postal_code": "46002", "country": "ES"}'::jsonb,
 '2026-07-28 09:15:00+02', '2026-08-02 16:30:00+02'),

-- Pedido 4: Cliente c004, 1 producto caro electrodoméstico, delivered hace 3 días
('o004', 'c004', 'ORD-2026-00004', 'delivered', 549.99,
 '{"street": "Paseo de la Paz 20", "city": "Sevilla", "postal_code": "41004", "country": "ES"}'::jsonb,
 '2026-08-05 11:00:00+02', '2026-08-08 14:20:00+02'),

-- Pedido 5: Cliente c005 (frequent returner), 2 perfumes, delivered hace 2 días
('o005', 'c005', 'ORD-2026-00005', 'delivered', 94.98,
 '{"street": "Calle Nueva 15", "city": "Bilbao", "postal_code": "48005", "country": "ES"}'::jsonb,
 '2026-08-07 13:45:00+02', '2026-08-09 10:15:00+02'),

-- Pedido 6: Cliente c001 (para test inválido - fuera de plazo), delivered hace 60 días
('o006', 'c001', 'ORD-2026-00006', 'delivered', 399.99,
 '{"street": "Calle Mayor 10", "city": "Madrid", "postal_code": "28013", "country": "ES"}'::jsonb,
 '2026-06-10 08:00:00+02', '2026-06-15 12:30:00+02');

-- =========================================================================
-- STEP 5: LÍNEAS DE PEDIDO (order_items)
-- =========================================================================
-- Orden o001
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
('oi001', 'o001', 'p001', 1, 749.99, 749.99),
('oi002', 'o001', 'p003', 1, 14.99, 14.99);

-- Orden o002
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
('oi003', 'o002', 'p004', 1, 129.99, 129.99),
('oi004', 'o002', 'p003', 1, 14.99, 14.99);

-- Orden o003
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
('oi005', 'o003', 'p005', 1, 89.99, 89.99);

-- Orden o004
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
('oi006', 'o004', 'p007', 1, 549.99, 549.99);

-- Orden o005
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
('oi007', 'o005', 'p009', 1, 59.99, 59.99),
('oi008', 'o005', 'p010', 1, 34.99, 34.99);

-- Orden o006
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
('oi009', 'o006', 'p002', 1, 399.99, 399.99);

-- =========================================================================
-- STEP 6: SOLICITUDES DE DEVOLUCIÓN (return_requests)
-- =========================================================================
-- CASO 1: VÁLIDO - Dentro de plazo (5 días), estado correcto, importe bajo
INSERT INTO return_requests (id, order_id, customer_id, status, reason, reason_category, resolution, refund_amount, tracking_number, notes, created_at, resolved_at) VALUES
('ret001', 'o001', 'c001', 'approved',
 'El portátil que me llegó no enciende, parece un fallo de fábrica',
 'defective', 'full_refund', 749.99, 'RET-0001ABC',
 '[CASE:VALID] Aprobado automáticamente. Solicitud dentro de plazo (5 de 30 días), estado aceptado (defective), importe 749.99€ requiere revisión pero la causa es fabricación.',
 '2026-07-30 16:30:00+02', '2026-08-01 09:00:00+02');

-- CASO 2: VÁLIDO - Dentro de plazo, talla equivocada (moda)
INSERT INTO return_requests (id, order_id, customer_id, status, reason, reason_category, resolution, refund_amount, tracking_number, notes, created_at, resolved_at) VALUES
('ret002', 'o002', 'c002', 'approved',
 'El abrigo me queda pequeño, necesito una talla más grande',
 'wrong_size', 'replacement', 129.99, 'RET-0002DEF',
 '[CASE:VALID] Aprobado automáticamente. Talla equivocada en moda (permitido sin coste), plazo correcto (3 de 30 días), importe dentro de límite.',
 '2026-08-05 12:30:00+02', '2026-08-06 11:00:00+02');

-- CASO 3: INVÁLIDO - Fuera de plazo (más de 30 días)
INSERT INTO return_requests (id, order_id, customer_id, status, reason, reason_category, resolution, refund_amount, tracking_number, notes, created_at, resolved_at) VALUES
('ret003', 'o006', 'c001', 'rejected',
 'El smartphone no me gusta, quiero devolverlo',
 'changed_mind', 'rejected', 0.00, NULL,
 '[CASE:INVALID] Rechazado automáticamente. Plazo de devolución superado: 57 días desde la entrega frente a un máximo de 30 días. Rechazo automático.',
 '2026-09-10 10:00:00+02', '2026-09-10 11:30:00+02');

-- CASO 4: INVÁLIDO - Higiene sensible + embalaje roto (cosmética)
INSERT INTO return_requests (id, order_id, customer_id, status, reason, reason_category, resolution, refund_amount, tracking_number, notes, created_at, resolved_at) VALUES
('ret004', 'o005', 'c005', 'rejected',
 'El perfume no me sienta bien, me produjo alergia al usarlo',
 'allergic_reaction', 'rejected', 0.00, NULL,
 '[CASE:INVALID] Rechazado automáticamente. Motivo ''allergic_reaction'' con producto de higiene/seguridad (cosmética) abierto/usado. Art. 103 TRLGDCU excluye devolución. Rechazo automático independientemente del plazo.',
 '2026-08-09 15:00:00+02', '2026-08-10 09:00:00+02');

-- CASO 5: REVISIÓN HUMANA - Importe > 100€ + motivo defectuoso (electrodoméstico)
INSERT INTO return_requests (id, order_id, customer_id, status, reason, reason_category, resolution, refund_amount, tracking_number, notes, created_at, resolved_at) VALUES
('ret005', 'o004', 'c004', 'pending_approval',
 'La nevera no enfría bien, sospecho que el compresor tiene un problema',
 'defective', NULL, 549.99, NULL,
 '[CASE:HUMAN_REVIEW] Pendiente de aprobación manual (HITL). Solicitud dentro de plazo (3 de 30 días), estado aceptado (defective), pero importe de 549.99€ supera el umbral de 100€ (HITL fijo de la plataforma).',
 '2026-08-08 16:00:00+02', NULL);

-- CASO 6: REVISIÓN HUMANA - Cliente frecuente (posible abuso)
INSERT INTO return_requests (id, order_id, customer_id, status, reason, reason_category, resolution, refund_amount, tracking_number, notes, created_at, resolved_at) VALUES
('ret006', 'o005', 'c005', 'pending_approval',
 'La crema facial no me convence, la calidad es peor de lo esperada',
 'quality_issue', NULL, 34.99, NULL,
 '[CASE:HUMAN_REVIEW] Pendiente de aprobación manual (HITL). Cliente con historial de devoluciones frecuentes (posible abuso); motivo subjetivo (quality_issue) requiere verificación humana.',
 '2026-08-09 14:00:00+02', NULL);

-- =========================================================================
-- STEP 7: LÍNEAS DE DEVOLUCIÓN (return_items)
-- =========================================================================
INSERT INTO return_items (id, return_request_id, order_item_id, quantity, condition) VALUES
('ri001', 'ret001', 'oi001', 1, 'defective'),
('ri002', 'ret002', 'oi003', 1, 'wrong_size'),
('ri003', 'ret003', 'oi009', 1, 'opened_unused'),
('ri004', 'ret004', 'oi007', 1, 'opened_tested'),
('ri005', 'ret005', 'oi006', 1, 'defective'),
('ri006', 'ret006', 'oi008', 1, 'opened_unused');

-- =========================================================================
-- STEP 8: SESIONES DE CHAT (chat_sessions) para pruebas end-to-end
-- =========================================================================
INSERT INTO chat_sessions (id, customer_id, status, started_at, ended_at, metadata) VALUES
('sess001', 'c001', 'closed', '2026-07-30 16:00:00+02', '2026-07-30 16:15:00+02',
 '{"return_request_id": "ret001", "order_number": "ORD-2026-00001", "expected_label": "valid", "source": "test_dataset"}'::jsonb),

('sess002', 'c002', 'closed', '2026-08-05 12:00:00+02', '2026-08-05 12:10:00+02',
 '{"return_request_id": "ret002", "order_number": "ORD-2026-00002", "expected_label": "valid", "source": "test_dataset"}'::jsonb),

('sess003', 'c001', 'closed', '2026-09-10 09:00:00+02', '2026-09-10 09:15:00+02',
 '{"return_request_id": "ret003", "order_number": "ORD-2026-00006", "expected_label": "invalid", "source": "test_dataset"}'::jsonb),

('sess004', 'c004', 'closed', '2026-08-08 15:00:00+02', '2026-08-08 15:20:00+02',
 '{"return_request_id": "ret005", "order_number": "ORD-2026-00004", "expected_label": "human_review", "source": "test_dataset"}'::jsonb);

-- =========================================================================
-- STEP 9: MENSAJES DE CHAT (chat_messages) para pruebas end-to-end
-- =========================================================================
-- SESIÓN 1: Caso VÁLIDO (defectuoso, dentro de plazo)
INSERT INTO chat_messages (id, session_id, role, content, created_at) VALUES
('msg001', 'sess001', 'user', 'Hola, tengo un problema con un pedido', '2026-07-30 16:00:00+02'),
('msg002', 'sess001', 'assistant', 'Claro, encantado de ayudarte. ¿Me indicas el número de tu pedido?', '2026-07-30 16:01:00+02'),
('msg003', 'sess001', 'user', 'Es el pedido ORD-2026-00001. El portátil que me llegó no enciende, parece un fallo de fábrica', '2026-07-30 16:03:00+02'),
('msg004', 'sess001', 'assistant', 'Gracias, dame un momento para revisar el pedido ORD-2026-00001 y comprobar la política de devolución de Electrónica e Informática.', '2026-07-30 16:05:00+02'),
('msg005', 'sess001', 'assistant', 'Perfecto, ORD-2026-00001: revisado el pedido, tu devolución del Nortek UltraBook queda aprobada. Reembolso de 749.99€ según la política de Electrónica e Informática. En breve recibirás la etiqueta de envío.', '2026-07-30 16:08:00+02');

-- SESIÓN 2: Caso VÁLIDO (talla equivocada)
INSERT INTO chat_messages (id, session_id, role, content, created_at) VALUES
('msg006', 'sess002', 'user', 'Hola! necesito ayuda con un pedido mío', '2026-08-05 12:00:00+02'),
('msg007', 'sess002', 'assistant', 'Sin problema. ¿Puedes pasarme el número de pedido para localizarlo?', '2026-08-05 12:01:00+02'),
('msg008', 'sess002', 'user', 'Es el pedido ORD-2026-00002. El abrigo me queda pequeño, necesito una talla más grande.', '2026-08-05 12:03:00+02'),
('msg009', 'sess002', 'assistant', 'Todo correcto: la devolución del Nordic Wear Abrigo Parka (pedido ORD-2026-00002) cumple el plazo y las condiciones de la categoría Moda y Complementos, así que queda aprobada automáticamente con un reembolso de 129.99€.', '2026-08-05 12:06:00+02');

-- SESIÓN 3: Caso INVÁLIDO (fuera de plazo)
INSERT INTO chat_messages (id, session_id, role, content, created_at) VALUES
('msg010', 'sess003', 'user', 'Buenas tardes, quería tramitar una devolución.', '2026-09-10 09:00:00+02'),
('msg011', 'sess003', 'assistant', 'Vale, para revisarlo necesito el número de pedido, ¿lo tienes a mano?', '2026-09-10 09:01:00+02'),
('msg012', 'sess003', 'user', 'Es el pedido ORD-2026-00006. El smartphone no me gusta, quiero devolverlo.', '2026-09-10 09:03:00+02'),
('msg013', 'sess003', 'assistant', 'He revisado el pedido ORD-2026-00006 y, lo siento, la devolución del Vionix Smartphone Aurora no es posible: Plazo de devolución superado: más de 30 días desde la entrega. Según la política de Electrónica e Informática no podemos tramitarla.', '2026-09-10 09:08:00+02');

-- SESIÓN 4: Caso REVISIÓN HUMANA (importe elevado)
INSERT INTO chat_messages (id, session_id, role, content, created_at) VALUES
('msg014', 'sess004', 'user', 'Hola, ¿me podéis ayudar con una devolución?', '2026-08-08 15:00:00+02'),
('msg015', 'sess004', 'assistant', 'Sin problema. ¿Puedes pasarme el número de pedido para localizarlo?', '2026-08-08 15:01:00+02'),
('msg016', 'sess004', 'user', 'Es el pedido ORD-2026-00004. La nevera no enfría bien, sospecho que el compresor tiene un problema', '2026-08-08 15:03:00+02'),
('msg017', 'sess004', 'assistant', 'He registrado tu solicitud sobre el pedido ORD-2026-00004 (Frescor Frigorífico). Este caso concreto necesita revisión de un agente humano antes de darte una respuesta definitiva (importe a reembolsar de 549.99€ supera el umbral de 100€). Te avisaremos en cuanto se resuelva.', '2026-08-08 15:08:00+02'),
('msg018', 'sess004', 'system', 'Caso derivado a HITL: return_request_id=ret005, motivo=defective, importe=549.99 EUR.', '2026-08-08 15:09:00+02');

-- =========================================================================
-- FIN DEL DATASET DE PRUEBAS
-- =========================================================================
-- Resumen de casos generados:
-- - ret001 (VÁLIDO): Defectuoso, 5 días, 749.99€ - Requiere HITL por importe
-- - ret002 (VÁLIDO): Talla equivocada, 3 días, 129.99€ - Aprobado
-- - ret003 (INVÁLIDO): Fuera de plazo (57 días vs. 30 máx) - Rechazado
-- - ret004 (INVÁLIDO): Higiene sensible + abierto - Rechazado por ley
-- - ret005 (REVISIÓN HUMANA): Defectuoso pero 549.99€ > 100€ - HITL
-- - ret006 (REVISIÓN HUMANA): Cliente frecuente + motivo subjetivo - HITL
