"""
Genera el kit de pruebas QA para PEDIDOS MIXTOS (varios productos de
categorias distintas, con elegibilidad de devolucion parcial).

Complementa a dataset/qa_manual_testing_cases.xlsx / supabase/qa_manual_testing_seed.sql
(que solo cubren pedidos de UN articulo). Produce dos artefactos:
  - dataset/qa_manual_testing_casos_pedidos_mixtos.xlsx
  - supabase/qa_manual_testing_seed_pedidos_mixtos.sql

Requiere las categorias/policies ya insertadas por
supabase/qa_manual_testing_seed.sql (reutiliza las mismas 13 categorias,
no vuelve a insertar return_policies).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
)  # tests/qa/scripts/ → repo root

# ── UUIDs fijos (generados una vez, no se regeneran en cada ejecucion) ─────

IDS = {
    "001": {
        "customer_id": "0cf624c3-e5ba-4ac3-ba09-d551e4f59609",
        "order_id": "5293d74e-10e3-4e71-b8c0-9452f410f756",
        "products": [
            "d8a3a304-8742-4a18-8522-56351baf8ce8",
            "3dfba202-f382-4111-a9b1-a7fd79dc50c2",
        ],
        "order_items": [
            "198485e9-ed82-44b8-a253-c547fa56d13e",
            "4e5035cf-0d6d-4152-bbea-3552775efbd9",
        ],
    },
    "002": {
        "customer_id": "150f572e-27e0-4364-8ccd-699d5945c223",
        "order_id": "b1563596-a9d7-464b-805f-d14853a8c9ff",
        "products": [
            "97179628-efff-45a7-bb50-3b2fb7889774",
            "7e9ca431-c188-4fb5-bf52-a1439af309d6",
        ],
        "order_items": [
            "a5367ce3-6a87-4b85-84ab-f047b8c7751d",
            "ae74b5d7-aadc-48ab-bd9b-45d18658a330",
        ],
    },
    "003": {
        "customer_id": "38f8f399-84e5-4215-ad65-b52ae1364f73",
        "order_id": "753d7563-8d68-4596-b67e-6abd939314ef",
        "products": [
            "a0820cf8-7de4-4973-b0bf-e3f3f53f2319",
            "32990b3e-f8e6-4831-9612-fe8d4eb214fc",
            "73be6009-7c39-4e59-8759-9b09e50078c9",
        ],
        "order_items": [
            "fa474206-98f8-4e98-8f53-1020ebe25879",
            "ebc78ff1-fb7e-4973-ba52-6e289745e208",
            "93c5962b-beff-4c79-9415-c661d9298855",
        ],
    },
    "004": {
        "customer_id": "0a167878-fa00-47c6-b2b9-68638c6589a9",
        "order_id": "3b648f4e-42ef-47c9-be53-8f9ceb8ed87c",
        "products": [
            "57aba350-ffa3-4fce-b090-e089ef65419d",
            "b4c1f150-310d-4d1b-88e7-c73c18bc667f",
        ],
        "order_items": [
            "2b2d136a-dc6d-427d-90ba-777c90d817d0",
            "263410db-d5f1-4803-bf24-e605580ec27c",
        ],
    },
    "005": {
        "customer_id": "0c14d593-a08b-4a34-8f16-6e1dce77e11b",
        "order_id": "0c4855ae-d242-47b8-955c-a8d808b47ae7",
        "products": [
            "0e25ba43-b97e-47ad-856d-eee7ea159692",
            "6c4df112-afd1-45fd-95ab-dd57482bebe0",
        ],
        "order_items": [
            "d441b6fa-ce08-416c-9861-dcd5676cf4de",
            "d724a845-37a5-49ed-9fd0-9d7368aea97c",
        ],
    },
    "006": {
        "customer_id": "2d35af0b-9a3a-46d8-99ab-8c67042b9b26",
        "order_id": "9b92bf9e-10be-4ccf-825d-44c2906d647b",
        "products": [
            "02d4757f-3318-47a7-9fd3-f7964d982198",
            "869b41de-dc97-47b9-b06f-f558dbeb6453",
        ],
        "order_items": [
            "60227fae-a954-4344-815c-147f0c3dd4b1",
            "487c8e34-ba95-47ee-b588-790d3cfb87f8",
        ],
    },
    "007": {
        "customer_id": "9384c33a-53ee-4c8c-8a82-271248406a1a",
        "order_id": "723e1cbb-7897-49e8-a375-71dd24341303",
        "products": [
            "dac2f717-e61c-452e-81ed-f47db79656ec",
            "9de94575-b24c-4753-bcf9-6c481c7ed972",
        ],
        "order_items": [
            "5a42f71b-6c5c-41ba-96c0-4b207a264e96",
            "6cc8e69f-49c4-4629-a205-acd33787a048",
        ],
    },
    "009": {
        "customer_id": "183046f4-5eeb-40b2-ac69-3f459997369a",
        "order_id": "e334796c-bacc-4cdf-b68d-a1859c57608a",
        "products": [
            "364d03cd-4264-4965-b37d-494745278cf9",
            "26252715-391a-4d97-aa6b-6743f153eeda",
        ],
        "order_items": [
            "d268f199-6099-4979-a863-59d1d874f282",
            "0535ff38-35f6-4087-9423-049464c486f2",
        ],
    },
    "010": {
        "customer_id": "12428e0a-f16f-4c02-8686-2151bf770ef3",
        "order_id": "c04129c9-0318-47a1-acea-254317878e1c",
        "products": [
            "657c385c-8e06-411b-92f4-8294473ad13f",
            "7f83b62d-508c-48ed-92a4-4033149f771a",
        ],
        "order_items": [
            "1afeb2fc-66ed-4794-984f-0ce9b77c3283",
            "b980741b-28ec-403e-8fd9-c5896fd2fad8",
        ],
    },
    "011": {
        "customer_id": "36c764ca-f938-4996-93e7-46e48f8e6774",
        "order_id": "1dd8ba1d-b069-4c45-b587-eaab77f56163",
        "products": [
            "67ddc496-6160-4581-baf0-34e85de2ea04",
            "1628212f-bc75-4d09-9ddb-244359adcb34",
        ],
        "order_items": [
            "0b4decf5-1435-46ea-80c8-6be12ce1c1c4",
            "a84b27ea-9be0-4f7d-b589-b91d30731d8d",
        ],
    },
    "012": {
        "customer_id": "a9e2563d-5483-4362-adb4-30ba295ef963",
        "order_id": "9c7cd286-da5a-4352-a54a-3d62bcff1592",
        "products": [
            "453c1bb3-5f62-4934-b5f5-c439af88c78a",
            "8f9f3048-906a-498e-8a8a-e5212397f117",
        ],
        "order_items": [
            "8961b444-af3f-4963-b6b9-dff6ac5d2242",
            "9107ec9d-f945-4a9f-a499-229287ebc619",
        ],
    },
    "013": {
        "customer_id": "62885a71-417c-4443-a8d4-5198242b3f20",
        "order_id": "34079360-ed53-49e4-bd7f-98539dce86ab",
        "products": [
            "d98b3da4-7eac-4170-8e73-e4654bd8c0e5",
            "49b8b96e-2d8c-422e-ab48-03e9e28b7bd9",
            "a75e8fe2-b328-400d-98f5-af13e9cdf29d",
        ],
        "order_items": [
            "a9379d6b-ffbb-4dea-990c-ab2ab7ebfd07",
            "97c11046-3e86-40a2-bcf2-e9225e0d8c91",
            "6b072b15-2525-4c8a-92d1-13e76eaa6617",
        ],
    },
    "014": {
        "customer_id": "fa36cc4b-70f1-43e7-bf68-bce5f461a839",
        "order_id": "80650785-d43e-4866-85f1-4a3bdf574a95",
        "products": [
            "3e859976-7e05-4897-ab36-ae165461569f",
            "04ac0e26-6184-496b-af1e-2970021edffe",
            "e31b03d2-7506-4dea-a4fc-b0817609dfae",
        ],
        "order_items": [
            "2eb60b11-25ec-4120-9026-2b7d737bfb33",
            "76999572-5e28-413e-b257-975bbf27d6dc",
            "c887e876-702b-485d-aa36-072e9900836c",
        ],
    },
    "015": {
        "customer_id": "3918c24b-dfa3-4c62-9b63-717b20ecfe01",
        "order_id": "95f50ee3-5c53-436b-a9b1-87cd1d487ddd",
        "products": [
            "40466527-6783-4dce-8508-6d3287d419c4",
            "c370fae2-83ac-4e62-8f88-0367afd4968d",
        ],
        "order_items": [
            "c9e3d87a-17de-4718-8a90-329ea6944236",
            "8743e98c-f815-45ef-96bd-d12c87838363",
        ],
    },
    "016": {
        "customer_id": "0d548a0b-862d-4372-b6cb-d8a5016f4f05",
        "order_id": "f37cfbe8-56ec-48fb-88ee-b2efb5cfd71e",
        "products": [
            "8dc7b594-807f-4865-8765-cd81d84f2872",
            "f9eaecdf-8835-4d03-97b7-5b809b29a1b3",
        ],
        "order_items": [
            "d451cae7-66e7-471b-b540-2970f7488e51",
            "e979318c-21c8-4e05-a57e-3a70068dd1af",
        ],
    },
    "017": {
        "customer_id": "2afd7a49-b6cb-472c-9766-2839c50435a1",
        "order_id": "67666e6e-c1ba-49eb-b245-2eb894b6d427",
        "products": [
            "5c5daee9-cdb8-4a95-95d2-a00fe104201a",
            "7f74fc61-05e8-40f7-b8db-b00476a05696",
            "198c4e95-e9a2-4146-993b-034287743f5e",
            "2e1f732b-40b8-4f6c-9849-61a1ee43a984",
        ],
        "order_items": [
            "f6b5584d-95f2-40a9-a65d-3ba4b5f316d7",
            "496a01b4-a49f-4e58-a891-f38355edc095",
            "213d3b28-5ff7-47b3-8ca8-c3600a7dd7c5",
            "5081a1fb-8696-4a97-8196-8805256dddc3",
        ],
    },
    "018": {
        "customer_id": "4f3fbe9d-cc38-4ffb-af81-59fd34a91c97",
        "order_id": "e7d9c4ab-f3a8-4faa-8a97-d8b98f5d1764",
        "products": [
            "75272170-7661-4537-a519-bc4ba6bafb9a",
            "4f02b224-459b-4b00-8ff2-647c7c559ebd",
        ],
        "order_items": [
            "8782d2c7-53ab-4051-bb16-983966a75f6f",
            "892f8732-9611-4d9d-855e-1529404b99a2",
        ],
    },
    "019": {
        "customer_id": "f74ea822-1e9f-429d-a1a1-1c8bea6db8cc",
        "order_id": "fe86ee39-c59e-484c-882c-a425f6b77018",
        "products": [
            "4820aa93-e171-4464-b9f1-2489d6adf014",
            "e328ff33-7d50-4434-9278-5d275e60bcf6",
        ],
        "order_items": [
            "f3e68ae9-b6c0-42fd-be2d-4c9298778682",
            "6a32c652-03d0-4ad9-9986-5b9f9ad0abad",
        ],
    },
    "020": {
        "customer_id": "ddbe2d65-221c-465f-b03e-c79057fe65dc",
        "order_id": "9a897a6c-3093-4b3e-939c-e4ab3fbd1b0b",
        "products": [
            "cdd1a2f3-c5e4-4ecc-b181-46821202a768",
            "4e2f6ad6-a213-4709-88eb-4beed0db1a23",
            "8717adf7-243f-48b8-95d8-e9a90f6e2730",
        ],
        "order_items": [
            "46f33414-8fde-4a1b-bcf2-bbe74cc96196",
            "3b3d7a4a-777d-4c7c-9aea-afd900d93779",
            "99d934eb-0bef-4099-85bb-dacbf553c588",
        ],
    },
    "021": {
        "customer_id": "86787910-ab43-4942-90fe-ef5d3fa23eda",
        "order_id": "604cf1b0-2e75-47eb-acfa-44753b5ef4d5",
        "products": [
            "8365d664-9812-4d6d-9c34-6d493bf776af",
            "3d83ebfd-a5d4-4058-bfc1-9832752ccd4f",
            "7e624e44-ae99-4410-92f0-6a03f76ebd76",
            "3682e13f-109e-4df4-8711-23c4161bb652",
            "14f922fa-a6c8-407c-9afe-e1b25930cdcc",
        ],
        "order_items": [
            "8851b799-a342-4ec5-bfdb-64fb2c44439c",
            "0fd54755-f6b3-4029-acac-4162f294024f",
            "1c8fc0af-5d85-4070-9514-0bf5ef25543d",
            "43245755-589e-4f7d-bdb9-80595e973b79",
            "a6eb816b-d705-4732-a072-0458685f6780",
        ],
    },
    "022": {
        "customer_id": "7d4e3725-613e-47d2-afdf-9a69c2e364ae",
        "order_id": "1f3840fc-1bbd-471e-9f5e-d902c6922ca1",
        "products": [
            "a15d4f52-61ba-4789-bff8-d3c658a8cb24",
            "3d4130a7-8319-4796-b44d-00c4aca3e282",
        ],
        "order_items": [
            "87c79da2-d562-4e76-867e-e422a83f471b",
            "6253bfeb-d8bf-4222-a142-2823620d6944",
        ],
    },
    "023": {
        "customer_id": "29b6c5bc-7461-428c-b4c6-aea18689e8e3",
        "order_id": "0fa0c56b-5e2d-43a5-ae39-698c02929fcf",
        "products": [
            "f9ecb0cc-403f-442e-b2ce-1ed46dd033c0",
            "e616be02-7557-4a44-9027-31f27ab8f7a8",
        ],
        "order_items": [
            "82c4c230-7518-4963-9259-ba4eb2714366",
            "1d6932ed-d178-4fad-bb5a-4194dc0088cd",
        ],
    },
    "024": {
        "customer_id": "fff1989a-e422-4444-ba78-92ce91926848",
        "order_id": "301a6e4f-ac7e-4d86-9ecf-3ba6f40ede0c",
        "products": [
            "97b0f721-befc-49d2-b699-b9e208429e51",
            "be1ef29a-e4b8-4862-beb2-005a88ad7116",
            "78818a38-1bf8-40cf-8e53-a903eb832f7c",
        ],
        "order_items": [
            "3623c65e-0b8b-460e-b583-1cdc8b4affcb",
            "d589fd7d-14c1-4fac-be22-fc1dd3db3203",
            "913ed529-1563-4bf5-9192-5eb74a05eba3",
        ],
    },
    "025": {
        "customer_id": "214c37ae-a5ca-4e71-bc66-2e2f3b8bbc83",
        "order_id": "b1f43e14-a13b-450a-9021-7a23dede965c",
        "products": [
            "8cf34399-5fae-448f-b4dc-f46d592df79e",
            "f231ee5e-28c0-4cc8-9659-6e36703aead6",
            "c9ec530b-be90-43ce-9ee7-c0bf089ba390",
        ],
        "order_items": [
            "cbb486d5-6387-4f3b-949c-83668c5be9f9",
            "14783e8c-a938-43b1-b69b-3aa8b2f15366",
            "70b88a78-6b85-4ee8-b2f1-1f048928527b",
        ],
    },
    "026": {
        "customer_id": "fc18c1e2-e1b2-4598-8301-93d752212a89",
        "order_id": "f44e1071-bcbe-4d5a-b934-8ad70e1690bd",
        "products": [
            "b92caba3-3fc9-4b2c-8db5-86fb253c6ca8",
            "b3766ea4-4ad5-4f9c-b958-9d3186498232",
        ],
        "order_items": [
            "f6c68f12-85ac-46e5-b872-26bcfc9ade81",
            "484e6c62-558d-4691-8977-7a4d0967637f",
        ],
    },
    "027": {
        "customer_id": "a8d1a344-8f62-45e9-b4b6-11ccc9a46508",
        "order_id": "67cc03c6-3076-41f6-9c1b-c5051fe5f718",
        "products": [
            "157b1f93-841a-4936-bcf8-c853357336d7",
            "426cb065-c547-4e08-8742-0911772f9abb",
            "11ec5ef3-8e06-4aef-bbf5-f4913b2f9a79",
        ],
        "order_items": [
            "9dafe9d4-09dc-4048-b664-6cfdbed4248e",
            "d613a7e6-df07-4f81-99a8-c894ae4de333",
            "06559ec9-f419-4b85-8f52-65a118411b87",
        ],
    },
    "028": {
        "customer_id": "a36cd009-97b0-44c1-80e7-8d33987162fd",
        "order_id": "e16d2a4d-a281-4391-a148-0b161a739de5",
        "products": [
            "9eb051e1-3779-4c4d-bebc-9eafa6f0f86b",
            "fcfbd3da-4b18-4c97-84c3-6309d928a506",
            "936a8d21-9a8c-4fc3-b886-dcea3606e5aa",
            "5f2b0d7b-d04a-4085-8880-1d5dc1810434",
        ],
        "order_items": [
            "485cabba-807f-4988-97f9-23a618519c82",
            "0798f45b-9aa2-44b8-9451-c9ab23cc3261",
            "f9b33973-6963-4f50-8112-2a803c9ca426",
            "0efdb692-c0f9-40eb-b719-c46ca59f1fd0",
        ],
    },
}

# ── Definicion de los 8 casos ────────────────────────────────────────────
# Cada item: (category, name, motivo, plazo_max_dias, precio, valido, justificacion)

CASES = [
    dict(
        num="001",
        order_number="ORD-QAM-0001",
        dias_entrega=8,
        resultado="🟡 PARCIAL",
        resultado_txt="parcialmente aprobado",
        items=[
            (
                "electronica_informatica",
                "Auriculares Bluetooth Pro",
                "defective",
                30,
                39.99,
                True,
                "Defectuoso dentro de plazo (8/30 dias)",
            ),
            (
                "cosmetica_perfumeria",
                "Perfume Eau de Parfum 50ml",
                "changed_mind",
                21,
                29.99,
                False,
                "Exclusion legal de higiene (Art. 103 TRLGDCU): precinto retirado por cambio de opinion",
            ),
        ],
        criterios="Elegibilidad por articulo en pedido mixto: electronica (defectuoso, dentro de plazo) "
        "valida + cosmetica (cambio de opinion, precinto retirado) invalida por exclusion legal "
        "de higiene. El resultado NO debe colapsar a un unico booleano para todo el pedido.",
    ),
    dict(
        num="002",
        order_number="ORD-QAM-0002",
        dias_entrega=12,
        resultado="🔄 HITL",
        resultado_txt="HITL parcial (1 aprobado tras revision + 1 rechazado)",
        items=[
            (
                "electrodomesticos",
                "Microondas Digital 20L",
                "defective",
                30,
                149.99,
                True,
                "Defectuoso dentro de plazo (12/30 dias)",
            ),
            (
                "drogueria_salud",
                "Champu Anticaspa 400ml",
                "changed_mind",
                21,
                12.99,
                False,
                "Exclusion legal de higiene: producto usado, cambio de opinion",
            ),
        ],
        criterios="El importe elegible (solo el microondas, 149.99€) supera el umbral HITL de 100€ aunque "
        "el pedido tenga un segundo articulo rechazado. Verifica que el HITL se calcule sobre el "
        "reembolso de los articulos ELEGIBLES, no sobre el total del pedido, y que el champu no "
        "se incluya en la etiqueta/reembolso aunque el admin apruebe.",
    ),
    dict(
        num="003",
        order_number="ORD-QAM-0003",
        dias_entrega=20,
        resultado="🟡 PARCIAL",
        resultado_txt="parcialmente aprobado (2 de 3)",
        items=[
            (
                "juguetes",
                "Puzzle 1000 Piezas Paisaje",
                "defective",
                30,
                24.99,
                True,
                "Defectuoso dentro de plazo (20/30 dias)",
            ),
            (
                "libros_papeleria",
                "Agenda 2026 Tapa Dura",
                "defective",
                21,
                15.99,
                True,
                "Defectuosa dentro de plazo, en el limite (20/21 dias)",
            ),
            (
                "alimentacion",
                "Lote de Conservas Gourmet",
                "changed_mind",
                14,
                18.50,
                False,
                "Fuera de plazo (20 dias > 14 maximo de la categoria)",
            ),
        ],
        criterios="3 articulos de 3 categorias distintas en la misma solicitud: 2 elegibles (cada una con "
        "su propio plazo maximo, uno de ellos justo en el limite) + 1 no elegible por plazo. "
        "Verifica que el reembolso agregado sea la SUMA de los 2 elegibles (40.98€), no el total "
        "del pedido (59.48€), y que se hagan 3 busquedas RAG (una por categoria).",
    ),
    dict(
        num="004",
        order_number="ORD-QAM-0004",
        dias_entrega=18,
        resultado="❌ INVÁLIDO",
        resultado_txt="rechazo total (0 de 2 elegibles)",
        items=[
            (
                "cosmetica_perfumeria",
                "Crema Facial Antiedad",
                "changed_mind",
                21,
                22.99,
                False,
                "Exclusion legal de higiene: producto usado, cambio de opinion",
            ),
            (
                "alimentacion",
                "Aceite de Oliva Virgen Extra",
                "changed_mind",
                14,
                9.99,
                False,
                "Fuera de plazo (18 dias > 14 maximo de la categoria)",
            ),
        ],
        criterios="Los 2 articulos son NO elegibles pero por motivos distintos (higiene vs plazo). Verifica "
        "que el mensaje de rechazo explique AMBOS motivos por separado (no un motivo generico "
        "unico), y que el pedido complete se enrute a 'reject' (ningun articulo elegible).",
    ),
    dict(
        num="005",
        order_number="ORD-QAM-0005",
        dias_entrega=10,
        resultado="🟡 PARCIAL",
        resultado_txt="parcialmente aprobado (misma categoria)",
        items=[
            (
                "calzado",
                "Zapatillas Running Pro",
                "wrong_size",
                30,
                59.99,
                True,
                "Talla equivocada, sin abrir, dentro de plazo (10/30 dias)",
            ),
            (
                "calzado",
                "Botas de Senderismo",
                "changed_mind",
                30,
                89.99,
                False,
                "Estado no admitido: uso evidente tras varias semanas de trekking (no es defecto de fabrica "
                "ni error de talla)",
            ),
        ],
        criterios="Los 2 articulos son de la MISMA categoria (calzado) y llegaron en el MISMO pedido (misma "
        "fecha de entrega, mismo plazo maximo): la diferencia de elegibilidad viene del ESTADO del "
        "articulo, no del plazo ni de la categoria. Verifica que la busqueda RAG se deduplique a "
        "UNA sola llamada (misma categoria) pero el LLM siga evaluando cada order_item_id por "
        "separado dentro de ese unico contexto de politica.",
    ),
    dict(
        num="006",
        order_number="ORD-QAM-0006",
        dias_entrega=4,
        resultado="✅ VÁLIDO",
        resultado_txt="aprobado (2 de 2, sin HITL)",
        items=[
            (
                "juguetes",
                "Muñeco Articulado Superheroe",
                "defective",
                30,
                19.99,
                True,
                "Defectuoso dentro de plazo (4/30 dias)",
            ),
            (
                "mascotas",
                "Correa para Perro Ajustable",
                "wrong_item",
                21,
                14.99,
                True,
                "Articulo equivocado, dentro de plazo (4/21 dias)",
            ),
        ],
        criterios="REGRESION: pedido mixto donde AMBOS articulos son elegibles. Confirma que el fix de "
        "elegibilidad por articulo no rompe el camino feliz (antes del fix ya funcionaba porque "
        "la unica categoria consultada por RAG resultaba ser, por azar, la correcta).",
    ),
    dict(
        num="007",
        order_number="ORD-QAM-0007",
        dias_entrega=9,
        resultado="🔄 HITL",
        resultado_txt="HITL, ambos aprobados tras revision",
        items=[
            (
                "electrodomesticos",
                "Aspiradora sin Cable",
                "defective",
                30,
                179.99,
                True,
                "Defectuoso dentro de plazo (9/30 dias)",
            ),
            (
                "deportes_aire_libre",
                "Bicicleta Estatica Plegable",
                "defective",
                30,
                259.99,
                True,
                "Defectuoso dentro de plazo (9/30 dias)",
            ),
        ],
        criterios="REGRESION del bug reportado por Tamara en QA-002 (PR #14): el mensaje de HITL no hacia "
        "referencia al articulo que se estaba devolviendo. Aqui hay DOS articulos elegibles que "
        "suman >100€ (439.98€): el mensaje de HITL y la resolucion final deben nombrar los DOS "
        "articulos, no solo uno generico.",
    ),
    # ── Casos 009-028: bateria ampliada de HITL en pedidos mixtos (10 con ────
    #    HITL, 10 sin HITL) para cubrir el umbral de 100€ desde mas angulos:
    #    limite exacto, un solo articulo caro, agregacion de 3-5 articulos,
    #    misma categoria, e higiene/plazo/estado como motivo de rechazo. ────
    dict(
        num="009",
        order_number="ORD-QAM-0009",
        dias_entrega=15,
        resultado="🔄 HITL",
        resultado_txt="HITL, ambos elegibles (justo por encima del umbral, +1€)",
        items=[
            (
                "jardineria_bricolaje",
                "Cortacesped Manual de Precision",
                "defective",
                30,
                65.50,
                True,
                "Defectuoso dentro de plazo (15/30 dias)",
            ),
            (
                "bebe_puericultura",
                "Trona Plegable de Viaje",
                "defective",
                30,
                35.50,
                True,
                "Defectuosa dentro de plazo (15/30 dias)",
            ),
        ],
        criterios="Primera aparicion en el kit mixto de 'jardineria_bricolaje' y 'bebe_puericultura'. Los 2 "
        "articulos son elegibles y su suma (65.50€ + 35.50€ = 101.00€) supera el umbral HITL por "
        "solo 1€. Verifica que la regla sea estrictamente '> 100€' (no '>= 100€'). Comparar con "
        "QAM-010 (mismo diseño, un euro por debajo) para aislar el limite exacto.",
    ),
    dict(
        num="010",
        order_number="ORD-QAM-0010",
        dias_entrega=10,
        resultado="✅ VÁLIDO",
        resultado_txt="aprobado (2 de 2, justo por debajo del umbral, sin HITL)",
        items=[
            (
                "mascotas",
                "Rascador para Gato XL",
                "defective",
                21,
                49.99,
                True,
                "Defectuoso dentro de plazo (10/21 dias)",
            ),
            (
                "libros_papeleria",
                "Cuaderno de Notas A5 (Pack de 3)",
                "defective",
                21,
                49.99,
                True,
                "Defectuosa dentro de plazo (10/21 dias)",
            ),
        ],
        criterios="Caso EMPAREJADO con QAM-009 para aislar la variable del umbral HITL: 2 articulos "
        "elegibles de categorias distintas, ambos claramente dentro de plazo, pero la suma "
        "(49.99€ + 49.99€ = 99.98€) queda justo por debajo de 100€. Debe aprobarse "
        "automaticamente SIN pausa HITL. Ejecutar QAM-009 y QAM-010 juntos para detectar un "
        "umbral mal implementado (p.ej. '>=100' en vez de '>100', o errores de redondeo).",
    ),
    dict(
        num="011",
        order_number="ORD-QAM-0011",
        dias_entrega=6,
        resultado="🔄 HITL",
        resultado_txt="HITL sobre un unico articulo de importe muy alto",
        items=[
            (
                "electronica_informatica",
                "Portatil Ultradelgado 14 Pulgadas",
                "defective",
                30,
                899.00,
                True,
                "Defectuoso dentro de plazo (6/30 dias)",
            ),
            (
                "drogueria_salud",
                "Gel de Ducha Dermoprotector",
                "changed_mind",
                21,
                6.50,
                False,
                "Exclusion legal de higiene: envase abierto, cambio de opinion",
            ),
        ],
        criterios="Un solo articulo de importe muy alto (899.00€) basta por si solo para disparar el "
        "HITL, sin necesidad de sumar varios articulos. El segundo articulo es rechazado por "
        "higiene y su importe (6.50€) NO debe sumarse al reembolso ni influir en el mensaje de "
        "HITL, que debe referirse solo al portatil.",
    ),
    dict(
        num="012",
        order_number="ORD-QAM-0012",
        dias_entrega=8,
        resultado="❌ INVÁLIDO",
        resultado_txt="rechazo total (0 de 2 elegibles, dos motivos distintos)",
        items=[
            (
                "cosmetica_perfumeria",
                "Mascarilla Facial Set x5",
                "changed_mind",
                21,
                15.99,
                False,
                "Exclusion legal de higiene: set abierto, cambio de opinion",
            ),
            (
                "calzado",
                "Zapatillas de Vestir",
                "changed_mind",
                30,
                45.00,
                False,
                "Estado no admitido: uso evidente (suela desgastada), no es error de talla ni defecto",
            ),
        ],
        criterios="Los 2 articulos son NO elegibles pero por motivos DISTINTOS a los de QAM-004: aqui es "
        "higiene (cosmetica) + estado del producto no admitido (calzado, no por higiene ni por "
        "plazo). Ambos dias estan dentro de plazo, asi que la unica explicacion valida es la "
        "condicion de cada articulo. El mensaje de rechazo debe justificar cada uno por separado.",
    ),
    dict(
        num="013",
        order_number="ORD-QAM-0013",
        dias_entrega=7,
        resultado="🔄 HITL",
        resultado_txt="HITL, 3 de 3 elegibles (pedido completo aprobado, con HITL)",
        items=[
            (
                "electrodomesticos",
                "Freidora de Aire 5L",
                "defective",
                30,
                79.99,
                True,
                "Defectuosa dentro de plazo (7/30 dias)",
            ),
            (
                "juguetes",
                "Robot Teledirigido",
                "defective",
                30,
                34.50,
                True,
                "Defectuoso dentro de plazo (7/30 dias)",
            ),
            (
                "libros_papeleria",
                "Mochila Escolar Ergonomica",
                "wrong_item",
                21,
                27.99,
                True,
                "Articulo equivocado, dentro de plazo (7/21 dias)",
            ),
        ],
        criterios="3 articulos de 3 categorias distintas, TODOS elegibles (sin ningun rechazo), y aun asi "
        "requiere HITL porque la suma (79.99€ + 34.50€ + 27.99€ = 142.48€) supera el umbral. "
        "Contraste directo con QAM-006 (2 de 2 elegibles, SIN HITL por estar bajo el umbral): "
        "confirma que 'pedido 100% aprobado' no es sinonimo de 'sin revision humana'.",
    ),
    dict(
        num="014",
        order_number="ORD-QAM-0014",
        dias_entrega=12,
        resultado="🟡 PARCIAL",
        resultado_txt="parcialmente aprobado (2 de 3), por debajo del umbral",
        items=[
            (
                "juguetes",
                "Cocina de Juguete de Madera",
                "defective",
                30,
                38.00,
                True,
                "Defectuosa dentro de plazo (12/30 dias)",
            ),
            (
                "mascotas",
                "Cama para Perro Mediana",
                "defective",
                21,
                29.99,
                True,
                "Defectuosa dentro de plazo (12/21 dias)",
            ),
            (
                "alimentacion",
                "Cafe en Grano 1kg",
                "changed_mind",
                14,
                11.50,
                False,
                "Exclusion legal de higiene: paquete abierto, cambio de opinion (dentro de plazo, 12/14 dias)",
            ),
        ],
        criterios="Complementa a QAM-003 (tambien 2 de 3, pero por PLAZO): aqui el tercer articulo esta "
        "DENTRO de plazo y aun asi se rechaza por higiene (alimentacion). El importe elegible "
        "(38.00€ + 29.99€ = 67.99€) queda por debajo del umbral: parcial SIN HITL.",
    ),
    dict(
        num="015",
        order_number="ORD-QAM-0015",
        dias_entrega=11,
        resultado="🔄 HITL",
        resultado_txt="HITL, misma categoria, ambos elegibles",
        items=[
            (
                "deportes_aire_libre",
                "Bicicleta de Montaña Junior",
                "defective",
                30,
                189.00,
                True,
                "Defectuosa dentro de plazo (11/30 dias)",
            ),
            (
                "deportes_aire_libre",
                "Casco de Ciclismo Ajustable",
                "defective",
                30,
                34.99,
                True,
                "Defectuoso dentro de plazo (11/30 dias)",
            ),
        ],
        criterios="Variante de QAM-005 (misma categoria, un elegible y otro no, SIN HITL): aqui los DOS "
        "articulos de la MISMA categoria (deportes_aire_libre) son elegibles y su suma "
        "(189.00€ + 34.99€ = 223.99€) dispara el HITL. Verifica que la deduplicacion de la "
        "busqueda RAG (una sola consulta, misma categoria) no afecte al calculo agregado del "
        "umbral ni a que se nombren los dos articulos en el mensaje de HITL.",
    ),
    dict(
        num="016",
        order_number="ORD-QAM-0016",
        dias_entrega=17,
        resultado="❌ INVÁLIDO",
        resultado_txt="rechazo total (0 de 2 elegibles: plazo + higiene)",
        items=[
            (
                "alimentacion",
                "Miel de Flores Silvestres 250g",
                "changed_mind",
                14,
                7.99,
                False,
                "Fuera de plazo (17 dias > 14 maximo de la categoria)",
            ),
            (
                "drogueria_salud",
                "Champu Solido Ecologico",
                "changed_mind",
                21,
                9.99,
                False,
                "Exclusion legal de higiene: envase abierto, cambio de opinion (dentro de plazo, 17/21 dias)",
            ),
        ],
        criterios="Variante de QAM-004 con categorias nuevas (alimentacion + drogueria_salud, no usadas "
        "juntas hasta ahora) y los mismos dos motivos de rechazo (plazo vs higiene) para ampliar "
        "la cobertura de combinaciones categoria x motivo. Importe elegible: 0€, sin HITL.",
    ),
    dict(
        num="017",
        order_number="ORD-QAM-0017",
        dias_entrega=8,
        resultado="🔄 HITL",
        resultado_txt="HITL parcial (2 de 4 elegibles, 2 rechazados por higiene)",
        items=[
            (
                "electrodomesticos",
                "Aspiradora Robot",
                "defective",
                30,
                249.00,
                True,
                "Defectuosa dentro de plazo (8/30 dias)",
            ),
            (
                "juguetes",
                "Puzzle Interactivo 3D",
                "defective",
                30,
                15.00,
                True,
                "Defectuoso dentro de plazo (8/30 dias)",
            ),
            (
                "cosmetica_perfumeria",
                "Set de Maquillaje Basico",
                "changed_mind",
                21,
                42.00,
                False,
                "Exclusion legal de higiene: set abierto, cambio de opinion",
            ),
            (
                "alimentacion",
                "Chocolate Artesanal Caja",
                "changed_mind",
                14,
                9.90,
                False,
                "Exclusion legal de higiene: caja abierta, cambio de opinion",
            ),
        ],
        criterios="4 categorias distintas en una misma solicitud: 2 articulos elegibles + 2 rechazados, "
        "ambos por higiene (categorias distintas). Verifica que el evaluador haga 4 busquedas "
        "RAG (una por categoria) y que el HITL se dispare por la suma de SOLO los 2 elegibles "
        "(249.00€ + 15.00€ = 264.00€), no por el total del pedido (315.90€).",
    ),
    dict(
        num="018",
        order_number="ORD-QAM-0018",
        dias_entrega=3,
        resultado="✅ VÁLIDO",
        resultado_txt="aprobado (2 de 2, importe bajo, sin HITL)",
        items=[
            (
                "electronica_informatica",
                "Adaptador USB Multiple",
                "wrong_item",
                30,
                14.99,
                True,
                "Articulo equivocado, dentro de plazo (3/30 dias)",
            ),
            (
                "jardineria_bricolaje",
                "Guantes de Jardineria Reforzados",
                "defective",
                30,
                9.99,
                True,
                "Defectuosos dentro de plazo (3/30 dias)",
            ),
        ],
        criterios="REGRESION adicional (como QAM-006): pedido mixto de importe bajo (24.98€ en total) "
        "donde AMBOS articulos son elegibles y no hay HITL. Camino feliz con categorias nuevas "
        "(electronica + jardineria) para no depender siempre de las mismas dos categorias.",
    ),
    dict(
        num="019",
        order_number="ORD-QAM-0019",
        dias_entrega=6,
        resultado="🔄 HITL",
        resultado_txt="HITL, misma categoria de higiene (el defecto anula la exclusion)",
        items=[
            (
                "mascotas",
                "Transportadora para Perro Grande",
                "defective",
                21,
                119.00,
                True,
                "Defectuosa dentro de plazo (6/21 dias)",
            ),
            (
                "mascotas",
                "Comedero Automatico Programable",
                "defective",
                21,
                54.00,
                True,
                "Defectuoso dentro de plazo (6/21 dias)",
            ),
        ],
        criterios="'mascotas' esta en las categorias con exclusion legal de higiene, pero el motivo aqui "
        "es 'defective' (imputable a Mercadia), que ANULA esa exclusion: los 2 articulos son "
        "elegibles. Su suma (119.00€ + 54.00€ = 173.00€) dispara el HITL. Verifica que el "
        "evaluador no rechace por higiene solo por pertenecer la categoria a esa lista, sino que "
        "mire tambien el motivo.",
    ),
    dict(
        num="020",
        order_number="ORD-QAM-0020",
        dias_entrega=6,
        resultado="🟡 PARCIAL",
        resultado_txt="parcialmente aprobado (1 de 3), por debajo del umbral",
        items=[
            (
                "deportes_aire_libre",
                "Esterilla de Yoga Premium",
                "wrong_size",
                30,
                24.99,
                True,
                "Talla/medida equivocada, dentro de plazo (6/30 dias)",
            ),
            (
                "bebe_puericultura",
                "Biberon Anticolico Set",
                "changed_mind",
                30,
                13.50,
                False,
                "Exclusion legal de higiene: set abierto, cambio de opinion",
            ),
            (
                "mascotas",
                "Arnes para Perro Ajustable",
                "changed_mind",
                21,
                17.99,
                False,
                "Exclusion legal de higiene: embalaje abierto, cambio de opinion",
            ),
        ],
        criterios="Proporcion inversa a QAM-003/QAM-014 (2 elegibles de 3): aqui solo 1 de 3 articulos es "
        "elegible y los otros 2 se rechazan por higiene en categorias distintas (bebe_puericultura "
        "y mascotas). Importe elegible bajo (24.99€), sin HITL. Verifica que un solo articulo "
        "elegible entre varios rechazados no arrastre el resto.",
    ),
    dict(
        num="021",
        order_number="ORD-QAM-0021",
        dias_entrega=4,
        resultado="🔄 HITL",
        resultado_txt="HITL por suma de 5 articulos pequeños (ninguno es HITL por si solo)",
        items=[
            (
                "electronica_informatica",
                "Cargador Rapido USB-C 65W",
                "defective",
                30,
                24.99,
                True,
                "Defectuoso dentro de plazo (4/30 dias)",
            ),
            (
                "juguetes",
                "Set de Bloques de Construccion",
                "defective",
                30,
                19.99,
                True,
                "Defectuoso dentro de plazo (4/30 dias)",
            ),
            (
                "libros_papeleria",
                "Calculadora Cientifica",
                "defective",
                21,
                22.50,
                True,
                "Defectuosa dentro de plazo (4/21 dias)",
            ),
            (
                "calzado",
                "Calcetines Tecnicos Running (Pack de 3)",
                "wrong_size",
                30,
                14.99,
                True,
                "Talla equivocada, dentro de plazo (4/30 dias)",
            ),
            (
                "deportes_aire_libre",
                "Botella Termica 1L",
                "defective",
                30,
                24.99,
                True,
                "Defectuosa dentro de plazo (4/30 dias)",
            ),
        ],
        criterios="El caso mixto con MAS articulos y categorias del kit (5 categorias distintas, 5 "
        "elegibles, sin ningun rechazo). Ningun articulo individual se acerca al umbral HITL "
        "(el mas caro es 24.99€), pero la SUMA de los 5 (107.46€) si lo supera. Verifica que el "
        "evaluador haga 5 busquedas RAG y que el reembolso agregado se calcule sobre TODOS los "
        "articulos elegibles, no solo sobre los 2 primeros.",
    ),
    dict(
        num="022",
        order_number="ORD-QAM-0022",
        dias_entrega=9,
        resultado="✅ VÁLIDO",
        resultado_txt="aprobado (2 de 2, misma categoria, sin HITL)",
        items=[
            (
                "libros_papeleria",
                "Diario de Gratitud Tapa Blanda",
                "defective",
                21,
                11.99,
                True,
                "Defectuoso dentro de plazo (9/21 dias)",
            ),
            (
                "libros_papeleria",
                "Set de Boligrafos de Gel",
                "wrong_item",
                21,
                8.50,
                True,
                "Articulo equivocado, dentro de plazo (9/21 dias)",
            ),
        ],
        criterios="Completa la matriz 'misma categoria x HITL' junto con QAM-005 (misma cat., 1 elegible, "
        "sin HITL) y QAM-015 (misma cat., 2 elegibles, CON HITL): aqui 2 elegibles de la MISMA "
        "categoria (libros_papeleria) suman solo 20.49€, por debajo del umbral. Sin HITL.",
    ),
    dict(
        num="023",
        order_number="ORD-QAM-0023",
        dias_entrega=24,
        resultado="🔄 HITL",
        resultado_txt="HITL sobre un unico articulo (el otro rechazado por plazo)",
        items=[
            (
                "electrodomesticos",
                "Lavavajillas Compacto",
                "defective",
                30,
                329.00,
                True,
                "Defectuoso dentro de plazo (24/30 dias)",
            ),
            (
                "libros_papeleria",
                "Cuaderno Universitario Tapa Blanda",
                "changed_mind",
                21,
                6.50,
                False,
                "Fuera de plazo (24 dias > 21 maximo de la categoria)",
            ),
        ],
        criterios="Variante de QAM-011 (un unico articulo caro dispara el HITL) pero con el segundo "
        "articulo rechazado por PLAZO en vez de higiene: mismo 'dias_entrega' para todo el "
        "pedido (24 dias) es valido para electrodomesticos (max. 30) pero invalido para "
        "libros_papeleria (max. 21). El HITL debe basarse solo en los 329.00€ del lavavajillas.",
    ),
    dict(
        num="024",
        order_number="ORD-QAM-0024",
        dias_entrega=14,
        resultado="🟡 PARCIAL",
        resultado_txt="parcialmente aprobado (2 de 3), justo por debajo del umbral",
        items=[
            (
                "electrodomesticos",
                "Batidora de Vaso 1.5L",
                "defective",
                30,
                42.00,
                True,
                "Defectuosa dentro de plazo (14/30 dias)",
            ),
            (
                "juguetes",
                "Pista de Coches Electrica",
                "defective",
                30,
                35.00,
                True,
                "Defectuosa dentro de plazo (14/30 dias)",
            ),
            (
                "cosmetica_perfumeria",
                "Perfume Miniatura 15ml",
                "changed_mind",
                21,
                9.99,
                False,
                "Exclusion legal de higiene: frasco abierto, cambio de opinion",
            ),
        ],
        criterios="Contraste con QAM-013 (3 categorias, 3 de 3 elegibles, CON HITL): aqui 2 de 3 son "
        "elegibles y su suma (42.00€ + 35.00€ = 77.00€) se queda por debajo del umbral. Sirve "
        "para comprobar que el evaluador no confunde 'varios articulos y categorias' con "
        "'siempre requiere HITL'.",
    ),
    dict(
        num="025",
        order_number="ORD-QAM-0025",
        dias_entrega=5,
        resultado="🔄 HITL",
        resultado_txt="HITL, 3 de 3 elegibles con motivos distintos",
        items=[
            (
                "calzado",
                "Zapatillas Deportivas Trail",
                "wrong_size",
                30,
                68.00,
                True,
                "Talla equivocada, dentro de plazo (5/30 dias)",
            ),
            (
                "electronica_informatica",
                "Teclado Mecanico Compacto",
                "defective",
                30,
                39.99,
                True,
                "Defectuoso dentro de plazo (5/30 dias)",
            ),
            (
                "juguetes",
                "Dron Mini con Camara",
                "wrong_item",
                30,
                44.00,
                True,
                "Articulo equivocado, dentro de plazo (5/30 dias)",
            ),
        ],
        criterios="3 articulos elegibles con TRES motivos distintos en la misma solicitud (talla "
        "equivocada, defecto, articulo erroneo), todos imputables a Mercadia o al proceso de "
        "envio. La suma (68.00€ + 39.99€ + 44.00€ = 151.99€) dispara el HITL. Verifica que el "
        "evaluador no necesite que los motivos coincidan entre articulos para aprobarlos todos.",
    ),
    dict(
        num="026",
        order_number="ORD-QAM-0026",
        dias_entrega=7,
        resultado="❌ INVÁLIDO",
        resultado_txt="rechazo total (0 de 2 elegibles, ambos por estado no admitido)",
        items=[
            (
                "calzado",
                "Sandalias de Playa",
                "changed_mind",
                30,
                19.99,
                False,
                "Estado no admitido: uso evidente (arena/desgaste), no es error de talla ni defecto",
            ),
            (
                "deportes_aire_libre",
                "Guantes de Ciclismo",
                "changed_mind",
                30,
                12.99,
                False,
                "Estado no admitido: visiblemente desgastados por uso intensivo",
            ),
        ],
        criterios="A diferencia de QAM-004/QAM-016 (higiene o plazo), aqui NINGUNA de las dos categorias "
        "tiene exclusion legal de higiene y ambos dias estan muy dentro de plazo: el rechazo es "
        "puramente por el ESTADO del producto (uso evidente) en las dos categorias. Aisla ese "
        "motivo de rechazo sin mezclarlo con higiene o plazo. Importe elegible: 0€, sin HITL.",
    ),
    dict(
        num="027",
        order_number="ORD-QAM-0027",
        dias_entrega=10,
        resultado="🔄 HITL",
        resultado_txt="HITL sobre un unico articulo (2 rechazados por higiene)",
        items=[
            (
                "deportes_aire_libre",
                "Kayak Inflable 2 Plazas",
                "defective",
                30,
                389.00,
                True,
                "Defectuoso dentro de plazo (10/30 dias)",
            ),
            (
                "cosmetica_perfumeria",
                "Colonia Infantil 200ml",
                "changed_mind",
                21,
                18.50,
                False,
                "Exclusion legal de higiene: frasco abierto, cambio de opinion",
            ),
            (
                "bebe_puericultura",
                "Chupetes Ortodoncicos Pack x2",
                "changed_mind",
                30,
                7.99,
                False,
                "Exclusion legal de higiene: blister abierto, cambio de opinion",
            ),
        ],
        criterios="Variante de QAM-011/QAM-023 (un unico articulo caro dispara el HITL) pero con DOS "
        "articulos rechazados en paralelo, cada uno de una categoria de higiene distinta. "
        "Verifica que dos exclusiones de higiene simultaneas no se combinen ni se confundan "
        "entre si, y que el HITL se calcule solo sobre el kayak (389.00€).",
    ),
    dict(
        num="028",
        order_number="ORD-QAM-0028",
        dias_entrega=10,
        resultado="🟡 PARCIAL",
        resultado_txt="parcialmente aprobado (2 de 4), por debajo del umbral",
        items=[
            (
                "electronica_informatica",
                "Funda Protectora para Portatil",
                "wrong_item",
                30,
                15.99,
                True,
                "Articulo equivocado, dentro de plazo (10/30 dias)",
            ),
            (
                "jardineria_bricolaje",
                "Manguera de Riego 20m",
                "defective",
                30,
                22.00,
                True,
                "Defectuosa dentro de plazo (10/30 dias)",
            ),
            (
                "drogueria_salud",
                "Locion Corporal 400ml",
                "changed_mind",
                21,
                8.99,
                False,
                "Exclusion legal de higiene: envase abierto, cambio de opinion",
            ),
            (
                "alimentacion",
                "Miel Artesanal 500g",
                "changed_mind",
                14,
                6.50,
                False,
                "Exclusion legal de higiene: tarro abierto, cambio de opinion",
            ),
        ],
        criterios="Version 'bajo el umbral' de QAM-017 (misma forma: 4 categorias, 2 elegibles + 2 "
        "rechazados por higiene) pero con importes pequeños: la suma de los 2 elegibles "
        "(15.99€ + 22.00€ = 37.99€) se queda muy por debajo de 100€. Sin HITL. Comparar ambos "
        "casos para verificar que el numero de categorias no dispara el HITL por si solo.",
    ),
]

# Caso 008: pedido inexistente, sin datos reales en BD.
CASE_008 = dict(
    id_="QAM-008",
    order_number="ORD-QAM-9999",
    resultado="⚠️ ERROR",
    saludo="Hola, tengo un problema con un pedido",
    mensaje=(
        "Es el pedido ORD-QAM-9999. Quiero devolver dos articulos: uno porque llego roto y otro porque "
        "cambie de opinion."
    ),
    palabras_clave="no se pudo encontrar el pedido, verifica el numero, sin inventar aprobacion ni rechazo",
    criterios="Pedido con order_number inexistente y mencion explicita de 2 articulos (intencion de "
    "devolucion mixta). Verifica que fetch_order_data controle el error ANTES de llegar al "
    "evaluador, y que el LLM de triaje no invente order_id/items ni un resultado de aprobacion/"
    "rechazo para un pedido que no existe.",
    notas="Camino de error, no ejercita evaluator_agent. Complementa (no sustituye) los casos "
    "QAM-001..007, que si ejercitan el fix de elegibilidad por articulo.",
)

CATEGORY_LABEL = {
    "electronica_informatica": "Electronica e Informatica",
    "cosmetica_perfumeria": "Cosmetica y Perfumeria",
    "electrodomesticos": "Electrodomesticos",
    "drogueria_salud": "Drogueria y Salud",
    "juguetes": "Juguetes",
    "libros_papeleria": "Libros y Papeleria",
    "alimentacion": "Alimentacion",
    "calzado": "Calzado",
    "mascotas": "Mascotas",
    "deportes_aire_libre": "Deportes y Aire Libre",
    "jardineria_bricolaje": "Jardineria y Bricolaje",
    "bebe_puericultura": "Bebe y Puericultura",
}


def eligible_amount(items):
    return round(sum(p for _, _, _, _, p, ok, _ in items if ok), 2)


def total_amount(items):
    return round(sum(p for _, _, _, _, p, ok, _ in items if True), 2)


def build_message(case):
    order_number = case["order_number"]
    parts = []
    for cat, name, motivo, _plazo, _precio, ok, _just in case["items"]:
        if motivo == "defective":
            frase = f"{name} porque ha llegado defectuoso/a"
        elif motivo == "changed_mind":
            frase = f"{name} porque he cambiado de opinion"
        elif motivo == "wrong_size":
            frase = f"{name} porque no es la talla que pedi"
        elif motivo == "wrong_item":
            frase = f"{name} porque no es el articulo que pedi"
        else:
            frase = f"{name} por el motivo: {motivo}"
        parts.append(frase)
    if len(parts) == 2:
        cuerpo = f"{parts[0]}, y {parts[1]}"
    else:
        cuerpo = ", ".join(parts[:-1]) + f", y {parts[-1]}"
    return f"Es el pedido {order_number}. Quiero devolver {len(parts)} articulos: {cuerpo}."


def build_keywords(case):
    aprobados = [n for _, n, _, _, _, ok, _ in case["items"] if ok]
    rechazados = [n for _, n, _, _, _, ok, _ in case["items"] if not ok]
    kw = []
    if aprobados:
        kw.append(
            "aprobado: "
            + ", ".join(aprobados)
            + f" ({eligible_amount(case['items']):.2f}€)"
        )
    if rechazados:
        kw.append("rechazado: " + ", ".join(rechazados))
    if eligible_amount(case["items"]) > 100:
        kw.append("revision de un administrador / HITL")
    return " | ".join(kw)


def build_notas(case):
    lines = []
    for cat, name, motivo, plazo, precio, ok, just in case["items"]:
        estado = "VALIDO" if ok else "INVALIDO"
        lines.append(
            f"{name} [{CATEGORY_LABEL.get(cat, cat)}]: motivo={motivo}, plazo max={plazo}d, "
            f"dias desde entrega={case['dias_entrega']}, importe={precio:.2f}€ -> {estado} ({just})"
        )
    lines.append(
        f"Importe elegible a reembolsar: {eligible_amount(case['items']):.2f}€ "
        f"(total del pedido: {total_amount(case['items']):.2f}€)"
    )
    return "\n".join(lines)


# ── 1) Generar el Excel ─────────────────────────────────────────────────


def generate_excel():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Casos de prueba"

    headers = [
        "tester",
        "ID",
        "Resultado",
        "Nº Pedido",
        "Categoría",
        "Producto",
        "Motivo",
        "Plazo Max",
        "Días",
        "Importe",
        "Saludo del Chat",
        "Mensaje con Nº Pedido",
        "Palabras Clave Esperadas",
        "Criterios",
        "Notas",
        "Comentarios",
        "Pasa/Falla",
        "PR",
    ]
    ws.append(headers)
    header_fill = PatternFill(
        start_color="1F4E78", end_color="1F4E78", fill_type="solid"
    )
    for col_idx, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )
    ws.freeze_panes = "A2"

    saludos = [
        "Hola, tengo un problema con un pedido",
        "Buenos días, necesito devolver varios artículos",
        "Quiero hacer una devolución parcial",
        "Hola, dos artículos de mi pedido tienen problemas distintos",
        "Buenas, tengo que devolver un par de cosas",
        "Hola, todo bien con el pedido salvo dos detalles",
        "Necesito ayuda, el importe es alto",
    ]

    for i, case in enumerate(CASES):
        n = case["num"]
        cats = "\n".join(CATEGORY_LABEL.get(c, c) for c, *_ in case["items"])
        prods = "\n".join(name for _, name, *_ in case["items"])
        motivos = "\n".join(m for _, _, m, *_ in case["items"])
        plazos = "\n".join(f"{item[3]} días" for item in case["items"])
        importes = "\n".join(f"{item[4]:.2f}€" for item in case["items"])
        dias = str(case["dias_entrega"])

        row = [
            "",  # tester (a rellenar por quien ejecute la prueba)
            f"QAM-{n}",
            case["resultado"],
            case["order_number"],
            cats,
            prods,
            motivos,
            plazos,
            dias,
            importes,
            saludos[i % len(saludos)],
            build_message(case),
            build_keywords(case),
            case["criterios"],
            build_notas(case),
            "",  # Comentarios (a rellenar tras ejecutar)
            "",  # Pasa/Falla
            "",  # PR
        ]
        ws.append(row)

    # Fila 008 (pedido inexistente)
    ws.append(
        [
            "",
            CASE_008["id_"],
            CASE_008["resultado"],
            CASE_008["order_number"],
            "—",
            "—",
            "—",
            "—",
            "—",
            "—",
            CASE_008["saludo"],
            CASE_008["mensaje"],
            CASE_008["palabras_clave"],
            CASE_008["criterios"],
            CASE_008["notas"],
            "",
            "",
            "",
        ]
    )

    widths = [8, 10, 14, 15, 22, 26, 14, 10, 7, 14, 26, 42, 34, 46, 46, 20, 12, 10]
    for idx, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = w

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    out_path = ROOT / "dataset" / "qa_manual_testing_casos_pedidos_mixtos.xlsx"
    wb.save(out_path)
    print(f"Excel escrito en: {out_path}")


# ── 2) Generar el SQL ───────────────────────────────────────────────────


def sql_escape(s: str) -> str:
    return s.replace("'", "''")


ALREADY_SEEDED_CASES = {"001", "002", "003", "004", "005", "006", "007"}
"""Casos cuyos INSERT ya se ejecutaron contra la BBDD en su momento: se excluyen
de este script (que se regenera cada vez que se añaden casos nuevos) para no
repetir trabajo. Sus filas siguen documentadas en el Excel y en la SELECT de
verificacion; si hiciera falta re-sembrarlos, el ON CONFLICT DO NOTHING de las
versiones anteriores del script los habria dejado igualmente intactos."""


def generate_sql():
    sql_cases = [c for c in CASES if c["num"] not in ALREADY_SEEDED_CASES]

    lines = []
    lines.append(
        "-- ========================================================================="
    )
    lines.append(
        "-- ReFlow -- Kit de datos QA: PEDIDOS MIXTOS (varias categorias por pedido,"
    )
    lines.append("-- elegibilidad de devolucion parcial)")
    lines.append("--")
    lines.append(
        "-- Complementa a supabase/qa_manual_testing_seed.sql (que solo cubre pedidos de"
    )
    lines.append(
        "-- UN articulo). Reutiliza las mismas 13 categorias/return_policies ya insertadas"
    )
    lines.append(
        "-- por ese script -- EJECUTAR DESPUES de qa_manual_testing_seed.sql (o de"
    )
    lines.append("-- seed_synthetic.sql), no antes.")
    lines.append("--")
    lines.append(
        "-- Generado por tests/qa/scripts/generate_mixed_qa_kit.py. Guion de pruebas (mensaje a"
    )
    lines.append("-- pegar en el chat por caso) en")
    lines.append("-- dataset/qa_manual_testing_casos_pedidos_mixtos.xlsx.")
    lines.append("--")
    lines.append(
        "-- NO incluye QAM-001..QAM-007: sus INSERT ya se ejecutaron contra la BBDD "
        "y se omiten aqui"
    )
    lines.append(
        "-- a proposito (siguen documentados en el Excel). Solo se insertan los casos "
        "nuevos:"
    )
    lines.append("-- " + ", ".join(f"QAM-{c['num']}" for c in sql_cases) + ".")
    lines.append("--")
    lines.append(
        "-- ADITIVO e IDEMPOTENTE (ON CONFLICT DO NOTHING). A PROPOSITO no inserta"
    )
    lines.append(
        "-- return_requests/return_items: los debe crear el propio agente al procesar la"
    )
    lines.append("-- conversacion -- es justo lo que se quiere probar.")
    lines.append(
        "-- ========================================================================="
    )
    lines.append("")

    # 1) customers
    lines.append(
        "-- -------------------------------------------------------------------------"
    )
    lines.append("-- 1) Clientes de prueba (uno por caso mixto)")
    lines.append(
        "-- -------------------------------------------------------------------------"
    )
    lines.append("INSERT INTO customers (id, email, full_name, phone, address) VALUES")
    cust_rows = []
    for i, case in enumerate(sql_cases, start=1):
        n = case["num"]
        cats = " + ".join(CATEGORY_LABEL.get(c, c) for c, *_ in case["items"])
        phone = f"+3460000{int(n):04d}"
        cust_rows.append(
            f"    ('{IDS[n]['customer_id']}', 'qa.casomixto{n}@reflow-test.local', "
            f"'QA Mixto {n} ({cats})', '{phone}', "
            '\'{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", '
            '"postal_code": "28001", "country": "ES"}\'::jsonb)'
        )
    lines.append(",\n".join(cust_rows))
    lines.append("ON CONFLICT (email) DO NOTHING;")
    lines.append("")

    # 2) products
    lines.append(
        "-- -------------------------------------------------------------------------"
    )
    lines.append(
        "-- 2) Productos de prueba (varios por caso, distinta categoria cada uno)"
    )
    lines.append(
        "-- -------------------------------------------------------------------------"
    )
    lines.append(
        "INSERT INTO products (id, sku, name, description, category, price, weight_kg, image_url) VALUES"
    )
    prod_rows = []
    for case in sql_cases:
        n = case["num"]
        for idx, (cat, name, motivo, plazo, precio, ok, just) in enumerate(
            case["items"]
        ):
            pid = IDS[n]["products"][idx]
            sku = f"QAM-{n}-{idx + 1:02d}"
            desc = f"Articulo ficticio de QA (pedido mixto) para el caso QAM-{n}, item {idx + 1}."
            prod_rows.append(
                f"    ('{pid}', '{sku}', '{sql_escape(name)}', '{desc}', '{cat}', {precio:.2f}, NULL, NULL)"
            )
    lines.append(",\n".join(prod_rows))
    lines.append("ON CONFLICT (sku) DO NOTHING;")
    lines.append("")

    # 3) orders
    lines.append(
        "-- -------------------------------------------------------------------------"
    )
    lines.append(
        "-- 3) Pedidos de prueba, YA ENTREGADOS hace 'dias_entrega' dias (ver Excel)"
    )
    lines.append(
        "-- -------------------------------------------------------------------------"
    )
    lines.append(
        "INSERT INTO orders (id, customer_id, order_number, status, total_amount, "
        "shipping_address, ordered_at, delivered_at) VALUES"
    )
    order_rows = []
    for case in sql_cases:
        n = case["num"]
        total = total_amount(case["items"])
        dias = case["dias_entrega"]
        order_rows.append(
            f"    ('{IDS[n]['order_id']}', '{IDS[n]['customer_id']}', '{case['order_number']}', "
            f"'delivered', {total:.2f}, "
            '\'{"street": "Calle de Pruebas QA Mixtos 1", "city": "Madrid", '
            '"postal_code": "28001", "country": "ES"}\'::jsonb, '
            f"NOW() - INTERVAL '{dias + 3} days', NOW() - INTERVAL '{dias} days')"
        )
    lines.append(",\n".join(order_rows))
    lines.append("ON CONFLICT (order_number) DO NOTHING;")
    lines.append("")

    # 4) order_items
    lines.append(
        "-- -------------------------------------------------------------------------"
    )
    lines.append(
        "-- 4) Lineas de pedido (varias por caso -- esto es lo que hace el pedido MIXTO)"
    )
    lines.append(
        "-- -------------------------------------------------------------------------"
    )
    lines.append(
        "INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES"
    )
    item_rows = []
    for case in sql_cases:
        n = case["num"]
        for idx, (cat, name, motivo, plazo, precio, ok, just) in enumerate(
            case["items"]
        ):
            oi_id = IDS[n]["order_items"][idx]
            pid = IDS[n]["products"][idx]
            item_rows.append(
                f"    ('{oi_id}', '{IDS[n]['order_id']}', '{pid}', 1, {precio:.2f}, {precio:.2f})"
            )
    lines.append(",\n".join(item_rows))
    lines.append("ON CONFLICT (id) DO NOTHING;")
    lines.append("")

    # 5) verificacion
    lines.append(
        "-- -------------------------------------------------------------------------"
    )
    lines.append(
        "-- 5) Verificacion: un pedido = varias filas (una por order_item), con la"
    )
    lines.append(
        "--    categoria y el importe de cada articulo para contrastar con el Excel."
    )
    lines.append(
        "-- -------------------------------------------------------------------------"
    )
    lines.append("SELECT")
    lines.append("    o.order_number,")
    lines.append("    o.id            AS order_id,")
    lines.append("    oi.id           AS order_item_id,")
    lines.append("    c.email         AS customer_email,")
    lines.append("    p.name          AS product_name,")
    lines.append("    p.category,")
    lines.append("    p.price         AS importe,")
    lines.append("    o.delivered_at,")
    lines.append(
        "    EXTRACT(DAY FROM NOW() - o.delivered_at)::int AS dias_desde_entrega_actual"
    )
    lines.append("FROM orders o")
    lines.append("JOIN customers c ON c.id = o.customer_id")
    lines.append("JOIN order_items oi ON oi.order_id = o.id")
    lines.append("JOIN products p ON p.id = oi.product_id")
    lines.append("WHERE o.order_number LIKE 'ORD-QAM-%'")
    lines.append("ORDER BY o.order_number, p.category;")
    lines.append("")

    out_path = ROOT / "supabase" / "qa_manual_testing_seed_pedidos_mixtos.sql"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"SQL escrito en: {out_path}")


if __name__ == "__main__":
    generate_excel()
    generate_sql()
