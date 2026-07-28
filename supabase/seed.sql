-- Seed data for development and demo purposes

-- Sample customers
INSERT INTO customers (id, email, full_name, phone, address) VALUES
    ('a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'maria.garcia@email.com', 'María García López', '+34612345678', '{"street": "Calle Gran Vía 42", "city": "Madrid", "postal_code": "28013", "country": "ES"}'),
    ('b2c3d4e5-f6a7-8901-bcde-f12345678901', 'carlos.martinez@email.com', 'Carlos Martínez Ruiz', '+34623456789', '{"street": "Avda. Diagonal 211", "city": "Barcelona", "postal_code": "08018", "country": "ES"}'),
    ('c3d4e5f6-a7b8-9012-cdef-123456789012', 'laura.fernandez@email.com', 'Laura Fernández Soto', '+34634567890', '{"street": "Calle Sierpes 15", "city": "Sevilla", "postal_code": "41004", "country": "ES"}');

-- Sample products
INSERT INTO products (id, sku, name, description, category, price, weight_kg) VALUES
    ('d4e5f6a7-b8c9-0123-defa-234567890123', 'ELEC-LAPTOP-001', 'Portátil ProBook 15"', 'Portátil de alto rendimiento con 16GB RAM y 512GB SSD', 'electronics', 899.99, 1.8),
    ('e5f6a7b8-c9d0-1234-efab-345678901234', 'ELEC-PHONE-001', 'Smartphone Galaxy X12', 'Smartphone 5G con cámara de 108MP', 'electronics', 649.99, 0.19),
    ('f6a7b8c9-d0e1-2345-fabc-456789012345', 'FASH-JACKET-001', 'Chaqueta de Cuero Premium', 'Chaqueta de cuero auténtico, talla M', 'fashion', 199.99, 1.2),
    ('a7b8c9d0-e1f2-3456-abcd-567890123456', 'HOME-BLENDER-001', 'Batidora de Vaso 1200W', 'Batidora profesional con 6 velocidades', 'home_appliances', 79.99, 2.5),
    ('b8c9d0e1-f2a3-4567-bcde-678901234567', 'BOOK-PROG-001', 'Clean Code (Edición Español)', 'Libro sobre buenas prácticas de programación', 'books', 34.99, 0.6);

-- Sample orders
INSERT INTO orders (id, customer_id, order_number, status, total_amount, shipping_address, ordered_at, delivered_at) VALUES
    ('c9d0e1f2-a3b4-5678-cdef-789012345678', 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'ORD-2026-00142', 'delivered', 899.99, '{"street": "Calle Gran Vía 42", "city": "Madrid", "postal_code": "28013", "country": "ES"}', '2026-07-10 14:30:00+02', '2026-07-14 11:00:00+02'),
    ('d0e1f2a3-b4c5-6789-defa-890123456789', 'b2c3d4e5-f6a7-8901-bcde-f12345678901', 'ORD-2026-00158', 'delivered', 849.98, '{"street": "Avda. Diagonal 211", "city": "Barcelona", "postal_code": "08018", "country": "ES"}', '2026-07-05 09:15:00+02', '2026-07-09 16:45:00+02'),
    ('e1f2a3b4-c5d6-7890-efab-901234567890', 'c3d4e5f6-a7b8-9012-cdef-123456789012', 'ORD-2026-00163', 'delivered', 114.98, '{"street": "Calle Sierpes 15", "city": "Sevilla", "postal_code": "41004", "country": "ES"}', '2026-06-20 18:00:00+02', '2026-06-25 10:30:00+02');

-- Sample order items
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
    ('f2a3b4c5-d6e7-8901-fabc-012345678901', 'c9d0e1f2-a3b4-5678-cdef-789012345678', 'd4e5f6a7-b8c9-0123-defa-234567890123', 1, 899.99, 899.99),
    ('a3b4c5d6-e7f8-9012-abcd-123456789012', 'd0e1f2a3-b4c5-6789-defa-890123456789', 'e5f6a7b8-c9d0-1234-efab-345678901234', 1, 649.99, 649.99),
    ('b4c5d6e7-f8a9-0123-bcde-234567890123', 'd0e1f2a3-b4c5-6789-defa-890123456789', 'f6a7b8c9-d0e1-2345-fabc-456789012345', 1, 199.99, 199.99),
    ('c5d6e7f8-a9b0-1234-cdef-345678901234', 'e1f2a3b4-c5d6-7890-efab-901234567890', 'a7b8c9d0-e1f2-3456-abcd-567890123456', 1, 79.99, 79.99),
    ('d6e7f8a9-b0c1-2345-defa-456789012345', 'e1f2a3b4-c5d6-7890-efab-901234567890', 'b8c9d0e1-f2a3-4567-bcde-678901234567', 1, 34.99, 34.99);

-- Sample return policies
INSERT INTO return_policies (id, category, max_return_days, requires_original_packaging, restocking_fee_percent, allowed_conditions, policy_text) VALUES
    ('e7f8a9b0-c1d2-3456-efab-567890123456', 'electronics', 15, TRUE, 10.00, ARRAY['unopened', 'defective', 'wrong_item'], 'Los productos electrónicos pueden devolverse en un plazo de 15 días desde la entrega. Deben incluir el embalaje original y todos los accesorios. Se aplica una tarifa de reposición del 10% para productos abiertos no defectuosos. Los productos defectuosos se reembolsan íntegramente.'),
    ('f8a9b0c1-d2e3-4567-fabc-678901234567', 'fashion', 30, FALSE, 0.00, ARRAY['unopened', 'wrong_size', 'wrong_item', 'not_as_described'], 'Las prendas de moda tienen un plazo de devolución de 30 días. No es necesario el embalaje original pero las prendas deben estar sin usar y con las etiquetas puestas. No se cobra tarifa de reposición. Cambios de talla disponibles según stock.'),
    ('a9b0c1d2-e3f4-5678-abcd-789012345678', 'home_appliances', 30, TRUE, 5.00, ARRAY['unopened', 'defective', 'wrong_item'], 'Los electrodomésticos pueden devolverse en 30 días. Requieren embalaje original. Tarifa de reposición del 5% para productos abiertos funcionales. Garantía de 2 años para defectos de fabricación.'),
    ('b0c1d2e3-f4a5-6789-bcde-890123456789', 'books', 14, FALSE, 0.00, ARRAY['wrong_item', 'defective'], 'Los libros solo pueden devolverse en 14 días si se recibió un artículo incorrecto o el producto está defectuoso (páginas faltantes, daño de impresión). No se aceptan devoluciones por cambio de opinión.');
