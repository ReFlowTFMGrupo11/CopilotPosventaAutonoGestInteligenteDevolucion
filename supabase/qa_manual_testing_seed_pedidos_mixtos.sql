-- =========================================================================
-- ReFlow -- Kit de datos QA: PEDIDOS MIXTOS (varias categorias por pedido,
-- elegibilidad de devolucion parcial)
--
-- Complementa a supabase/qa_manual_testing_seed.sql (que solo cubre pedidos de
-- UN articulo). Reutiliza las mismas 13 categorias/return_policies ya insertadas
-- por ese script -- EJECUTAR DESPUES de qa_manual_testing_seed.sql (o de
-- seed_synthetic.sql), no antes.
--
-- Generado por dataset/generate_mixed_qa_kit.py. Guion de pruebas (mensaje a
-- pegar en el chat por caso) en
-- dataset/qa_manual_testing_casos_pedidos_mixtos.xlsx.
--
-- ADITIVO e IDEMPOTENTE (ON CONFLICT DO NOTHING). A PROPOSITO no inserta
-- return_requests/return_items: los debe crear el propio agente al procesar la
-- conversacion -- es justo lo que se quiere probar.
-- =========================================================================

-- -------------------------------------------------------------------------
-- 1) Clientes de prueba (uno por caso mixto)
-- -------------------------------------------------------------------------
INSERT INTO customers (id, email, full_name, phone, address) VALUES
    ('0cf624c3-e5ba-4ac3-ba09-d551e4f59609', 'qa.casomixto001@reflow-test.local', 'QA Mixto 001 (Electronica e Informatica + Cosmetica y Perfumeria)', '+34600000001', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('150f572e-27e0-4364-8ccd-699d5945c223', 'qa.casomixto002@reflow-test.local', 'QA Mixto 002 (Electrodomesticos + Drogueria y Salud)', '+34600000002', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('38f8f399-84e5-4215-ad65-b52ae1364f73', 'qa.casomixto003@reflow-test.local', 'QA Mixto 003 (Juguetes + Libros y Papeleria + Alimentacion)', '+34600000003', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('0a167878-fa00-47c6-b2b9-68638c6589a9', 'qa.casomixto004@reflow-test.local', 'QA Mixto 004 (Cosmetica y Perfumeria + Alimentacion)', '+34600000004', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('0c14d593-a08b-4a34-8f16-6e1dce77e11b', 'qa.casomixto005@reflow-test.local', 'QA Mixto 005 (Calzado + Calzado)', '+34600000005', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('2d35af0b-9a3a-46d8-99ab-8c67042b9b26', 'qa.casomixto006@reflow-test.local', 'QA Mixto 006 (Juguetes + Mascotas)', '+34600000006', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('9384c33a-53ee-4c8c-8a82-271248406a1a', 'qa.casomixto007@reflow-test.local', 'QA Mixto 007 (Electrodomesticos + Deportes y Aire Libre)', '+34600000007', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb)
ON CONFLICT (email) DO NOTHING;

-- -------------------------------------------------------------------------
-- 2) Productos de prueba (varios por caso, distinta categoria cada uno)
-- -------------------------------------------------------------------------
INSERT INTO products (id, sku, name, description, category, price, weight_kg, image_url) VALUES
    ('d8a3a304-8742-4a18-8522-56351baf8ce8', 'QAM-001-01', 'Auriculares Bluetooth Pro', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-001, item 1.', 'electronica_informatica', 39.99, NULL, NULL),
    ('3dfba202-f382-4111-a9b1-a7fd79dc50c2', 'QAM-001-02', 'Perfume Eau de Parfum 50ml', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-001, item 2.', 'cosmetica_perfumeria', 29.99, NULL, NULL),
    ('97179628-efff-45a7-bb50-3b2fb7889774', 'QAM-002-01', 'Microondas Digital 20L', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-002, item 1.', 'electrodomesticos', 149.99, NULL, NULL),
    ('7e9ca431-c188-4fb5-bf52-a1439af309d6', 'QAM-002-02', 'Champu Anticaspa 400ml', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-002, item 2.', 'drogueria_salud', 12.99, NULL, NULL),
    ('a0820cf8-7de4-4973-b0bf-e3f3f53f2319', 'QAM-003-01', 'Puzzle 1000 Piezas Paisaje', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-003, item 1.', 'juguetes', 24.99, NULL, NULL),
    ('32990b3e-f8e6-4831-9612-fe8d4eb214fc', 'QAM-003-02', 'Agenda 2026 Tapa Dura', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-003, item 2.', 'libros_papeleria', 15.99, NULL, NULL),
    ('73be6009-7c39-4e59-8759-9b09e50078c9', 'QAM-003-03', 'Lote de Conservas Gourmet', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-003, item 3.', 'alimentacion', 18.50, NULL, NULL),
    ('57aba350-ffa3-4fce-b090-e089ef65419d', 'QAM-004-01', 'Crema Facial Antiedad', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-004, item 1.', 'cosmetica_perfumeria', 22.99, NULL, NULL),
    ('b4c1f150-310d-4d1b-88e7-c73c18bc667f', 'QAM-004-02', 'Aceite de Oliva Virgen Extra', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-004, item 2.', 'alimentacion', 9.99, NULL, NULL),
    ('0e25ba43-b97e-47ad-856d-eee7ea159692', 'QAM-005-01', 'Zapatillas Running Pro', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-005, item 1.', 'calzado', 59.99, NULL, NULL),
    ('6c4df112-afd1-45fd-95ab-dd57482bebe0', 'QAM-005-02', 'Botas de Senderismo', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-005, item 2.', 'calzado', 89.99, NULL, NULL),
    ('02d4757f-3318-47a7-9fd3-f7964d982198', 'QAM-006-01', 'Muñeco Articulado Superheroe', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-006, item 1.', 'juguetes', 19.99, NULL, NULL),
    ('869b41de-dc97-47b9-b06f-f558dbeb6453', 'QAM-006-02', 'Correa para Perro Ajustable', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-006, item 2.', 'mascotas', 14.99, NULL, NULL),
    ('dac2f717-e61c-452e-81ed-f47db79656ec', 'QAM-007-01', 'Aspiradora sin Cable', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-007, item 1.', 'electrodomesticos', 179.99, NULL, NULL),
    ('9de94575-b24c-4753-bcf9-6c481c7ed972', 'QAM-007-02', 'Bicicleta Estatica Plegable', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-007, item 2.', 'deportes_aire_libre', 259.99, NULL, NULL)
ON CONFLICT (sku) DO NOTHING;

-- -------------------------------------------------------------------------
-- 3) Pedidos de prueba, YA ENTREGADOS hace 'dias_entrega' dias (ver Excel)
-- -------------------------------------------------------------------------
INSERT INTO orders (id, customer_id, order_number, status, total_amount, shipping_address, ordered_at, delivered_at) VALUES
    ('5293d74e-10e3-4e71-b8c0-9452f410f756', '0cf624c3-e5ba-4ac3-ba09-d551e4f59609', 'ORD-QAM-0001', 'delivered', 69.98, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '11 days', NOW() - INTERVAL '8 days'),
    ('b1563596-a9d7-464b-805f-d14853a8c9ff', '150f572e-27e0-4364-8ccd-699d5945c223', 'ORD-QAM-0002', 'delivered', 162.98, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '15 days', NOW() - INTERVAL '12 days'),
    ('753d7563-8d68-4596-b67e-6abd939314ef', '38f8f399-84e5-4215-ad65-b52ae1364f73', 'ORD-QAM-0003', 'delivered', 59.48, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '23 days', NOW() - INTERVAL '20 days'),
    ('3b648f4e-42ef-47c9-be53-8f9ceb8ed87c', '0a167878-fa00-47c6-b2b9-68638c6589a9', 'ORD-QAM-0004', 'delivered', 32.98, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '21 days', NOW() - INTERVAL '18 days'),
    ('0c4855ae-d242-47b8-955c-a8d808b47ae7', '0c14d593-a08b-4a34-8f16-6e1dce77e11b', 'ORD-QAM-0005', 'delivered', 149.98, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '13 days', NOW() - INTERVAL '10 days'),
    ('9b92bf9e-10be-4ccf-825d-44c2906d647b', '2d35af0b-9a3a-46d8-99ab-8c67042b9b26', 'ORD-QAM-0006', 'delivered', 34.98, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '7 days', NOW() - INTERVAL '4 days'),
    ('723e1cbb-7897-49e8-a375-71dd24341303', '9384c33a-53ee-4c8c-8a82-271248406a1a', 'ORD-QAM-0007', 'delivered', 439.98, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '12 days', NOW() - INTERVAL '9 days')
ON CONFLICT (order_number) DO NOTHING;

-- -------------------------------------------------------------------------
-- 4) Lineas de pedido (varias por caso -- esto es lo que hace el pedido MIXTO)
-- -------------------------------------------------------------------------
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
    ('198485e9-ed82-44b8-a253-c547fa56d13e', '5293d74e-10e3-4e71-b8c0-9452f410f756', 'd8a3a304-8742-4a18-8522-56351baf8ce8', 1, 39.99, 39.99),
    ('4e5035cf-0d6d-4152-bbea-3552775efbd9', '5293d74e-10e3-4e71-b8c0-9452f410f756', '3dfba202-f382-4111-a9b1-a7fd79dc50c2', 1, 29.99, 29.99),
    ('a5367ce3-6a87-4b85-84ab-f047b8c7751d', 'b1563596-a9d7-464b-805f-d14853a8c9ff', '97179628-efff-45a7-bb50-3b2fb7889774', 1, 149.99, 149.99),
    ('ae74b5d7-aadc-48ab-bd9b-45d18658a330', 'b1563596-a9d7-464b-805f-d14853a8c9ff', '7e9ca431-c188-4fb5-bf52-a1439af309d6', 1, 12.99, 12.99),
    ('fa474206-98f8-4e98-8f53-1020ebe25879', '753d7563-8d68-4596-b67e-6abd939314ef', 'a0820cf8-7de4-4973-b0bf-e3f3f53f2319', 1, 24.99, 24.99),
    ('ebc78ff1-fb7e-4973-ba52-6e289745e208', '753d7563-8d68-4596-b67e-6abd939314ef', '32990b3e-f8e6-4831-9612-fe8d4eb214fc', 1, 15.99, 15.99),
    ('93c5962b-beff-4c79-9415-c661d9298855', '753d7563-8d68-4596-b67e-6abd939314ef', '73be6009-7c39-4e59-8759-9b09e50078c9', 1, 18.50, 18.50),
    ('2b2d136a-dc6d-427d-90ba-777c90d817d0', '3b648f4e-42ef-47c9-be53-8f9ceb8ed87c', '57aba350-ffa3-4fce-b090-e089ef65419d', 1, 22.99, 22.99),
    ('263410db-d5f1-4803-bf24-e605580ec27c', '3b648f4e-42ef-47c9-be53-8f9ceb8ed87c', 'b4c1f150-310d-4d1b-88e7-c73c18bc667f', 1, 9.99, 9.99),
    ('d441b6fa-ce08-416c-9861-dcd5676cf4de', '0c4855ae-d242-47b8-955c-a8d808b47ae7', '0e25ba43-b97e-47ad-856d-eee7ea159692', 1, 59.99, 59.99),
    ('d724a845-37a5-49ed-9fd0-9d7368aea97c', '0c4855ae-d242-47b8-955c-a8d808b47ae7', '6c4df112-afd1-45fd-95ab-dd57482bebe0', 1, 89.99, 89.99),
    ('60227fae-a954-4344-815c-147f0c3dd4b1', '9b92bf9e-10be-4ccf-825d-44c2906d647b', '02d4757f-3318-47a7-9fd3-f7964d982198', 1, 19.99, 19.99),
    ('487c8e34-ba95-47ee-b588-790d3cfb87f8', '9b92bf9e-10be-4ccf-825d-44c2906d647b', '869b41de-dc97-47b9-b06f-f558dbeb6453', 1, 14.99, 14.99),
    ('5a42f71b-6c5c-41ba-96c0-4b207a264e96', '723e1cbb-7897-49e8-a375-71dd24341303', 'dac2f717-e61c-452e-81ed-f47db79656ec', 1, 179.99, 179.99),
    ('6cc8e69f-49c4-4629-a205-acd33787a048', '723e1cbb-7897-49e8-a375-71dd24341303', '9de94575-b24c-4753-bcf9-6c481c7ed972', 1, 259.99, 259.99)
ON CONFLICT (id) DO NOTHING;

-- -------------------------------------------------------------------------
-- 5) Verificacion: un pedido = varias filas (una por order_item), con la
--    categoria y el importe de cada articulo para contrastar con el Excel.
-- -------------------------------------------------------------------------
SELECT
    o.order_number,
    o.id            AS order_id,
    oi.id           AS order_item_id,
    c.email         AS customer_email,
    p.name          AS product_name,
    p.category,
    p.price         AS importe,
    o.delivered_at,
    EXTRACT(DAY FROM NOW() - o.delivered_at)::int AS dias_desde_entrega_actual
FROM orders o
JOIN customers c ON c.id = o.customer_id
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id
WHERE o.order_number LIKE 'ORD-QAM-%'
ORDER BY o.order_number, p.category;
