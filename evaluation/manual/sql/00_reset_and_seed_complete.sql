-- =============================================================================
-- SCRIPT COMPLETO: RESET + SEED + POLÍTICAS para QA v2
-- =============================================================================
-- EJECUTAR ESTE SCRIPT PRIMERO
-- Borra todo y recarga: políticas + 24 clientes + 24 productos + 24 pedidos
-- =============================================================================

-- ── STEP 1: Limpiar tablas (orden inverso por FK) ─────────────────────────
DELETE FROM return_items;
DELETE FROM return_requests;
DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM products;
DELETE FROM customers;
-- NO borrar return_policies, solo actualizar si faltan

-- ── STEP 2: INSERTAR POLÍTICAS DE DEVOLUCIÓN (16 categorías) ──────────────
INSERT INTO return_policies (category, max_return_days, requires_original_packaging, restocking_fee_percent, allowed_conditions, policy_text, active) VALUES
    ('alimentacion', 14, FALSE, 0, ARRAY['unopened','defective','wrong_item'], 'Política: Alimentación - 14 días max', TRUE),
    ('bebe_puericultura', 30, FALSE, 0, ARRAY['unopened','defective','wrong_item','not_as_described'], 'Política: Bebé y Puericultura - 30 días', TRUE),
    ('calzado', 30, TRUE, 0, ARRAY['unopened','defective','wrong_item','wrong_size','not_as_described'], 'Política: Calzado - 30 días', TRUE),
    ('cosmetica_perfumeria', 21, FALSE, 0, ARRAY['unopened','defective','wrong_item'], 'Política: Cosmética - 21 días (HIGIENE SENSIBLE)', TRUE),
    ('deportes_aire_libre', 30, FALSE, 0, ARRAY['unopened','defective','wrong_item','not_as_described','opened_tested'], 'Política: Deportes - 30 días', TRUE),
    ('drogueria_salud', 21, FALSE, 0, ARRAY['unopened','defective','wrong_item'], 'Política: Droguería - 21 días (HIGIENE SENSIBLE)', TRUE),
    ('electrodomesticos', 30, TRUE, 10, ARRAY['unopened','defective','wrong_item','not_as_described','missing_parts'], 'Política: Electrodomésticos - 30 días, recargo 10%', TRUE),
    ('electronica_informatica', 30, FALSE, 15, ARRAY['unopened','defective','wrong_item','not_as_described','missing_parts','opened_tested'], 'Política: Electrónica - 30 días, recargo 15%', TRUE),
    ('jardineria_bricolaje', 30, FALSE, 5, ARRAY['unopened','defective','wrong_item','not_as_described'], 'Política: Jardinería - 30 días, recargo 5%', TRUE),
    ('juguetes', 30, TRUE, 0, ARRAY['unopened','defective','wrong_item','not_as_described'], 'Política: Juguetes - 30 días', TRUE),
    ('libros_papeleria', 21, FALSE, 0, ARRAY['unopened','defective','wrong_item'], 'Política: Libros - 21 días', TRUE),
    ('mascotas', 21, FALSE, 0, ARRAY['unopened','defective','wrong_item'], 'Política: Mascotas - 21 días (HIGIENE SENSIBLE)', TRUE),
    ('moda_ropa', 30, FALSE, 0, ARRAY['unopened','wrong_size','defective','wrong_item','not_as_described','opened_unused'], 'Política: Moda - 30 días, sin recargo', TRUE),
    ('muebles', 14, TRUE, 15, ARRAY['unopened','defective','wrong_item'], 'Política: Muebles - 14 días, recargo 15%', TRUE),
    ('hogar_decoracion', 30, FALSE, 0, ARRAY['unopened','defective','wrong_item','opened_unused'], 'Política: Hogar - 30 días', TRUE),
    ('joyeria_relojes', 15, TRUE, 0, ARRAY['unopened','defective','wrong_item'], 'Política: Joyería - 15 días (PLAZO CORTO)', TRUE)
ON CONFLICT (category) WHERE active = TRUE DO NOTHING;

-- ── STEP 3: INSERTAR CUSTOMERS (24) ────────────────────────────────────────
INSERT INTO customers (id, email, full_name, phone, address) VALUES
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567801', 'qa.test.01@example.com', 'Cliente QA 01', '+34600000001',
   '{"street": "Calle Test 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567802', 'qa.test.02@example.com', 'Cliente QA 02', '+34600000002',
   '{"street": "Calle Test 2", "city": "Barcelona", "postal_code": "08001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567803', 'qa.test.03@example.com', 'Cliente QA 03', '+34600000003',
   '{"street": "Calle Test 3", "city": "Valencia", "postal_code": "46001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567804', 'qa.test.04@example.com', 'Cliente QA 04', '+34600000004',
   '{"street": "Calle Test 4", "city": "Sevilla", "postal_code": "41001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567805', 'qa.test.05@example.com', 'Cliente QA 05', '+34600000005',
   '{"street": "Calle Test 5", "city": "Bilbao", "postal_code": "48001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567806', 'qa.test.06@example.com', 'Cliente QA 06', '+34600000006',
   '{"street": "Calle Test 6", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567807', 'qa.test.07@example.com', 'Cliente QA 07', '+34600000007',
   '{"street": "Calle Test 7", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567808', 'qa.test.08@example.com', 'Cliente QA 08', '+34600000008',
   '{"street": "Calle Test 8", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567809', 'qa.test.09@example.com', 'Cliente QA 09', '+34600000009',
   '{"street": "Calle Test 9", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567810', 'qa.test.10@example.com', 'Cliente QA 10', '+34600000010',
   '{"street": "Calle Test 10", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567811', 'qa.test.11@example.com', 'Cliente QA 11', '+34600000011',
   '{"street": "Calle Test 11", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567812', 'qa.test.12@example.com', 'Cliente QA 12', '+34600000012',
   '{"street": "Calle Test 12", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567813', 'qa.test.13@example.com', 'Cliente QA 13', '+34600000013',
   '{"street": "Calle Test 13", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567814', 'qa.test.14@example.com', 'Cliente QA 14 ⚠️ FRECUENTE', '+34600000014',
   '{"street": "Calle Test 14", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567815', 'qa.test.15@example.com', 'Cliente QA 15', '+34600000015',
   '{"street": "Calle Test 15", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567816', 'qa.test.16@example.com', 'Cliente QA 16', '+34600000016',
   '{"street": "Calle Test 16", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567817', 'qa.test.17@example.com', 'Cliente QA 17', '+34600000017',
   '{"street": "Calle Test 17", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567818', 'qa.test.18@example.com', 'Cliente QA 18', '+34600000018',
   '{"street": "Calle Test 18", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567819', 'qa.test.19@example.com', 'Cliente QA 19', '+34600000019',
   '{"street": "Calle Test 19", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567820', 'qa.test.20@example.com', 'Cliente QA 20', '+34600000020',
   '{"street": "Calle Test 20", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567821', 'qa.test.21@example.com', 'Cliente QA 21 ⚠️ FRECUENTE', '+34600000021',
   '{"street": "Calle Test 21", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567822', 'qa.test.22@example.com', 'Cliente QA 22', '+34600000022',
   '{"street": "Calle Test 22", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567823', 'qa.test.23@example.com', 'Cliente QA 23', '+34600000023',
   '{"street": "Calle Test 23", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567824', 'qa.test.24@example.com', 'Cliente QA 24', '+34600000024',
   '{"street": "Calle Test 24", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb);

-- ── STEP 4: INSERTAR PRODUCTS (24) ────────────────────────────────────────
INSERT INTO products (id, sku, name, description, category, price, weight_kg) VALUES
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d601', 'QA-001', 'Alimento QA #1', 'Test', 'alimentacion', 29.99, 0.5),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d602', 'QA-002', 'Cochecito QA #2', 'Test', 'bebe_puericultura', 299.99, 8),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d603', 'QA-003', 'Zapatillas QA #3', 'Test', 'calzado', 79.99, 0.5),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d604', 'QA-004', 'Perfume QA #4', 'Test', 'cosmetica_perfumeria', 49.99, 0.1),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d605', 'QA-005', 'Bicicleta QA #5', 'Test', 'deportes_aire_libre', 399.99, 18),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d606', 'QA-006', 'Champú QA #6', 'Test', 'drogueria_salud', 12.99, 0.3),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d607', 'QA-007', 'Libro QA #7', 'Test', 'libros_papeleria', 24.99, 0.6),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d608', 'QA-008', 'Comida mascotas QA #8', 'Test', 'mascotas', 39.99, 5),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d609', 'QA-009', 'Nevera QA #9', 'Test', 'electrodomesticos', 849.99, 70),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d610', 'QA-010', 'Portátil QA #10', 'Test', 'electronica_informatica', 899.99, 2),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d611', 'QA-011', 'Herramientas QA #11', 'Test', 'jardineria_bricolaje', 69.99, 3),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d612', 'QA-012', 'Juguete QA #12', 'Test', 'juguetes', 89.99, 1.5),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d613', 'QA-013', 'Camiseta QA #13', 'Test', 'moda_ropa', 34.99, 0.3),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d614', 'QA-014', 'Sofá QA #14', 'Test', 'muebles', 1299.99, 50),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d615', 'QA-015', 'Lámpara QA #15', 'Test', 'hogar_decoracion', 59.99, 2),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d616', 'QA-016', 'Reloj QA #16', 'Test', 'joyeria_relojes', 299.99, 0.2),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d617', 'QA-017', 'Aceite QA #17', 'Test', 'alimentacion', 15.99, 1),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d618', 'QA-018', 'Lavadora QA #18', 'Test', 'electrodomesticos', 549.99, 60),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d619', 'QA-019', 'Botas QA #19', 'Test', 'calzado', 119.99, 1),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d620', 'QA-020', 'Silla coche QA #20', 'Test', 'bebe_puericultura', 199.99, 6),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d621', 'QA-021', 'Loción QA #21', 'Test', 'drogueria_salud', 19.99, 0.5),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d622', 'QA-022', 'Alimento gourmet QA #22', 'Test', 'alimentacion', 59.99, 2),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d623', 'QA-023', 'Esmalte QA #23', 'Test', 'cosmetica_perfumeria', 14.99, 0.05),
  ('b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d624', 'QA-024', 'Teclado QA #24', 'Test', 'electronica_informatica', 129.99, 1);

-- ── STEP 5: INSERTAR ORDERS (24) ───────────────────────────────────────────
INSERT INTO orders (id, customer_id, order_number, status, total_amount, shipping_address, ordered_at, delivered_at) VALUES
  ('c3d4e5f6-a7b8-9012-cdef-123456789001', 'a1b2c3d4-e5f6-7890-abcd-ef1234567801', 'ORD-QA-0001', 'delivered', 29.99, '{"street": "Calle Test 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '8 days', NOW() - INTERVAL '5 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789002', 'a1b2c3d4-e5f6-7890-abcd-ef1234567802', 'ORD-QA-0002', 'delivered', 299.99, '{"street": "Calle Test 2", "city": "Barcelona", "postal_code": "08001", "country": "ES"}'::jsonb, NOW() - INTERVAL '10 days', NOW() - INTERVAL '7 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789003', 'a1b2c3d4-e5f6-7890-abcd-ef1234567803', 'ORD-QA-0003', 'delivered', 79.99, '{"street": "Calle Test 3", "city": "Valencia", "postal_code": "46001", "country": "ES"}'::jsonb, NOW() - INTERVAL '15 days', NOW() - INTERVAL '12 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789004', 'a1b2c3d4-e5f6-7890-abcd-ef1234567804', 'ORD-QA-0004', 'delivered', 49.99, '{"street": "Calle Test 4", "city": "Sevilla", "postal_code": "41001", "country": "ES"}'::jsonb, NOW() - INTERVAL '3 days', NOW() - INTERVAL '0 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789005', 'a1b2c3d4-e5f6-7890-abcd-ef1234567805', 'ORD-QA-0005', 'delivered', 399.99, '{"street": "Calle Test 5", "city": "Bilbao", "postal_code": "48001", "country": "ES"}'::jsonb, NOW() - INTERVAL '20 days', NOW() - INTERVAL '17 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789006', 'a1b2c3d4-e5f6-7890-abcd-ef1234567806', 'ORD-QA-0006', 'delivered', 12.99, '{"street": "Calle Test 6", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '28 days', NOW() - INTERVAL '25 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789007', 'a1b2c3d4-e5f6-7890-abcd-ef1234567807', 'ORD-QA-0007', 'delivered', 24.99, '{"street": "Calle Test 7", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '45 days', NOW() - INTERVAL '42 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789008', 'a1b2c3d4-e5f6-7890-abcd-ef1234567808', 'ORD-QA-0008', 'delivered', 39.99, '{"street": "Calle Test 8", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '6 days', NOW() - INTERVAL '3 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789009', 'a1b2c3d4-e5f6-7890-abcd-ef1234567809', 'ORD-QA-0009', 'delivered', 849.99, '{"street": "Calle Test 9", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '12 days', NOW() - INTERVAL '9 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789010', 'a1b2c3d4-e5f6-7890-abcd-ef1234567810', 'ORD-QA-0010', 'delivered', 899.99, '{"street": "Calle Test 10", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '18 days', NOW() - INTERVAL '15 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789011', 'a1b2c3d4-e5f6-7890-abcd-ef1234567811', 'ORD-QA-0011', 'delivered', 69.99, '{"street": "Calle Test 11", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '7 days', NOW() - INTERVAL '4 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789012', 'a1b2c3d4-e5f6-7890-abcd-ef1234567812', 'ORD-QA-0012', 'delivered', 89.99, '{"street": "Calle Test 12", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '22 days', NOW() - INTERVAL '19 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789013', 'a1b2c3d4-e5f6-7890-abcd-ef1234567813', 'ORD-QA-0013', 'delivered', 34.99, '{"street": "Calle Test 13", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '2 days', NOW() - INTERVAL '0 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789014', 'a1b2c3d4-e5f6-7890-abcd-ef1234567814', 'ORD-QA-0014', 'delivered', 1299.99, '{"street": "Calle Test 14", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '5 days', NOW() - INTERVAL '2 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789015', 'a1b2c3d4-e5f6-7890-abcd-ef1234567815', 'ORD-QA-0015', 'delivered', 59.99, '{"street": "Calle Test 15", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '11 days', NOW() - INTERVAL '8 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789016', 'a1b2c3d4-e5f6-7890-abcd-ef1234567816', 'ORD-QA-0016', 'delivered', 299.99, '{"street": "Calle Test 16", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '32 days', NOW() - INTERVAL '29 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789017', 'a1b2c3d4-e5f6-7890-abcd-ef1234567817', 'ORD-QA-0017', 'delivered', 15.99, '{"street": "Calle Test 17", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '19 days', NOW() - INTERVAL '16 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789018', 'a1b2c3d4-e5f6-7890-abcd-ef1234567818', 'ORD-QA-0018', 'delivered', 549.99, '{"street": "Calle Test 18", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '27 days', NOW() - INTERVAL '24 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789019', 'a1b2c3d4-e5f6-7890-abcd-ef1234567819', 'ORD-QA-0019', 'delivered', 119.99, '{"street": "Calle Test 19", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '28 days', NOW() - INTERVAL '25 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789020', 'a1b2c3d4-e5f6-7890-abcd-ef1234567820', 'ORD-QA-0020', 'delivered', 199.99, '{"street": "Calle Test 20", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '9 days', NOW() - INTERVAL '6 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789021', 'a1b2c3d4-e5f6-7890-abcd-ef1234567821', 'ORD-QA-0021', 'delivered', 19.99, '{"street": "Calle Test 21", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '14 days', NOW() - INTERVAL '11 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789022', 'a1b2c3d4-e5f6-7890-abcd-ef1234567822', 'ORD-QA-0022', 'delivered', 59.99, '{"street": "Calle Test 22", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '8 days', NOW() - INTERVAL '5 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789023', 'a1b2c3d4-e5f6-7890-abcd-ef1234567823', 'ORD-QA-0023', 'delivered', 14.99, '{"street": "Calle Test 23", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '11 days', NOW() - INTERVAL '8 days'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789024', 'a1b2c3d4-e5f6-7890-abcd-ef1234567824', 'ORD-QA-0024', 'delivered', 129.99, '{"street": "Calle Test 24", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '26 days', NOW() - INTERVAL '23 days');

-- ── STEP 6: INSERTAR ORDER_ITEMS (24) ──────────────────────────────────────
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
  ('d4e5f6a7-b8c9-0123-defa-234567890101', 'c3d4e5f6-a7b8-9012-cdef-123456789001', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d601', 1, 29.99, 29.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890102', 'c3d4e5f6-a7b8-9012-cdef-123456789002', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d602', 1, 299.99, 299.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890103', 'c3d4e5f6-a7b8-9012-cdef-123456789003', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d603', 1, 79.99, 79.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890104', 'c3d4e5f6-a7b8-9012-cdef-123456789004', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d604', 1, 49.99, 49.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890105', 'c3d4e5f6-a7b8-9012-cdef-123456789005', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d605', 1, 399.99, 399.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890106', 'c3d4e5f6-a7b8-9012-cdef-123456789006', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d606', 1, 12.99, 12.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890107', 'c3d4e5f6-a7b8-9012-cdef-123456789007', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d607', 1, 24.99, 24.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890108', 'c3d4e5f6-a7b8-9012-cdef-123456789008', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d608', 1, 39.99, 39.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890109', 'c3d4e5f6-a7b8-9012-cdef-123456789009', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d609', 1, 849.99, 849.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890110', 'c3d4e5f6-a7b8-9012-cdef-123456789010', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d610', 1, 899.99, 899.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890111', 'c3d4e5f6-a7b8-9012-cdef-123456789011', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d611', 1, 69.99, 69.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890112', 'c3d4e5f6-a7b8-9012-cdef-123456789012', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d612', 1, 89.99, 89.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890113', 'c3d4e5f6-a7b8-9012-cdef-123456789013', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d613', 1, 34.99, 34.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890114', 'c3d4e5f6-a7b8-9012-cdef-123456789014', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d614', 1, 1299.99, 1299.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890115', 'c3d4e5f6-a7b8-9012-cdef-123456789015', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d615', 1, 59.99, 59.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890116', 'c3d4e5f6-a7b8-9012-cdef-123456789016', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d616', 1, 299.99, 299.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890117', 'c3d4e5f6-a7b8-9012-cdef-123456789017', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d617', 1, 15.99, 15.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890118', 'c3d4e5f6-a7b8-9012-cdef-123456789018', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d618', 1, 549.99, 549.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890119', 'c3d4e5f6-a7b8-9012-cdef-123456789019', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d619', 1, 119.99, 119.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890120', 'c3d4e5f6-a7b8-9012-cdef-123456789020', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d620', 1, 199.99, 199.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890121', 'c3d4e5f6-a7b8-9012-cdef-123456789021', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d621', 1, 19.99, 19.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890122', 'c3d4e5f6-a7b8-9012-cdef-123456789022', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d622', 1, 59.99, 59.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890123', 'c3d4e5f6-a7b8-9012-cdef-123456789023', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d623', 1, 14.99, 14.99),
  ('d4e5f6a7-b8c9-0123-defa-234567890124', 'c3d4e5f6-a7b8-9012-cdef-123456789024', 'b2c3d4e5-f6a7-b8c9-d0e1-f2a3b4c5d624', 1, 129.99, 129.99);

-- ── VERIFICACIÓN ──────────────────────────────────────────────────────────
SELECT 'customers' AS tabla, count(*) FROM customers
UNION ALL SELECT 'products', count(*) FROM products
UNION ALL SELECT 'orders', count(*) FROM orders
UNION ALL SELECT 'order_items', count(*) FROM order_items
UNION ALL SELECT 'return_requests', count(*) FROM return_requests;

-- ═════════════════════════════════════════════════════════════════════════════
-- ✅ RESET AND SEED COMPLETO - Listo para probar
-- Este script carga TODO: 16 políticas + 24 clientes + 24 productos + 24 pedidos
-- ═════════════════════════════════════════════════════════════════════════════
