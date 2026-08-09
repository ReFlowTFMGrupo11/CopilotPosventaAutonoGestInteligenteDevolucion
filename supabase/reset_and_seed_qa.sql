-- =============================================================================
-- Script de reset + seed para pruebas manuales de los 3 casos de uso.
-- Ejecutar en Supabase SQL Editor o con psql.
--
-- Casos:
--   1. ✅ Auto-aprobado: Batidora 79,99€ (defectuosa)
--   2. 🟡 HITL: Portátil 899,99€ (píxeles muertos)
--   3. ❌ Rechazado: Libro 34,99€ (cambio de opinión)
-- =============================================================================

-- ── Limpiar tablas (orden inverso por FK) ─────────────────────────────────
DELETE FROM return_items;
DELETE FROM return_requests;
DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM products;
DELETE FROM customers;

-- ── Customers ─────────────────────────────────────────────────────────────
INSERT INTO customers (id, email, full_name, phone, address) VALUES
  ('a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'maria.garcia@email.com', 'María García López', '+34612345678',
   '{"street": "Calle Gran Vía 42", "city": "Madrid", "postal_code": "28013", "country": "ES"}'),
  ('c3d4e5f6-a7b8-9012-cdef-123456789012', 'laura.fernandez@email.com', 'Laura Fernández Soto', '+34634567890',
   '{"street": "Calle Sierpes 15", "city": "Sevilla", "postal_code": "41004", "country": "ES"}');

-- ── Products ──────────────────────────────────────────────────────────────
INSERT INTO products (id, sku, name, description, category, price, weight_kg) VALUES
  ('d4e5f6a7-b8c9-0123-defa-234567890123', 'ELEC-LAPTOP-001', 'Portátil ProBook 15"',
   'Portátil de alto rendimiento con 16GB RAM y 512GB SSD', 'electronics', 899.99, 1.8),
  ('a7b8c9d0-e1f2-3456-abcd-567890123456', 'HOME-BLENDER-001', 'Batidora de Vaso 1200W',
   'Batidora profesional con 6 velocidades', 'home_appliances', 79.99, 2.5),
  ('b8c9d0e1-f2a3-4567-bcde-678901234567', 'BOOK-PROG-001', 'Clean Code (Edición Español)',
   'Libro sobre buenas prácticas de programación', 'books', 34.99, 0.6);

-- ── Orders (fechas ajustadas a hoy 2026-08-09) ───────────────────────────

-- Caso 2: Portátil (María) — entregado hace 8 días (dentro de 15 días electronics)
INSERT INTO orders (id, customer_id, order_number, status, total_amount, shipping_address, ordered_at, delivered_at) VALUES
  ('c9d0e1f2-a3b4-5678-cdef-789012345678', 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'ORD-2026-00142', 'delivered', 899.99,
   '{"street": "Calle Gran Vía 42", "city": "Madrid", "postal_code": "28013", "country": "ES"}',
   '2026-07-28 14:30:00+02', '2026-08-01 11:00:00+02');

-- Casos 1 y 3: Batidora + Libro (Laura) — entregado hace 5 días
INSERT INTO orders (id, customer_id, order_number, status, total_amount, shipping_address, ordered_at, delivered_at) VALUES
  ('e1f2a3b4-c5d6-7890-efab-901234567890', 'c3d4e5f6-a7b8-9012-cdef-123456789012', 'ORD-2026-00163', 'delivered', 114.98,
   '{"street": "Calle Sierpes 15", "city": "Sevilla", "postal_code": "41004", "country": "ES"}',
   '2026-07-31 18:00:00+02', '2026-08-04 10:30:00+02');

-- ── Order Items ───────────────────────────────────────────────────────────

-- Portátil de María
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
  ('f2a3b4c5-d6e7-8901-fabc-012345678901', 'c9d0e1f2-a3b4-5678-cdef-789012345678',
   'd4e5f6a7-b8c9-0123-defa-234567890123', 1, 899.99, 899.99);

-- Batidora de Laura
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
  ('c5d6e7f8-a9b0-1234-cdef-345678901234', 'e1f2a3b4-c5d6-7890-efab-901234567890',
   'a7b8c9d0-e1f2-3456-abcd-567890123456', 1, 79.99, 79.99);

-- Libro de Laura
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
  ('d6e7f8a9-b0c1-2345-defa-456789012345', 'e1f2a3b4-c5d6-7890-efab-901234567890',
   'b8c9d0e1-f2a3-4567-bcde-678901234567', 1, 34.99, 34.99);

-- ── Verificación ──────────────────────────────────────────────────────────
SELECT 'customers' AS tabla, count(*) FROM customers
UNION ALL SELECT 'products', count(*) FROM products
UNION ALL SELECT 'orders', count(*) FROM orders
UNION ALL SELECT 'order_items', count(*) FROM order_items
UNION ALL SELECT 'return_requests', count(*) FROM return_requests;
