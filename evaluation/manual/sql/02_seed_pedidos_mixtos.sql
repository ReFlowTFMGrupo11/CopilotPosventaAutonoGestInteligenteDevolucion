-- =========================================================================
-- ReFlow -- Kit de datos QA: PEDIDOS MIXTOS (varias categorias por pedido,
-- elegibilidad de devolucion parcial)
--
-- Complementa a supabase/qa_manual_testing_seed.sql (que solo cubre pedidos de
-- UN articulo). Reutiliza las mismas 13 categorias/return_policies ya insertadas
-- por ese script -- EJECUTAR DESPUES de qa_manual_testing_seed.sql (o de
-- seed_synthetic.sql), no antes.
--
-- Generado por evaluation/manual/scripts/generate_mixed_qa_kit.py. Guion de pruebas (mensaje a
-- pegar en el chat por caso) en
-- dataset/qa_manual_testing_casos_pedidos_mixtos.xlsx.
--
-- NO incluye QAM-001..QAM-007: sus INSERT ya se ejecutaron contra la BBDD y se omiten aqui
-- a proposito (siguen documentados en el Excel). Solo se insertan los casos nuevos:
-- QAM-009, QAM-010, QAM-011, QAM-012, QAM-013, QAM-014, QAM-015, QAM-016, QAM-017, QAM-018, QAM-019, QAM-020, QAM-021, QAM-022, QAM-023, QAM-024, QAM-025, QAM-026, QAM-027, QAM-028.
--
-- ADITIVO e IDEMPOTENTE (ON CONFLICT DO NOTHING). A PROPOSITO no inserta
-- return_requests/return_items: los debe crear el propio agente al procesar la
-- conversacion -- es justo lo que se quiere probar.
-- =========================================================================

-- -------------------------------------------------------------------------
-- 1) Clientes de prueba (uno por caso mixto)
-- -------------------------------------------------------------------------
INSERT INTO customers (id, email, full_name, phone, address) VALUES
    ('183046f4-5eeb-40b2-ac69-3f459997369a', 'qa.casomixto009@reflow-test.local', 'QA Mixto 009 (Jardineria y Bricolaje + Bebe y Puericultura)', '+34600000009', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('12428e0a-f16f-4c02-8686-2151bf770ef3', 'qa.casomixto010@reflow-test.local', 'QA Mixto 010 (Mascotas + Libros y Papeleria)', '+34600000010', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('36c764ca-f938-4996-93e7-46e48f8e6774', 'qa.casomixto011@reflow-test.local', 'QA Mixto 011 (Electronica e Informatica + Drogueria y Salud)', '+34600000011', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('a9e2563d-5483-4362-adb4-30ba295ef963', 'qa.casomixto012@reflow-test.local', 'QA Mixto 012 (Cosmetica y Perfumeria + Calzado)', '+34600000012', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('62885a71-417c-4443-a8d4-5198242b3f20', 'qa.casomixto013@reflow-test.local', 'QA Mixto 013 (Electrodomesticos + Juguetes + Libros y Papeleria)', '+34600000013', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('fa36cc4b-70f1-43e7-bf68-bce5f461a839', 'qa.casomixto014@reflow-test.local', 'QA Mixto 014 (Juguetes + Mascotas + Alimentacion)', '+34600000014', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('3918c24b-dfa3-4c62-9b63-717b20ecfe01', 'qa.casomixto015@reflow-test.local', 'QA Mixto 015 (Deportes y Aire Libre + Deportes y Aire Libre)', '+34600000015', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('0d548a0b-862d-4372-b6cb-d8a5016f4f05', 'qa.casomixto016@reflow-test.local', 'QA Mixto 016 (Alimentacion + Drogueria y Salud)', '+34600000016', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('2afd7a49-b6cb-472c-9766-2839c50435a1', 'qa.casomixto017@reflow-test.local', 'QA Mixto 017 (Electrodomesticos + Juguetes + Cosmetica y Perfumeria + Alimentacion)', '+34600000017', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('4f3fbe9d-cc38-4ffb-af81-59fd34a91c97', 'qa.casomixto018@reflow-test.local', 'QA Mixto 018 (Electronica e Informatica + Jardineria y Bricolaje)', '+34600000018', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('f74ea822-1e9f-429d-a1a1-1c8bea6db8cc', 'qa.casomixto019@reflow-test.local', 'QA Mixto 019 (Mascotas + Mascotas)', '+34600000019', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('ddbe2d65-221c-465f-b03e-c79057fe65dc', 'qa.casomixto020@reflow-test.local', 'QA Mixto 020 (Deportes y Aire Libre + Bebe y Puericultura + Mascotas)', '+34600000020', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('86787910-ab43-4942-90fe-ef5d3fa23eda', 'qa.casomixto021@reflow-test.local', 'QA Mixto 021 (Electronica e Informatica + Juguetes + Libros y Papeleria + Calzado + Deportes y Aire Libre)', '+34600000021', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('7d4e3725-613e-47d2-afdf-9a69c2e364ae', 'qa.casomixto022@reflow-test.local', 'QA Mixto 022 (Libros y Papeleria + Libros y Papeleria)', '+34600000022', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('29b6c5bc-7461-428c-b4c6-aea18689e8e3', 'qa.casomixto023@reflow-test.local', 'QA Mixto 023 (Electrodomesticos + Libros y Papeleria)', '+34600000023', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('fff1989a-e422-4444-ba78-92ce91926848', 'qa.casomixto024@reflow-test.local', 'QA Mixto 024 (Electrodomesticos + Juguetes + Cosmetica y Perfumeria)', '+34600000024', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('214c37ae-a5ca-4e71-bc66-2e2f3b8bbc83', 'qa.casomixto025@reflow-test.local', 'QA Mixto 025 (Calzado + Electronica e Informatica + Juguetes)', '+34600000025', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('fc18c1e2-e1b2-4598-8301-93d752212a89', 'qa.casomixto026@reflow-test.local', 'QA Mixto 026 (Calzado + Deportes y Aire Libre)', '+34600000026', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('a8d1a344-8f62-45e9-b4b6-11ccc9a46508', 'qa.casomixto027@reflow-test.local', 'QA Mixto 027 (Deportes y Aire Libre + Cosmetica y Perfumeria + Bebe y Puericultura)', '+34600000027', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb),
    ('a36cd009-97b0-44c1-80e7-8d33987162fd', 'qa.casomixto028@reflow-test.local', 'QA Mixto 028 (Electronica e Informatica + Jardineria y Bricolaje + Drogueria y Salud + Alimentacion)', '+34600000028', '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb)
ON CONFLICT (email) DO NOTHING;

-- -------------------------------------------------------------------------
-- 2) Productos de prueba (varios por caso, distinta categoria cada uno)
-- -------------------------------------------------------------------------
INSERT INTO products (id, sku, name, description, category, price, weight_kg, image_url) VALUES
    ('364d03cd-4264-4965-b37d-494745278cf9', 'QAM-009-01', 'Cortacesped Manual de Precision', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-009, item 1.', 'jardineria_bricolaje', 65.50, NULL, NULL),
    ('26252715-391a-4d97-aa6b-6743f153eeda', 'QAM-009-02', 'Trona Plegable de Viaje', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-009, item 2.', 'bebe_puericultura', 35.50, NULL, NULL),
    ('657c385c-8e06-411b-92f4-8294473ad13f', 'QAM-010-01', 'Rascador para Gato XL', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-010, item 1.', 'mascotas', 49.99, NULL, NULL),
    ('7f83b62d-508c-48ed-92a4-4033149f771a', 'QAM-010-02', 'Cuaderno de Notas A5 (Pack de 3)', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-010, item 2.', 'libros_papeleria', 49.99, NULL, NULL),
    ('67ddc496-6160-4581-baf0-34e85de2ea04', 'QAM-011-01', 'Portatil Ultradelgado 14 Pulgadas', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-011, item 1.', 'electronica_informatica', 899.00, NULL, NULL),
    ('1628212f-bc75-4d09-9ddb-244359adcb34', 'QAM-011-02', 'Gel de Ducha Dermoprotector', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-011, item 2.', 'drogueria_salud', 6.50, NULL, NULL),
    ('453c1bb3-5f62-4934-b5f5-c439af88c78a', 'QAM-012-01', 'Mascarilla Facial Set x5', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-012, item 1.', 'cosmetica_perfumeria', 15.99, NULL, NULL),
    ('8f9f3048-906a-498e-8a8a-e5212397f117', 'QAM-012-02', 'Zapatillas de Vestir', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-012, item 2.', 'calzado', 45.00, NULL, NULL),
    ('d98b3da4-7eac-4170-8e73-e4654bd8c0e5', 'QAM-013-01', 'Freidora de Aire 5L', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-013, item 1.', 'electrodomesticos', 79.99, NULL, NULL),
    ('49b8b96e-2d8c-422e-ab48-03e9e28b7bd9', 'QAM-013-02', 'Robot Teledirigido', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-013, item 2.', 'juguetes', 34.50, NULL, NULL),
    ('a75e8fe2-b328-400d-98f5-af13e9cdf29d', 'QAM-013-03', 'Mochila Escolar Ergonomica', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-013, item 3.', 'libros_papeleria', 27.99, NULL, NULL),
    ('3e859976-7e05-4897-ab36-ae165461569f', 'QAM-014-01', 'Cocina de Juguete de Madera', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-014, item 1.', 'juguetes', 38.00, NULL, NULL),
    ('04ac0e26-6184-496b-af1e-2970021edffe', 'QAM-014-02', 'Cama para Perro Mediana', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-014, item 2.', 'mascotas', 29.99, NULL, NULL),
    ('e31b03d2-7506-4dea-a4fc-b0817609dfae', 'QAM-014-03', 'Cafe en Grano 1kg', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-014, item 3.', 'alimentacion', 11.50, NULL, NULL),
    ('40466527-6783-4dce-8508-6d3287d419c4', 'QAM-015-01', 'Bicicleta de Montaña Junior', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-015, item 1.', 'deportes_aire_libre', 189.00, NULL, NULL),
    ('c370fae2-83ac-4e62-8f88-0367afd4968d', 'QAM-015-02', 'Casco de Ciclismo Ajustable', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-015, item 2.', 'deportes_aire_libre', 34.99, NULL, NULL),
    ('8dc7b594-807d-4865-8765-cd81d84f2872', 'QAM-016-01', 'Miel de Flores Silvestres 250g', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-016, item 1.', 'alimentacion', 7.99, NULL, NULL),
    ('f9eaecdf-8835-4d03-97b7-5b809b29a1b3', 'QAM-016-02', 'Champu Solido Ecologico', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-016, item 2.', 'drogueria_salud', 9.99, NULL, NULL),
    ('5c5daee9-cdb8-4a95-95d2-a00fe104201a', 'QAM-017-01', 'Aspiradora Robot', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-017, item 1.', 'electrodomesticos', 249.00, NULL, NULL),
    ('7f74fc61-05e8-40f7-b8db-b00476a05696', 'QAM-017-02', 'Puzzle Interactivo 3D', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-017, item 2.', 'juguetes', 15.00, NULL, NULL),
    ('198c4e95-e9a2-4146-993b-034287743f5e', 'QAM-017-03', 'Set de Maquillaje Basico', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-017, item 3.', 'cosmetica_perfumeria', 42.00, NULL, NULL),
    ('2e1f732b-40b8-4f6c-9849-61a1ee43a984', 'QAM-017-04', 'Chocolate Artesanal Caja', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-017, item 4.', 'alimentacion', 9.90, NULL, NULL),
    ('75272170-7661-4537-a519-bc4ba6bafb9a', 'QAM-018-01', 'Adaptador USB Multiple', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-018, item 1.', 'electronica_informatica', 14.99, NULL, NULL),
    ('4f02b224-459b-4b00-8ff2-647c7c559ebd', 'QAM-018-02', 'Guantes de Jardineria Reforzados', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-018, item 2.', 'jardineria_bricolaje', 9.99, NULL, NULL),
    ('4820aa93-e171-4464-b9f1-2489d6adf014', 'QAM-019-01', 'Transportadora para Perro Grande', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-019, item 1.', 'mascotas', 119.00, NULL, NULL),
    ('e328ff33-7d50-4434-9278-5d275e60bcf6', 'QAM-019-02', 'Comedero Automatico Programable', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-019, item 2.', 'mascotas', 54.00, NULL, NULL),
    ('cdd1a2f3-c5e4-4ecc-b181-46821202a768', 'QAM-020-01', 'Esterilla de Yoga Premium', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-020, item 1.', 'deportes_aire_libre', 24.99, NULL, NULL),
    ('4e2f6ad6-a213-4709-88eb-4beed0db1a23', 'QAM-020-02', 'Biberon Anticolico Set', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-020, item 2.', 'bebe_puericultura', 13.50, NULL, NULL),
    ('8717adf7-243f-48b8-95d8-e9a90f6e2730', 'QAM-020-03', 'Arnes para Perro Ajustable', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-020, item 3.', 'mascotas', 17.99, NULL, NULL),
    ('8365d664-9812-4d6d-9c34-6d493bf776af', 'QAM-021-01', 'Cargador Rapido USB-C 65W', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-021, item 1.', 'electronica_informatica', 24.99, NULL, NULL),
    ('3d83ebfd-a5d4-4058-bfc1-9832752ccd4f', 'QAM-021-02', 'Set de Bloques de Construccion', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-021, item 2.', 'juguetes', 19.99, NULL, NULL),
    ('7e624e44-ae99-4410-92f0-6a03f76ebd76', 'QAM-021-03', 'Calculadora Cientifica', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-021, item 3.', 'libros_papeleria', 22.50, NULL, NULL),
    ('3682e13f-109e-4df4-8711-23c4161bb652', 'QAM-021-04', 'Calcetines Tecnicos Running (Pack de 3)', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-021, item 4.', 'calzado', 14.99, NULL, NULL),
    ('14f922fa-a6c8-407c-9afe-e1b25930cdcc', 'QAM-021-05', 'Botella Termica 1L', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-021, item 5.', 'deportes_aire_libre', 24.99, NULL, NULL),
    ('a15d4f52-61ba-4789-bff8-d3c658a8cb24', 'QAM-022-01', 'Diario de Gratitud Tapa Blanda', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-022, item 1.', 'libros_papeleria', 11.99, NULL, NULL),
    ('3d4130a7-8319-4796-b44d-00c4aca3e282', 'QAM-022-02', 'Set de Boligrafos de Gel', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-022, item 2.', 'libros_papeleria', 8.50, NULL, NULL),
    ('f9ecb0cc-403f-442e-b2ce-1ed46dd033c0', 'QAM-023-01', 'Lavavajillas Compacto', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-023, item 1.', 'electrodomesticos', 329.00, NULL, NULL),
    ('e616be02-7557-4a44-9027-31f27ab8f7a8', 'QAM-023-02', 'Cuaderno Universitario Tapa Blanda', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-023, item 2.', 'libros_papeleria', 6.50, NULL, NULL),
    ('97b0f721-befc-49d2-b699-b9e208429e51', 'QAM-024-01', 'Batidora de Vaso 1.5L', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-024, item 1.', 'electrodomesticos', 42.00, NULL, NULL),
    ('be1ef29a-e4b8-4862-beb2-005a88ad7116', 'QAM-024-02', 'Pista de Coches Electrica', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-024, item 2.', 'juguetes', 35.00, NULL, NULL),
    ('78818a38-1bf8-40cf-8e53-a903eb832f7c', 'QAM-024-03', 'Perfume Miniatura 15ml', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-024, item 3.', 'cosmetica_perfumeria', 9.99, NULL, NULL),
    ('8cf34399-5fae-448f-b4dc-f46d592df79e', 'QAM-025-01', 'Zapatillas Deportivas Trail', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-025, item 1.', 'calzado', 68.00, NULL, NULL),
    ('f231ee5e-28c0-4cc8-9659-6e36703aead6', 'QAM-025-02', 'Teclado Mecanico Compacto', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-025, item 2.', 'electronica_informatica', 39.99, NULL, NULL),
    ('c9ec530b-be90-43ce-9ee7-c0bf089ba390', 'QAM-025-03', 'Dron Mini con Camara', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-025, item 3.', 'juguetes', 44.00, NULL, NULL),
    ('b92caba3-3fc9-4b2c-8db5-86fb253c6ca8', 'QAM-026-01', 'Sandalias de Playa', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-026, item 1.', 'calzado', 19.99, NULL, NULL),
    ('b3766ea4-4ad5-4f9c-b958-9d3186498232', 'QAM-026-02', 'Guantes de Ciclismo', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-026, item 2.', 'deportes_aire_libre', 12.99, NULL, NULL),
    ('157b1f93-841a-4936-bcf8-c853357336d7', 'QAM-027-01', 'Kayak Inflable 2 Plazas', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-027, item 1.', 'deportes_aire_libre', 389.00, NULL, NULL),
    ('426cb065-c547-4e08-8742-0911772f9abb', 'QAM-027-02', 'Colonia Infantil 200ml', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-027, item 2.', 'cosmetica_perfumeria', 18.50, NULL, NULL),
    ('11ec5ef3-8e06-4aef-bbf5-f4913b2f9a79', 'QAM-027-03', 'Chupetes Ortodoncicos Pack x2', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-027, item 3.', 'bebe_puericultura', 7.99, NULL, NULL),
    ('9eb051e1-3779-4c4d-bebc-9eafa6f0f86b', 'QAM-028-01', 'Funda Protectora para Portatil', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-028, item 1.', 'electronica_informatica', 15.99, NULL, NULL),
    ('fcfbd3da-4b18-4c97-84c3-6309d928a506', 'QAM-028-02', 'Manguera de Riego 20m', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-028, item 2.', 'jardineria_bricolaje', 22.00, NULL, NULL),
    ('936a8d21-9a8c-4fc3-b886-dcea3606e5aa', 'QAM-028-03', 'Locion Corporal 400ml', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-028, item 3.', 'drogueria_salud', 8.99, NULL, NULL),
    ('5f2b0d7b-d04a-4085-8880-1d5dc1810434', 'QAM-028-04', 'Miel Artesanal 500g', 'Articulo ficticio de QA (pedido mixto) para el caso QAM-028, item 4.', 'alimentacion', 6.50, NULL, NULL)
ON CONFLICT (sku) DO NOTHING;

-- -------------------------------------------------------------------------
-- 3) Pedidos de prueba, YA ENTREGADOS hace 'dias_entrega' dias (ver Excel)
-- -------------------------------------------------------------------------
INSERT INTO orders (id, customer_id, order_number, status, total_amount, shipping_address, ordered_at, delivered_at) VALUES
    ('e334796c-bacc-4cdf-b68d-a1859c57608a', '183046f4-5eeb-40b2-ac69-3f459997369a', 'ORD-QAM-0009', 'delivered', 101.00, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '18 days', NOW() - INTERVAL '15 days'),
    ('c04129c9-0318-47a1-acea-254317878e1c', '12428e0a-f16f-4c02-8686-2151bf770ef3', 'ORD-QAM-0010', 'delivered', 99.98, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '13 days', NOW() - INTERVAL '10 days'),
    ('1dd8ba1d-b069-4c45-b587-eaab77f56163', '36c764ca-f938-4996-93e7-46e48f8e6774', 'ORD-QAM-0011', 'delivered', 905.50, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '9 days', NOW() - INTERVAL '6 days'),
    ('9c7cd286-da5a-4352-a54a-3d62bcff1592', 'a9e2563d-5483-4362-adb4-30ba295ef963', 'ORD-QAM-0012', 'delivered', 60.99, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '11 days', NOW() - INTERVAL '8 days'),
    ('34079360-ed53-49e4-bd7f-98539dce86ab', '62885a71-417c-4443-a8d4-5198242b3f20', 'ORD-QAM-0013', 'delivered', 142.48, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '10 days', NOW() - INTERVAL '7 days'),
    ('80650785-d43e-4866-85f1-4a3bdf574a95', 'fa36cc4b-70f1-43e7-bf68-bce5f461a839', 'ORD-QAM-0014', 'delivered', 79.49, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '15 days', NOW() - INTERVAL '12 days'),
    ('95f50ee3-5c53-436b-a9b1-87cd1d487ddd', '3918c24b-dfa3-4c62-9b63-717b20ecfe01', 'ORD-QAM-0015', 'delivered', 223.99, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '14 days', NOW() - INTERVAL '11 days'),
    ('f37cfbe8-56ec-48fb-88ee-b2efb5cfd71e', '0d548a0b-862d-4372-b6cb-d8a5016f4f05', 'ORD-QAM-0016', 'delivered', 17.98, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '20 days', NOW() - INTERVAL '17 days'),
    ('67666e6e-c1ba-49eb-b245-2eb894b6d427', '2afd7a49-b6cb-472c-9766-2839c50435a1', 'ORD-QAM-0017', 'delivered', 315.90, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '11 days', NOW() - INTERVAL '8 days'),
    ('e7d9c4ab-f3a8-4faa-8a97-d8b98f5d1764', '4f3fbe9d-cc38-4ffb-af81-59fd34a91c97', 'ORD-QAM-0018', 'delivered', 24.98, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '6 days', NOW() - INTERVAL '3 days'),
    ('fe86ee39-c59e-484c-882c-a425f6b77018', 'f74ea822-1e9f-429d-a1a1-1c8bea6db8cc', 'ORD-QAM-0019', 'delivered', 173.00, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '9 days', NOW() - INTERVAL '6 days'),
    ('9a897a6c-3093-4b3e-939c-e4ab3fbd1b0b', 'ddbe2d65-221c-465f-b03e-c79057fe65dc', 'ORD-QAM-0020', 'delivered', 56.48, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '9 days', NOW() - INTERVAL '6 days'),
    ('604cf1b0-2e75-47eb-acfa-44753b5ef4d5', '86787910-ab43-4942-90fe-ef5d3fa23eda', 'ORD-QAM-0021', 'delivered', 107.46, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '7 days', NOW() - INTERVAL '4 days'),
    ('1f3840fc-1bbd-471e-9f5e-d902c6922ca1', '7d4e3725-613e-47d2-afdf-9a69c2e364ae', 'ORD-QAM-0022', 'delivered', 20.49, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '12 days', NOW() - INTERVAL '9 days'),
    ('0fa0c56b-5e2d-43a5-ae39-698c02929fcf', '29b6c5bc-7461-428c-b4c6-aea18689e8e3', 'ORD-QAM-0023', 'delivered', 335.50, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '27 days', NOW() - INTERVAL '24 days'),
    ('301a6e4f-ac7e-4d86-9ecf-3ba6f40ede0c', 'fff1989a-e422-4444-ba78-92ce91926848', 'ORD-QAM-0024', 'delivered', 86.99, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '17 days', NOW() - INTERVAL '14 days'),
    ('b1f43e14-a13b-450a-9021-7a23dede965c', '214c37ae-a5ca-4e71-bc66-2e2f3b8bbc83', 'ORD-QAM-0025', 'delivered', 151.99, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '8 days', NOW() - INTERVAL '5 days'),
    ('f44e1071-bcbe-4d5a-b934-8ad70e1690bd', 'fc18c1e2-e1b2-4598-8301-93d752212a89', 'ORD-QAM-0026', 'delivered', 32.98, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '10 days', NOW() - INTERVAL '7 days'),
    ('67cc03c6-3076-41f6-9c1b-c5051fe5f718', 'a8d1a344-8f62-45e9-b4b6-11ccc9a46508', 'ORD-QAM-0027', 'delivered', 415.49, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '13 days', NOW() - INTERVAL '10 days'),
    ('e16d2a4d-a281-4391-a148-0b161a739de5', 'a36cd009-97b0-44c1-80e7-8d33987162fd', 'ORD-QAM-0028', 'delivered', 53.48, '{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", "postal_code": "28001", "country": "ES"}'::jsonb, NOW() - INTERVAL '13 days', NOW() - INTERVAL '10 days')
ON CONFLICT (order_number) DO NOTHING;

-- -------------------------------------------------------------------------
-- 4) Lineas de pedido (varias por caso -- esto es lo que hace el pedido MIXTO)
-- -------------------------------------------------------------------------
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
    ('d268f199-6099-4979-a863-59d1d874f282', 'e334796c-bacc-4cdf-b68d-a1859c57608a', '364d03cd-4264-4965-b37d-494745278cf9', 1, 65.50, 65.50),
    ('0535ff38-35f6-4087-9423-049464c486f2', 'e334796c-bacc-4cdf-b68d-a1859c57608a', '26252715-391a-4d97-aa6b-6743f153eeda', 1, 35.50, 35.50),
    ('1afeb2fc-66ed-4794-984f-0ce9b77c3283', 'c04129c9-0318-47a1-acea-254317878e1c', '657c385c-8e06-411b-92f4-8294473ad13f', 1, 49.99, 49.99),
    ('b980741b-28ec-403e-8fd9-c5896fd2fad8', 'c04129c9-0318-47a1-acea-254317878e1c', '7f83b62d-508c-48ed-92a4-4033149f771a', 1, 49.99, 49.99),
    ('0b4decf5-1435-46ea-80c8-6be12ce1c1c4', '1dd8ba1d-b069-4c45-b587-eaab77f56163', '67ddc496-6160-4581-baf0-34e85de2ea04', 1, 899.00, 899.00),
    ('a84b27ea-9be0-4f7d-b589-b91d30731d8d', '1dd8ba1d-b069-4c45-b587-eaab77f56163', '1628212f-bc75-4d09-9ddb-244359adcb34', 1, 6.50, 6.50),
    ('8961b444-af3f-4963-b6b9-dff6ac5d2242', '9c7cd286-da5a-4352-a54a-3d62bcff1592', '453c1bb3-5f62-4934-b5f5-c439af88c78a', 1, 15.99, 15.99),
    ('9107ec9d-f945-4a9f-a499-229287ebc619', '9c7cd286-da5a-4352-a54a-3d62bcff1592', '8f9f3048-906a-498e-8a8a-e5212397f117', 1, 45.00, 45.00),
    ('a9379d6b-ffbb-4dea-990c-ab2ab7ebfd07', '34079360-ed53-49e4-bd7f-98539dce86ab', 'd98b3da4-7eac-4170-8e73-e4654bd8c0e5', 1, 79.99, 79.99),
    ('97c11046-3e86-40a2-bcf2-e9225e0d8c91', '34079360-ed53-49e4-bd7f-98539dce86ab', '49b8b96e-2d8c-422e-ab48-03e9e28b7bd9', 1, 34.50, 34.50),
    ('6b072b15-2525-4c8a-92d1-13e76eaa6617', '34079360-ed53-49e4-bd7f-98539dce86ab', 'a75e8fe2-b328-400d-98f5-af13e9cdf29d', 1, 27.99, 27.99),
    ('2eb60b11-25ec-4120-9026-2b7d737bfb33', '80650785-d43e-4866-85f1-4a3bdf574a95', '3e859976-7e05-4897-ab36-ae165461569f', 1, 38.00, 38.00),
    ('76999572-5e28-413e-b257-975bbf27d6dc', '80650785-d43e-4866-85f1-4a3bdf574a95', '04ac0e26-6184-496b-af1e-2970021edffe', 1, 29.99, 29.99),
    ('c887e876-702b-485d-aa36-072e9900836c', '80650785-d43e-4866-85f1-4a3bdf574a95', 'e31b03d2-7506-4dea-a4fc-b0817609dfae', 1, 11.50, 11.50),
    ('c9e3d87a-17de-4718-8a90-329ea6944236', '95f50ee3-5c53-436b-a9b1-87cd1d487ddd', '40466527-6783-4dce-8508-6d3287d419c4', 1, 189.00, 189.00),
    ('8743e98c-f815-45ef-96bd-d12c87838363', '95f50ee3-5c53-436b-a9b1-87cd1d487ddd', 'c370fae2-83ac-4e62-8f88-0367afd4968d', 1, 34.99, 34.99),
    ('d451cae7-66e7-471b-b540-2970f7488e51', 'f37cfbe8-56ec-48fb-88ee-b2efb5cfd71e', '8dc7b594-807d-4865-8765-cd81d84f2872', 1, 7.99, 7.99),
    ('e979318c-21c8-4e05-a57e-3a70068dd1af', 'f37cfbe8-56ec-48fb-88ee-b2efb5cfd71e', 'f9eaecdf-8835-4d03-97b7-5b809b29a1b3', 1, 9.99, 9.99),
    ('f6b5584d-95f2-40a9-a65d-3ba4b5f316d7', '67666e6e-c1ba-49eb-b245-2eb894b6d427', '5c5daee9-cdb8-4a95-95d2-a00fe104201a', 1, 249.00, 249.00),
    ('496a01b4-a49f-4e58-a891-f38355edc095', '67666e6e-c1ba-49eb-b245-2eb894b6d427', '7f74fc61-05e8-40f7-b8db-b00476a05696', 1, 15.00, 15.00),
    ('213d3b28-5ff7-47b3-8ca8-c3600a7dd7c5', '67666e6e-c1ba-49eb-b245-2eb894b6d427', '198c4e95-e9a2-4146-993b-034287743f5e', 1, 42.00, 42.00),
    ('5081a1fb-8696-4a97-8196-8805256dddc3', '67666e6e-c1ba-49eb-b245-2eb894b6d427', '2e1f732b-40b8-4f6c-9849-61a1ee43a984', 1, 9.90, 9.90),
    ('8782d2c7-53ab-4051-bb16-983966a75f6f', 'e7d9c4ab-f3a8-4faa-8a97-d8b98f5d1764', '75272170-7661-4537-a519-bc4ba6bafb9a', 1, 14.99, 14.99),
    ('892f8732-9611-4d9d-855e-1529404b99a2', 'e7d9c4ab-f3a8-4faa-8a97-d8b98f5d1764', '4f02b224-459b-4b00-8ff2-647c7c559ebd', 1, 9.99, 9.99),
    ('f3e68ae9-b6c0-42fd-be2d-4c9298778682', 'fe86ee39-c59e-484c-882c-a425f6b77018', '4820aa93-e171-4464-b9f1-2489d6adf014', 1, 119.00, 119.00),
    ('6a32c652-03d0-4ad9-9986-5b9f9ad0abad', 'fe86ee39-c59e-484c-882c-a425f6b77018', 'e328ff33-7d50-4434-9278-5d275e60bcf6', 1, 54.00, 54.00),
    ('46f33414-8fde-4a1b-bcf2-bbe74cc96196', '9a897a6c-3093-4b3e-939c-e4ab3fbd1b0b', 'cdd1a2f3-c5e4-4ecc-b181-46821202a768', 1, 24.99, 24.99),
    ('3b3d7a4a-777d-4c7c-9aea-afd900d93779', '9a897a6c-3093-4b3e-939c-e4ab3fbd1b0b', '4e2f6ad6-a213-4709-88eb-4beed0db1a23', 1, 13.50, 13.50),
    ('99d934eb-0bef-4099-85bb-dacbf553c588', '9a897a6c-3093-4b3e-939c-e4ab3fbd1b0b', '8717adf7-243f-48b8-95d8-e9a90f6e2730', 1, 17.99, 17.99),
    ('8851b799-a342-4ec5-bfdb-64fb2c44439c', '604cf1b0-2e75-47eb-acfa-44753b5ef4d5', '8365d664-9812-4d6d-9c34-6d493bf776af', 1, 24.99, 24.99),
    ('0fd54755-f6b3-4029-acac-4162f294024f', '604cf1b0-2e75-47eb-acfa-44753b5ef4d5', '3d83ebfd-a5d4-4058-bfc1-9832752ccd4f', 1, 19.99, 19.99),
    ('1c8fc0af-5d85-4070-9514-0bf5ef25543d', '604cf1b0-2e75-47eb-acfa-44753b5ef4d5', '7e624e44-ae99-4410-92f0-6a03f76ebd76', 1, 22.50, 22.50),
    ('43245755-589e-4f7d-bdb9-80595e973b79', '604cf1b0-2e75-47eb-acfa-44753b5ef4d5', '3682e13f-109e-4df4-8711-23c4161bb652', 1, 14.99, 14.99),
    ('a6eb816b-d705-4732-a072-0458685f6780', '604cf1b0-2e75-47eb-acfa-44753b5ef4d5', '14f922fa-a6c8-407c-9afe-e1b25930cdcc', 1, 24.99, 24.99),
    ('87c79da2-d562-4e76-867e-e422a83f471b', '1f3840fc-1bbd-471e-9f5e-d902c6922ca1', 'a15d4f52-61ba-4789-bff8-d3c658a8cb24', 1, 11.99, 11.99),
    ('6253bfeb-d8bf-4222-a142-2823620d6944', '1f3840fc-1bbd-471e-9f5e-d902c6922ca1', '3d4130a7-8319-4796-b44d-00c4aca3e282', 1, 8.50, 8.50),
    ('82c4c230-7518-4963-9259-ba4eb2714366', '0fa0c56b-5e2d-43a5-ae39-698c02929fcf', 'f9ecb0cc-403f-442e-b2ce-1ed46dd033c0', 1, 329.00, 329.00),
    ('1d6932ed-d178-4fad-bb5a-4194dc0088cd', '0fa0c56b-5e2d-43a5-ae39-698c02929fcf', 'e616be02-7557-4a44-9027-31f27ab8f7a8', 1, 6.50, 6.50),
    ('3623c65e-0b8b-460e-b583-1cdc8b4affcb', '301a6e4f-ac7e-4d86-9ecf-3ba6f40ede0c', '97b0f721-befc-49d2-b699-b9e208429e51', 1, 42.00, 42.00),
    ('d589fd7d-14c1-4fac-be22-fc1dd3db3203', '301a6e4f-ac7e-4d86-9ecf-3ba6f40ede0c', 'be1ef29a-e4b8-4862-beb2-005a88ad7116', 1, 35.00, 35.00),
    ('913ed529-1563-4bf5-9192-5eb74a05eba3', '301a6e4f-ac7e-4d86-9ecf-3ba6f40ede0c', '78818a38-1bf8-40cf-8e53-a903eb832f7c', 1, 9.99, 9.99),
    ('cbb486d5-6387-4f3b-949c-83668c5be9f9', 'b1f43e14-a13b-450a-9021-7a23dede965c', '8cf34399-5fae-448f-b4dc-f46d592df79e', 1, 68.00, 68.00),
    ('14783e8c-a938-43b1-b69b-3aa8b2f15366', 'b1f43e14-a13b-450a-9021-7a23dede965c', 'f231ee5e-28c0-4cc8-9659-6e36703aead6', 1, 39.99, 39.99),
    ('70b88a78-6b85-4ee8-b2f1-1f048928527b', 'b1f43e14-a13b-450a-9021-7a23dede965c', 'c9ec530b-be90-43ce-9ee7-c0bf089ba390', 1, 44.00, 44.00),
    ('f6c68f12-85ac-46e5-b872-26bcfc9ade81', 'f44e1071-bcbe-4d5a-b934-8ad70e1690bd', 'b92caba3-3fc9-4b2c-8db5-86fb253c6ca8', 1, 19.99, 19.99),
    ('484e6c62-558d-4691-8977-7a4d0967637f', 'f44e1071-bcbe-4d5a-b934-8ad70e1690bd', 'b3766ea4-4ad5-4f9c-b958-9d3186498232', 1, 12.99, 12.99),
    ('9dafe9d4-09dc-4048-b664-6cfdbed4248e', '67cc03c6-3076-41f6-9c1b-c5051fe5f718', '157b1f93-841a-4936-bcf8-c853357336d7', 1, 389.00, 389.00),
    ('d613a7e6-df07-4f81-99a8-c894ae4de333', '67cc03c6-3076-41f6-9c1b-c5051fe5f718', '426cb065-c547-4e08-8742-0911772f9abb', 1, 18.50, 18.50),
    ('06559ec9-f419-4b85-8f52-65a118411b87', '67cc03c6-3076-41f6-9c1b-c5051fe5f718', '11ec5ef3-8e06-4aef-bbf5-f4913b2f9a79', 1, 7.99, 7.99),
    ('485cabba-807f-4988-97f9-23a618519c82', 'e16d2a4d-a281-4391-a148-0b161a739de5', '9eb051e1-3779-4c4d-bebc-9eafa6f0f86b', 1, 15.99, 15.99),
    ('0798f45b-9aa2-44b8-9451-c9ab23cc3261', 'e16d2a4d-a281-4391-a148-0b161a739de5', 'fcfbd3da-4b18-4c97-84c3-6309d928a506', 1, 22.00, 22.00),
    ('f9b33973-6963-4f50-8112-2a803c9ca426', 'e16d2a4d-a281-4391-a148-0b161a739de5', '936a8d21-9a8c-4fc3-b886-dcea3606e5aa', 1, 8.99, 8.99),
    ('0efdb692-c0f9-40eb-b719-c46ca59f1fd0', 'e16d2a4d-a281-4391-a148-0b161a739de5', '5f2b0d7b-d04a-4085-8880-1d5dc1810434', 1, 6.50, 6.50)
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
