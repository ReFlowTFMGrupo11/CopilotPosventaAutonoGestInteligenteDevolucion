-- =========================================================================
-- ReFlow -- Kit de datos QA para pruebas manuales via chat UI
-- Generado a partir de un subconjunto curado de dataset/eval_cases.csv
-- (24 casos, cubriendo: valid / invalid / human_review y las reglas de
-- plazo, importe > 100 EUR, zona frontera, higiene/precinto roto, motivo
-- sensible, cliente frecuente, estado no admitido y falta de evidencia foto).
--
-- Este script es ADITIVO e IDEMPOTENTE: usa ON CONFLICT DO NOTHING, así que
-- se puede ejecutar sobre una base ya migrada (con o sin
-- supabase/seed_synthetic.sql cargado) sin romper nada ni duplicar filas.
--
-- A PROPOSITO no inserta return_requests/return_items: esos los debe crear
-- el propio agente al procesar la conversacion en el chat (Streamlit) -- es
-- justo lo que se quiere probar. Ver dataset/qa_manual_testing_cases.xlsx
-- para el guion de pruebas (mensaje a pegar en el chat por caso, con el
-- order_id/order_item_id ya insertados).
-- =========================================================================

-- -------------------------------------------------------------------------
-- 1) Politicas de devolucion (defensivo: si ya existen por categoria con
--    active = TRUE -- p.ej. porque ya cargaste seed_synthetic.sql -- se
--    conserva la existente y esta se ignora).
-- -------------------------------------------------------------------------
INSERT INTO return_policies (category, max_return_days, requires_original_packaging, restocking_fee_percent, allowed_conditions, policy_text, active) VALUES
    ('alimentacion', 14, FALSE, 0, ARRAY['unopened','defective','wrong_item'], 'Politica QA de pruebas para Alimentacion y Gran Consumo: plazo maximo de 14 dias desde la entrega.', TRUE),
    ('bebe_puericultura', 30, FALSE, 0, ARRAY['unopened','defective','wrong_item','not_as_described'], 'Politica QA de pruebas para Bebe y Puericultura: plazo maximo de 30 dias desde la entrega.', TRUE),
    ('calzado', 30, TRUE, 0, ARRAY['unopened','defective','wrong_item','not_as_described'], 'Politica QA de pruebas para Calzado: plazo maximo de 30 dias desde la entrega.', TRUE),
    ('cosmetica_perfumeria', 21, FALSE, 0, ARRAY['unopened','defective','wrong_item'], 'Politica QA de pruebas para Cosmetica y Perfumeria: plazo maximo de 21 dias desde la entrega.', TRUE),
    ('deportes_aire_libre', 30, FALSE, 0, ARRAY['unopened','defective','wrong_item','not_as_described'], 'Politica QA de pruebas para Deportes y Aire Libre: plazo maximo de 30 dias desde la entrega.', TRUE),
    ('drogueria_salud', 21, FALSE, 0, ARRAY['unopened','defective','wrong_item'], 'Politica QA de pruebas para Drogueria, Higiene y Salud: plazo maximo de 21 dias desde la entrega.', TRUE),
    ('electrodomesticos', 30, TRUE, 0, ARRAY['unopened','defective','wrong_item','not_as_described'], 'Politica QA de pruebas para Electrodomesticos: plazo maximo de 30 dias desde la entrega.', TRUE),
    ('electronica_informatica', 30, FALSE, 0, ARRAY['unopened','defective','wrong_item','not_as_described','missing_parts'], 'Politica QA de pruebas para Electronica e Informatica: plazo maximo de 30 dias desde la entrega.', TRUE),
    ('jardineria_bricolaje', 30, FALSE, 0, ARRAY['unopened','defective','wrong_item'], 'Politica QA de pruebas para Jardineria y Bricolaje: plazo maximo de 30 dias desde la entrega.', TRUE),
    ('juguetes', 30, FALSE, 0, ARRAY['unopened','defective','wrong_item','not_as_described'], 'Politica QA de pruebas para Juguetes: plazo maximo de 30 dias desde la entrega.', TRUE),
    ('libros_papeleria', 21, FALSE, 0, ARRAY['unopened','defective','wrong_item'], 'Politica QA de pruebas para Libros, Papeleria y Oficina: plazo maximo de 21 dias desde la entrega.', TRUE),
    ('mascotas', 21, FALSE, 0, ARRAY['unopened','defective','wrong_item'], 'Politica QA de pruebas para Mascotas: plazo maximo de 21 dias desde la entrega.', TRUE),
    ('muebles', 14, TRUE, 15, ARRAY['unopened','defective','wrong_item'], 'Politica QA de pruebas para Muebles: plazo maximo de 14 dias desde la entrega.', TRUE)
ON CONFLICT (category) WHERE active = TRUE DO NOTHING;

-- -------------------------------------------------------------------------
-- 2) Clientes de prueba (uno por caso)
-- -------------------------------------------------------------------------
INSERT INTO customers (id, email, full_name, phone, address) VALUES
    ('2a3546a2-3253-42ac-af56-b69b970b50f7', 'qa.caso01@reflow-test.local', 'QA Caso 01 (jardineria_bricolaje)', '+34600000001', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('123e9492-3945-484b-b666-ab870df1fca1', 'qa.caso02@reflow-test.local', 'QA Caso 02 (electrodomesticos)', '+34600000002', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('fe1d571d-75ca-49d0-a286-c3b645ca94dc', 'qa.caso03@reflow-test.local', 'QA Caso 03 (juguetes)', '+34600000003', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('2b89681c-fe63-4d5f-be58-cfe3dc737581', 'qa.caso04@reflow-test.local', 'QA Caso 04 (muebles)', '+34600000004', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('7cfb5462-88d7-494f-8917-3579525fcb25', 'qa.caso05@reflow-test.local', 'QA Caso 05 (electronica_informatica)', '+34600000005', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('e2ab2cde-52d3-4605-a500-79fd53b8e842', 'qa.caso06@reflow-test.local', 'QA Caso 06 (drogueria_salud)', '+34600000006', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('a141b32e-e84e-4bcb-a06a-8396876f092b', 'qa.caso07@reflow-test.local', 'QA Caso 07 (libros_papeleria)', '+34600000007', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('f1a32d53-7b16-4992-b74f-7ed1e26f93a4', 'qa.caso08@reflow-test.local', 'QA Caso 08 (alimentacion)', '+34600000008', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('1d4f2aba-65f2-4146-a019-b8a11d147070', 'qa.caso09@reflow-test.local', 'QA Caso 09 (libros_papeleria)', '+34600000009', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('6e007106-6259-499a-8f65-3bb50cc15c02', 'qa.caso10@reflow-test.local', 'QA Caso 10 (muebles)', '+34600000010', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('47ea7784-69f8-4ee9-b89e-ed921043b6c4', 'qa.caso11@reflow-test.local', 'QA Caso 11 (cosmetica_perfumeria)', '+34600000011', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('bfad669e-abf2-4ea2-935e-c55fd00911fa', 'qa.caso12@reflow-test.local', 'QA Caso 12 (mascotas)', '+34600000012', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('221b915d-c030-40b4-aa70-e7f1a34e1372', 'qa.caso13@reflow-test.local', 'QA Caso 13 (deportes_aire_libre)', '+34600000013', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('a5d2f4e0-5fad-4145-b6dc-18ff009d62ea', 'qa.caso14@reflow-test.local', 'QA Caso 14 (jardineria_bricolaje)', '+34600000014', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('4dd68075-b8ae-4374-ac8a-c1453fce48bb', 'qa.caso15@reflow-test.local', 'QA Caso 15 (electrodomesticos)', '+34600000015', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('3043d767-0050-46c2-91cd-eb5e29ff849f', 'qa.caso16@reflow-test.local', 'QA Caso 16 (alimentacion)', '+34600000016', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('13c91723-bf54-4879-8a94-99a524c4d015', 'qa.caso17@reflow-test.local', 'QA Caso 17 (alimentacion)', '+34600000017', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('34f8b992-1113-424e-976d-1f66e90f4334', 'qa.caso18@reflow-test.local', 'QA Caso 18 (electrodomesticos)', '+34600000018', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('d00f58ec-10d1-418f-b741-8d6bf6e50b31', 'qa.caso19@reflow-test.local', 'QA Caso 19 (calzado)', '+34600000019', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('6b1062d3-0732-4032-8e81-cb571f7c0f97', 'qa.caso20@reflow-test.local', 'QA Caso 20 (bebe_puericultura)', '+34600000020', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('4641d9f0-18cb-4b58-b943-be0bd7031a0a', 'qa.caso21@reflow-test.local', 'QA Caso 21 (drogueria_salud)', '+34600000021', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('c18fa474-a5b5-464f-a5e1-99577a9a171a', 'qa.caso22@reflow-test.local', 'QA Caso 22 (alimentacion)', '+34600000022', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('cbae7eb6-e36c-4f06-a450-bf43c2765e1d', 'qa.caso23@reflow-test.local', 'QA Caso 23 (cosmetica_perfumeria)', '+34600000023', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('7b54fb1f-1000-4909-ae49-2e2fef968867', 'qa.caso24@reflow-test.local', 'QA Caso 24 (electronica_informatica)', '+34600000024', '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb)
ON CONFLICT (email) DO NOTHING;

-- -------------------------------------------------------------------------
-- 3) Productos de prueba (uno por caso)
-- -------------------------------------------------------------------------
INSERT INTO products (id, sku, name, description, category, price, weight_kg, image_url) VALUES
    ('26dfacba-5b36-4a82-8621-5d86a7d3d9d3', 'QA-0001-JARD', 'Producto de prueba QA #01 - Jardineria y Bricolaje', 'Articulo ficticio de QA para el caso 01 (case_id origen: fd4500ff-6b1a-4df5-b093-11adffa011e9).', 'jardineria_bricolaje', 89.99, NULL, NULL),
    ('e2b1e655-084a-44d0-b732-e07d0be806ca', 'QA-0002-ELEC', 'Producto de prueba QA #02 - Electrodomesticos', 'Articulo ficticio de QA para el caso 02 (case_id origen: 7728e476-bad7-4008-9abd-b70a8e6c84c8).', 'electrodomesticos', 289.99, NULL, NULL),
    ('de7c9b54-b2b8-48d1-bd5e-e37201f94651', 'QA-0003-JUGU', 'Producto de prueba QA #03 - Juguetes', 'Articulo ficticio de QA para el caso 03 (case_id origen: d554dd7c-1e1c-49fa-a5ad-3b2bed74df6b).', 'juguetes', 55.98, NULL, NULL),
    ('b89856bb-5f66-4147-801e-0d2017742cbf', 'QA-0004-MUEB', 'Producto de prueba QA #04 - Muebles', 'Articulo ficticio de QA para el caso 04 (case_id origen: 87dfdfe7-36e3-4936-b1ce-786fe7897e87).', 'muebles', 2099.97, NULL, NULL),
    ('35ffafb3-de3f-4cd6-ab36-ef2e6b7c1217', 'QA-0005-ELEC', 'Producto de prueba QA #05 - Electronica e Informatica', 'Articulo ficticio de QA para el caso 05 (case_id origen: e2fdf7b5-f978-46c8-8576-27a46ef83f3d).', 'electronica_informatica', 59.99, NULL, NULL),
    ('c93d6eeb-a461-4b28-a525-6663c294c639', 'QA-0006-DROG', 'Producto de prueba QA #06 - Drogueria, Higiene y Salud', 'Articulo ficticio de QA para el caso 06 (case_id origen: 5cbc2c75-6389-4c6b-8707-a839524e07b4).', 'drogueria_salud', 22.99, NULL, NULL),
    ('05540e07-26a3-4f80-acc5-2e3b10fdb5eb', 'QA-0007-LIBR', 'Producto de prueba QA #07 - Libros, Papeleria y Oficina', 'Articulo ficticio de QA para el caso 07 (case_id origen: 908abbe1-0469-4b28-a06c-f7852c5ff134).', 'libros_papeleria', 33.98, NULL, NULL),
    ('1e5c85e9-8475-427d-b3c7-68d44eeb852a', 'QA-0008-ALIM', 'Producto de prueba QA #08 - Alimentacion y Gran Consumo', 'Articulo ficticio de QA para el caso 08 (case_id origen: 237a4e52-8ef0-46ea-9ef7-118c60b68e25).', 'alimentacion', 19.98, NULL, NULL),
    ('d77b3e21-7e40-4639-88ec-0905b91dc3a5', 'QA-0009-LIBR', 'Producto de prueba QA #09 - Libros, Papeleria y Oficina', 'Articulo ficticio de QA para el caso 09 (case_id origen: 1fa5c5d6-3a04-4432-8b68-590874070981).', 'libros_papeleria', 50.97, NULL, NULL),
    ('1e33f423-476b-44da-87f8-bd15fe57bcd6', 'QA-0010-MUEB', 'Producto de prueba QA #10 - Muebles', 'Articulo ficticio de QA para el caso 10 (case_id origen: 3f5bd4e3-caa1-4167-861b-3a7c20da6f83).', 'muebles', 149.99, NULL, NULL),
    ('3214675f-8e4e-437b-802c-0149b7a8acad', 'QA-0011-COSM', 'Producto de prueba QA #11 - Cosmetica y Perfumeria', 'Articulo ficticio de QA para el caso 11 (case_id origen: 0e00598e-cd01-4c9e-8498-3d07f1923237).', 'cosmetica_perfumeria', 19.98, NULL, NULL),
    ('9ac5972e-a36b-43c9-b561-7848fe8b3013', 'QA-0012-MASC', 'Producto de prueba QA #12 - Mascotas', 'Articulo ficticio de QA para el caso 12 (case_id origen: faab888c-dc07-48a5-b62b-ad3d3fba1f1f).', 'mascotas', 44.99, NULL, NULL),
    ('155f9c7c-047c-4ed2-864d-ae1d2d5299b5', 'QA-0013-DEPO', 'Producto de prueba QA #13 - Deportes y Aire Libre', 'Articulo ficticio de QA para el caso 13 (case_id origen: a91ac9f8-d61b-4434-84a6-ff5ebb0bdce8).', 'deportes_aire_libre', 34.99, NULL, NULL),
    ('b07e0750-20cc-43bb-8491-ba95324780d2', 'QA-0014-JARD', 'Producto de prueba QA #14 - Jardineria y Bricolaje', 'Articulo ficticio de QA para el caso 14 (case_id origen: 84bf7d90-ee68-4f63-bde1-03e532465939).', 'jardineria_bricolaje', 149.99, NULL, NULL),
    ('ace56f2a-42ad-4a9e-b22f-9d9dce92664a', 'QA-0015-ELEC', 'Producto de prueba QA #15 - Electrodomesticos', 'Articulo ficticio de QA para el caso 15 (case_id origen: 62001e2d-2fe0-4181-8a06-4418d4d705ec).', 'electrodomesticos', 1269.96, NULL, NULL),
    ('9ed4a012-521a-45d2-8670-586bcc8002b6', 'QA-0016-ALIM', 'Producto de prueba QA #16 - Alimentacion y Gran Consumo', 'Articulo ficticio de QA para el caso 16 (case_id origen: e6f8f7dc-2660-40c5-9d99-78e57c64aacd).', 'alimentacion', 26.97, NULL, NULL),
    ('1878035c-8d94-47f7-b854-38d8abf99a65', 'QA-0017-ALIM', 'Producto de prueba QA #17 - Alimentacion y Gran Consumo', 'Articulo ficticio de QA para el caso 17 (case_id origen: f3321348-3b17-4ded-9593-eb44ced5fcd8).', 'alimentacion', 8.99, NULL, NULL),
    ('5ce2b034-dbe9-4253-8625-750a4056d857', 'QA-0018-ELEC', 'Producto de prueba QA #18 - Electrodomesticos', 'Articulo ficticio de QA para el caso 18 (case_id origen: 268c0e93-4c7a-4ae3-a77c-dc1bb26a6823).', 'electrodomesticos', 79.99, NULL, NULL),
    ('ee6c9d78-71aa-4f64-bbca-47d631ccfa3f', 'QA-0019-CALZ', 'Producto de prueba QA #19 - Calzado', 'Articulo ficticio de QA para el caso 19 (case_id origen: 23b71ba2-66fa-4a2a-942e-02c936df6eb8).', 'calzado', 49.98, NULL, NULL),
    ('42cbcfd0-4f43-407a-b16e-d026a3c5e239', 'QA-0020-BEBE', 'Producto de prueba QA #20 - Bebe y Puericultura', 'Articulo ficticio de QA para el caso 20 (case_id origen: ebf59bf5-3746-4a4a-9d61-4122dbbc8bfa).', 'bebe_puericultura', 79.99, NULL, NULL),
    ('4ff7f944-d646-4473-b61c-576c6037616a', 'QA-0021-DROG', 'Producto de prueba QA #21 - Drogueria, Higiene y Salud', 'Articulo ficticio de QA para el caso 21 (case_id origen: 435e4c1e-d6c1-4ff5-b93d-60a6f15745ae).', 'drogueria_salud', 9.98, NULL, NULL),
    ('0c3ebd6c-8da2-4cb9-be55-c40e5b9e3c3a', 'QA-0022-ALIM', 'Producto de prueba QA #22 - Alimentacion y Gran Consumo', 'Articulo ficticio de QA para el caso 22 (case_id origen: 6cb7f148-546d-4dd6-b65f-f09827e14025).', 'alimentacion', 59.97, NULL, NULL),
    ('f3151419-82ac-4c38-849f-34ce656bc098', 'QA-0023-COSM', 'Producto de prueba QA #23 - Cosmetica y Perfumeria', 'Articulo ficticio de QA para el caso 23 (case_id origen: 2536a7b6-3853-4876-9d14-fc4f71c82ad2).', 'cosmetica_perfumeria', 14.99, NULL, NULL),
    ('567159e4-1e19-4f47-a5dc-d8130b5bc728', 'QA-0024-ELEC', 'Producto de prueba QA #24 - Electronica e Informatica', 'Articulo ficticio de QA para el caso 24 (case_id origen: bf62e1b2-97ce-4f00-86b1-ae956446beb3).', 'electronica_informatica', 59.98, NULL, NULL)
ON CONFLICT (sku) DO NOTHING;

-- -------------------------------------------------------------------------
-- 4) Pedidos de prueba, YA ENTREGADOS hace 'days_since_delivery' dias
--    (calculado en el momento de ejecutar este script; ver GENERATION_STATS
--    en el Excel adjunto para el valor objetivo de cada caso).
-- -------------------------------------------------------------------------
INSERT INTO orders (id, customer_id, order_number, status, total_amount, shipping_address, ordered_at, delivered_at) VALUES
    ('6744b25d-2a31-4a62-9037-a496368112bd', '2a3546a2-3253-42ac-af56-b69b970b50f7', 'ORD-QA-0001', 'delivered', 89.99, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '9 days', NOW() - INTERVAL '6 days'),
    ('576a31bb-2f7b-4606-afc8-11b794edbfec', '123e9492-3945-484b-b666-ab870df1fca1', 'ORD-QA-0002', 'delivered', 289.99, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '19 days', NOW() - INTERVAL '16 days'),
    ('07c9dec6-8756-4dba-9306-93eed8be375f', 'fe1d571d-75ca-49d0-a286-c3b645ca94dc', 'ORD-QA-0003', 'delivered', 55.98, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '4 days', NOW() - INTERVAL '1 days'),
    ('0af591e5-cbf3-4676-88fa-f6f2d629774c', '2b89681c-fe63-4d5f-be58-cfe3dc737581', 'ORD-QA-0004', 'delivered', 2099.97, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '59 days', NOW() - INTERVAL '56 days'),
    ('82d610f6-d46c-44ef-8dad-71ca8f4e62a7', '7cfb5462-88d7-494f-8917-3579525fcb25', 'ORD-QA-0005', 'delivered', 59.99, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '20 days', NOW() - INTERVAL '17 days'),
    ('5f3d9bd0-0989-4cb2-a889-562461dae9d7', 'e2ab2cde-52d3-4605-a500-79fd53b8e842', 'ORD-QA-0006', 'delivered', 22.99, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '17 days', NOW() - INTERVAL '14 days'),
    ('968f8839-4674-4904-8571-c56b6e115221', 'a141b32e-e84e-4bcb-a06a-8396876f092b', 'ORD-QA-0007', 'delivered', 33.98, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '26 days', NOW() - INTERVAL '23 days'),
    ('332b9aa6-b45f-4d15-b0b3-374d238fc302', 'f1a32d53-7b16-4992-b74f-7ed1e26f93a4', 'ORD-QA-0008', 'delivered', 19.98, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '11 days', NOW() - INTERVAL '8 days'),
    ('07d8e64b-54f9-44ce-9d44-96bfecdc9deb', '1d4f2aba-65f2-4146-a019-b8a11d147070', 'ORD-QA-0009', 'delivered', 50.97, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '9 days', NOW() - INTERVAL '6 days'),
    ('3e5e71c4-36a7-469a-bdcb-816358a64d77', '6e007106-6259-499a-8f65-3bb50cc15c02', 'ORD-QA-0010', 'delivered', 149.99, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '10 days', NOW() - INTERVAL '7 days'),
    ('a66fa6fd-82b3-45c1-9298-1ad31a578f03', '47ea7784-69f8-4ee9-b89e-ed921043b6c4', 'ORD-QA-0011', 'delivered', 19.98, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '17 days', NOW() - INTERVAL '14 days'),
    ('cbc992d3-f06e-47c3-9759-f99490984ccd', 'bfad669e-abf2-4ea2-935e-c55fd00911fa', 'ORD-QA-0012', 'delivered', 44.99, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '7 days', NOW() - INTERVAL '4 days'),
    ('8cda7c27-42ef-4da4-94a2-babbb1e997c9', '221b915d-c030-40b4-aa70-e7f1a34e1372', 'ORD-QA-0013', 'delivered', 34.99, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '8 days', NOW() - INTERVAL '5 days'),
    ('89e10b98-3c4a-4e57-9096-53de5d838e51', 'a5d2f4e0-5fad-4145-b6dc-18ff009d62ea', 'ORD-QA-0014', 'delivered', 149.99, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '7 days', NOW() - INTERVAL '4 days'),
    ('6c0ce408-9c3e-45b3-a60b-c5c356d1419d', '4dd68075-b8ae-4374-ac8a-c1453fce48bb', 'ORD-QA-0015', 'delivered', 1269.96, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '7 days', NOW() - INTERVAL '4 days'),
    ('504c89c8-76be-44ef-973e-c31e92608a6e', '3043d767-0050-46c2-91cd-eb5e29ff849f', 'ORD-QA-0016', 'delivered', 26.97, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '35 days', NOW() - INTERVAL '32 days'),
    ('99353aa4-39b8-4fd2-86ff-1c58d7ee9176', '13c91723-bf54-4879-8a94-99a524c4d015', 'ORD-QA-0017', 'delivered', 8.99, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '22 days', NOW() - INTERVAL '19 days'),
    ('877f366e-c2ba-423a-9dc5-2e8e1ecf8fa1', '34f8b992-1113-424e-976d-1f66e90f4334', 'ORD-QA-0018', 'delivered', 79.99, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '33 days', NOW() - INTERVAL '30 days'),
    ('89f2edb9-eaf1-4a7d-9f10-8dc5592ae60d', 'd00f58ec-10d1-418f-b741-8d6bf6e50b31', 'ORD-QA-0019', 'delivered', 49.98, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '33 days', NOW() - INTERVAL '30 days'),
    ('2b58e6e1-909f-4d9d-b4bd-962ec333261b', '6b1062d3-0732-4032-8e81-cb571f7c0f97', 'ORD-QA-0020', 'delivered', 79.99, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '9 days', NOW() - INTERVAL '6 days'),
    ('fea94f58-c662-46b1-ba92-e0bef5f0ff43', '4641d9f0-18cb-4b58-b943-be0bd7031a0a', 'ORD-QA-0021', 'delivered', 9.98, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '13 days', NOW() - INTERVAL '10 days'),
    ('92792737-81ac-442b-ad68-b9f4ad17ce26', 'c18fa474-a5b5-464f-a5e1-99577a9a171a', 'ORD-QA-0022', 'delivered', 59.97, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '8 days', NOW() - INTERVAL '5 days'),
    ('19bff230-1dba-4ddf-a99a-627329fa77cd', 'cbae7eb6-e36c-4f06-a450-bf43c2765e1d', 'ORD-QA-0023', 'delivered', 14.99, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '11 days', NOW() - INTERVAL '8 days'),
    ('728367f1-2a45-4d92-b320-fb3975aac387', '7b54fb1f-1000-4909-ae49-2e2fef968867', 'ORD-QA-0024', 'delivered', 59.98, '{"street": "Calle de Pruebas QA 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '19 days', NOW() - INTERVAL '16 days')
ON CONFLICT (order_number) DO NOTHING;

-- -------------------------------------------------------------------------
-- 5) Lineas de pedido (una por caso, cantidad 1)
-- -------------------------------------------------------------------------
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
    ('6b5f8c7b-a80a-487e-b8f3-79d1775eb6f4', '6744b25d-2a31-4a62-9037-a496368112bd', '26dfacba-5b36-4a82-8621-5d86a7d3d9d3', 1, 89.99, 89.99),
    ('23b6363a-2c3e-4442-8aa9-3fe9759e4d0b', '576a31bb-2f7b-4606-afc8-11b794edbfec', 'e2b1e655-084a-44d0-b732-e07d0be806ca', 1, 289.99, 289.99),
    ('335fea29-6cbe-4382-9445-d36d98cc8ba2', '07c9dec6-8756-4dba-9306-93eed8be375f', 'de7c9b54-b2b8-48d1-bd5e-e37201f94651', 1, 55.98, 55.98),
    ('55980820-5b22-4029-a068-925dec285e8a', '0af591e5-cbf3-4676-88fa-f6f2d629774c', 'b89856bb-5f66-4147-801e-0d2017742cbf', 1, 2099.97, 2099.97),
    ('7d277e49-ae54-46d7-b5d9-d83630bc79fa', '82d610f6-d46c-44ef-8dad-71ca8f4e62a7', '35ffafb3-de3f-4cd6-ab36-ef2e6b7c1217', 1, 59.99, 59.99),
    ('10ec73d2-6c60-453a-ac56-2de35e85e5d8', '5f3d9bd0-0989-4cb2-a889-562461dae9d7', 'c93d6eeb-a461-4b28-a525-6663c294c639', 1, 22.99, 22.99),
    ('2e7563a9-e871-4aad-97cb-f95c83ae7784', '968f8839-4674-4904-8571-c56b6e115221', '05540e07-26a3-4f80-acc5-2e3b10fdb5eb', 1, 33.98, 33.98),
    ('d8e9039d-fa17-46cb-961d-0477d7b7b1fb', '332b9aa6-b45f-4d15-b0b3-374d238fc302', '1e5c85e9-8475-427d-b3c7-68d44eeb852a', 1, 19.98, 19.98),
    ('64f00e06-1edc-4b5b-a749-c9aabf456cea', '07d8e64b-54f9-44ce-9d44-96bfecdc9deb', 'd77b3e21-7e40-4639-88ec-0905b91dc3a5', 1, 50.97, 50.97),
    ('e90ca6b6-2d31-42d2-b7b2-dadaf0e56b33', '3e5e71c4-36a7-469a-bdcb-816358a64d77', '1e33f423-476b-44da-87f8-bd15fe57bcd6', 1, 149.99, 149.99),
    ('62839db6-bbe9-4e4b-a9d8-555295cc8bbe', 'a66fa6fd-82b3-45c1-9298-1ad31a578f03', '3214675f-8e4e-437b-802c-0149b7a8acad', 1, 19.98, 19.98),
    ('81041352-e505-4e31-98c2-8b5de9d86d44', 'cbc992d3-f06e-47c3-9759-f99490984ccd', '9ac5972e-a36b-43c9-b561-7848fe8b3013', 1, 44.99, 44.99),
    ('02b74b5f-09eb-469a-9c99-06dc098a43a6', '8cda7c27-42ef-4da4-94a2-babbb1e997c9', '155f9c7c-047c-4ed2-864d-ae1d2d5299b5', 1, 34.99, 34.99),
    ('ecc9a67b-fbbd-4178-bcf8-cf788abcd15c', '89e10b98-3c4a-4e57-9096-53de5d838e51', 'b07e0750-20cc-43bb-8491-ba95324780d2', 1, 149.99, 149.99),
    ('96c89253-dc47-42f6-b1cb-ca3b9b9dd3fc', '6c0ce408-9c3e-45b3-a60b-c5c356d1419d', 'ace56f2a-42ad-4a9e-b22f-9d9dce92664a', 1, 1269.96, 1269.96),
    ('d06327bf-7798-42ea-a7c0-b835dd882b40', '504c89c8-76be-44ef-973e-c31e92608a6e', '9ed4a012-521a-45d2-8670-586bcc8002b6', 1, 26.97, 26.97),
    ('aa7ec016-3986-4520-a8ea-67fb71612dda', '99353aa4-39b8-4fd2-86ff-1c58d7ee9176', '1878035c-8d94-47f7-b854-38d8abf99a65', 1, 8.99, 8.99),
    ('304f5548-0267-4ff8-8457-ce804e63341e', '877f366e-c2ba-423a-9dc5-2e8e1ecf8fa1', '5ce2b034-dbe9-4253-8625-750a4056d857', 1, 79.99, 79.99),
    ('8d860a71-ff20-49f7-b7da-0c7fa9855e67', '89f2edb9-eaf1-4a7d-9f10-8dc5592ae60d', 'ee6c9d78-71aa-4f64-bbca-47d631ccfa3f', 1, 49.98, 49.98),
    ('c26199c8-77ff-41b9-ba0b-db6dd3eece0e', '2b58e6e1-909f-4d9d-b4bd-962ec333261b', '42cbcfd0-4f43-407a-b16e-d026a3c5e239', 1, 79.99, 79.99),
    ('a552007b-6934-4464-9e9e-ede8e9f00fa7', 'fea94f58-c662-46b1-ba92-e0bef5f0ff43', '4ff7f944-d646-4473-b61c-576c6037616a', 1, 9.98, 9.98),
    ('f4f68c84-5983-44e2-9166-2800ae5382db', '92792737-81ac-442b-ad68-b9f4ad17ce26', '0c3ebd6c-8da2-4cb9-be55-c40e5b9e3c3a', 1, 59.97, 59.97),
    ('81590185-3cd6-4799-b4a5-4a8fbb82b37c', '19bff230-1dba-4ddf-a99a-627329fa77cd', 'f3151419-82ac-4c38-849f-34ce656bc098', 1, 14.99, 14.99),
    ('0fa99113-9dfb-41ef-b243-91ed4fdb84e2', '728367f1-2a45-4d92-b320-fb3975aac387', '567159e4-1e19-4f47-a5dc-d8130b5bc728', 1, 59.98, 59.98)
ON CONFLICT (id) DO NOTHING;

-- -------------------------------------------------------------------------
-- 6) Verificacion: recupera order_id / order_item_id desde Supabase por si
--    se pierde el Excel (mismos valores que en qa_manual_testing_cases.xlsx).
-- -------------------------------------------------------------------------
SELECT
    o.order_number,
    o.id            AS order_id,
    oi.id           AS order_item_id,
    c.email         AS customer_email,
    p.category,
    p.price         AS refund_amount,
    o.delivered_at,
    EXTRACT(DAY FROM NOW() - o.delivered_at)::int AS dias_desde_entrega_actual
FROM orders o
JOIN customers c ON c.id = o.customer_id
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id
WHERE o.order_number LIKE 'ORD-QA-%'
ORDER BY o.order_number;
