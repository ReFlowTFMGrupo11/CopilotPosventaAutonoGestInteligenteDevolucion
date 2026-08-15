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

ROOT = Path(__file__).resolve().parent.parent

# ── UUIDs fijos (generados una vez, no se regeneran en cada ejecucion) ─────

IDS = {
    "001": {
        "customer_id": "0cf624c3-e5ba-4ac3-ba09-d551e4f59609",
        "order_id": "5293d74e-10e3-4e71-b8c0-9452f410f756",
        "products": ["d8a3a304-8742-4a18-8522-56351baf8ce8", "3dfba202-f382-4111-a9b1-a7fd79dc50c2"],
        "order_items": ["198485e9-ed82-44b8-a253-c547fa56d13e", "4e5035cf-0d6d-4152-bbea-3552775efbd9"],
    },
    "002": {
        "customer_id": "150f572e-27e0-4364-8ccd-699d5945c223",
        "order_id": "b1563596-a9d7-464b-805f-d14853a8c9ff",
        "products": ["97179628-efff-45a7-bb50-3b2fb7889774", "7e9ca431-c188-4fb5-bf52-a1439af309d6"],
        "order_items": ["a5367ce3-6a87-4b85-84ab-f047b8c7751d", "ae74b5d7-aadc-48ab-bd9b-45d18658a330"],
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
        "products": ["57aba350-ffa3-4fce-b090-e089ef65419d", "b4c1f150-310d-4d1b-88e7-c73c18bc667f"],
        "order_items": ["2b2d136a-dc6d-427d-90ba-777c90d817d0", "263410db-d5f1-4803-bf24-e605580ec27c"],
    },
    "005": {
        "customer_id": "0c14d593-a08b-4a34-8f16-6e1dce77e11b",
        "order_id": "0c4855ae-d242-47b8-955c-a8d808b47ae7",
        "products": ["0e25ba43-b97e-47ad-856d-eee7ea159692", "6c4df112-afd1-45fd-95ab-dd57482bebe0"],
        "order_items": ["d441b6fa-ce08-416c-9861-dcd5676cf4de", "d724a845-37a5-49ed-9fd0-9d7368aea97c"],
    },
    "006": {
        "customer_id": "2d35af0b-9a3a-46d8-99ab-8c67042b9b26",
        "order_id": "9b92bf9e-10be-4ccf-825d-44c2906d647b",
        "products": ["02d4757f-3318-47a7-9fd3-f7964d982198", "869b41de-dc97-47b9-b06f-f558dbeb6453"],
        "order_items": ["60227fae-a954-4344-815c-147f0c3dd4b1", "487c8e34-ba95-47ee-b588-790d3cfb87f8"],
    },
    "007": {
        "customer_id": "9384c33a-53ee-4c8c-8a82-271248406a1a",
        "order_id": "723e1cbb-7897-49e8-a375-71dd24341303",
        "products": ["dac2f717-e61c-452e-81ed-f47db79656ec", "9de94575-b24c-4753-bcf9-6c481c7ed972"],
        "order_items": ["5a42f71b-6c5c-41ba-96c0-4b207a264e96", "6cc8e69f-49c4-4629-a205-acd33787a048"],
    },
}

# ── Definicion de los 8 casos ────────────────────────────────────────────
# Cada item: (category, name, motivo, plazo_max_dias, precio, valido, justificacion)

CASES = [
    dict(
        num="001", order_number="ORD-QAM-0001", dias_entrega=8,
        resultado="🟡 PARCIAL", resultado_txt="parcialmente aprobado",
        items=[
            ("electronica_informatica", "Auriculares Bluetooth Pro", "defective", 30, 39.99, True,
             "Defectuoso dentro de plazo (8/30 dias)"),
            ("cosmetica_perfumeria", "Perfume Eau de Parfum 50ml", "changed_mind", 21, 29.99, False,
             "Exclusion legal de higiene (Art. 103 TRLGDCU): precinto retirado por cambio de opinion"),
        ],
        criterios="Elegibilidad por articulo en pedido mixto: electronica (defectuoso, dentro de plazo) "
                  "valida + cosmetica (cambio de opinion, precinto retirado) invalida por exclusion legal "
                  "de higiene. El resultado NO debe colapsar a un unico booleano para todo el pedido.",
    ),
    dict(
        num="002", order_number="ORD-QAM-0002", dias_entrega=12,
        resultado="🔄 HITL", resultado_txt="HITL parcial (1 aprobado tras revision + 1 rechazado)",
        items=[
            ("electrodomesticos", "Microondas Digital 20L", "defective", 30, 149.99, True,
             "Defectuoso dentro de plazo (12/30 dias)"),
            ("drogueria_salud", "Champu Anticaspa 400ml", "changed_mind", 21, 12.99, False,
             "Exclusion legal de higiene: producto usado, cambio de opinion"),
        ],
        criterios="El importe elegible (solo el microondas, 149.99€) supera el umbral HITL de 100€ aunque "
                  "el pedido tenga un segundo articulo rechazado. Verifica que el HITL se calcule sobre el "
                  "reembolso de los articulos ELEGIBLES, no sobre el total del pedido, y que el champu no "
                  "se incluya en la etiqueta/reembolso aunque el admin apruebe.",
    ),
    dict(
        num="003", order_number="ORD-QAM-0003", dias_entrega=20,
        resultado="🟡 PARCIAL", resultado_txt="parcialmente aprobado (2 de 3)",
        items=[
            ("juguetes", "Puzzle 1000 Piezas Paisaje", "defective", 30, 24.99, True,
             "Defectuoso dentro de plazo (20/30 dias)"),
            ("libros_papeleria", "Agenda 2026 Tapa Dura", "defective", 21, 15.99, True,
             "Defectuoso dentro de plazo, en el limite (20/21 dias)"),
            ("alimentacion", "Lote de Conservas Gourmet", "changed_mind", 14, 18.50, False,
             "Fuera de plazo (20 dias > 14 maximo de la categoria)"),
        ],
        criterios="3 articulos de 3 categorias distintas en la misma solicitud: 2 elegibles (cada una con "
                  "su propio plazo maximo, uno de ellos justo en el limite) + 1 no elegible por plazo. "
                  "Verifica que el reembolso agregado sea la SUMA de los 2 elegibles (40.98€), no el total "
                  "del pedido (59.48€), y que se hagan 3 busquedas RAG (una por categoria).",
    ),
    dict(
        num="004", order_number="ORD-QAM-0004", dias_entrega=18,
        resultado="❌ INVÁLIDO", resultado_txt="rechazo total (0 de 2 elegibles)",
        items=[
            ("cosmetica_perfumeria", "Crema Facial Antiedad", "changed_mind", 21, 22.99, False,
             "Exclusion legal de higiene: producto usado, cambio de opinion"),
            ("alimentacion", "Aceite de Oliva Virgen Extra", "changed_mind", 14, 9.99, False,
             "Fuera de plazo (18 dias > 14 maximo de la categoria)"),
        ],
        criterios="Los 2 articulos son NO elegibles pero por motivos distintos (higiene vs plazo). Verifica "
                  "que el mensaje de rechazo explique AMBOS motivos por separado (no un motivo generico "
                  "unico), y que el pedido complete se enrute a 'reject' (ningun articulo elegible).",
    ),
    dict(
        num="005", order_number="ORD-QAM-0005", dias_entrega=10,
        resultado="🟡 PARCIAL", resultado_txt="parcialmente aprobado (misma categoria)",
        items=[
            ("calzado", "Zapatillas Running Pro", "wrong_size", 30, 59.99, True,
             "Talla equivocada, sin abrir, dentro de plazo (10/30 dias)"),
            ("calzado", "Botas de Senderismo", "changed_mind", 30, 89.99, False,
             "Estado no admitido: uso evidente tras varias semanas de trekking (no es defecto de fabrica "
             "ni error de talla)"),
        ],
        criterios="Los 2 articulos son de la MISMA categoria (calzado) y llegaron en el MISMO pedido (misma "
                  "fecha de entrega, mismo plazo maximo): la diferencia de elegibilidad viene del ESTADO del "
                  "articulo, no del plazo ni de la categoria. Verifica que la busqueda RAG se deduplique a "
                  "UNA sola llamada (misma categoria) pero el LLM siga evaluando cada order_item_id por "
                  "separado dentro de ese unico contexto de politica.",
    ),
    dict(
        num="006", order_number="ORD-QAM-0006", dias_entrega=4,
        resultado="✅ VÁLIDO", resultado_txt="aprobado (2 de 2, sin HITL)",
        items=[
            ("juguetes", "Muñeco Articulado Superheroe", "defective", 30, 19.99, True,
             "Defectuoso dentro de plazo (4/30 dias)"),
            ("mascotas", "Correa para Perro Ajustable", "wrong_item", 21, 14.99, True,
             "Articulo equivocado, dentro de plazo (4/21 dias)"),
        ],
        criterios="REGRESION: pedido mixto donde AMBOS articulos son elegibles. Confirma que el fix de "
                  "elegibilidad por articulo no rompe el camino feliz (antes del fix ya funcionaba porque "
                  "la unica categoria consultada por RAG resultaba ser, por azar, la correcta).",
    ),
    dict(
        num="007", order_number="ORD-QAM-0007", dias_entrega=9,
        resultado="🔄 HITL", resultado_txt="HITL, ambos aprobados tras revision",
        items=[
            ("electrodomesticos", "Aspiradora sin Cable", "defective", 30, 179.99, True,
             "Defectuoso dentro de plazo (9/30 dias)"),
            ("deportes_aire_libre", "Bicicleta Estatica Plegable", "defective", 30, 259.99, True,
             "Defectuoso dentro de plazo (9/30 dias)"),
        ],
        criterios="REGRESION del bug reportado por Tamara en QA-002 (PR #14): el mensaje de HITL no hacia "
                  "referencia al articulo que se estaba devolviendo. Aqui hay DOS articulos elegibles que "
                  "suman >100€ (439.98€): el mensaje de HITL y la resolucion final deben nombrar los DOS "
                  "articulos, no solo uno generico.",
    ),
]

# Caso 008: pedido inexistente, sin datos reales en BD.
CASE_008 = dict(
    id_="QAM-008", order_number="ORD-QAM-9999", resultado="⚠️ ERROR",
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
    notas="Camino de error, no ejercita policy_evaluator_agent. Complementa (no sustituye) los casos "
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
    return (
        f"Es el pedido {order_number}. Quiero devolver {len(parts)} articulos: {cuerpo}."
    )


def build_keywords(case):
    aprobados = [n for _, n, _, _, _, ok, _ in case["items"] if ok]
    rechazados = [n for _, n, _, _, _, ok, _ in case["items"] if not ok]
    kw = []
    if aprobados:
        kw.append("aprobado: " + ", ".join(aprobados) + f" ({eligible_amount(case['items']):.2f}€)")
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
        "tester", "ID", "Resultado", "Nº Pedido", "Categoría", "Producto", "Motivo",
        "Plazo Max", "Días", "Importe", "Saludo del Chat", "Mensaje con Nº Pedido",
        "Palabras Clave Esperadas", "Criterios", "Notas", "Comentarios", "Pasa/Falla", "PR",
    ]
    ws.append(headers)
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    for col_idx, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
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
    ws.append([
        "", CASE_008["id_"], CASE_008["resultado"], CASE_008["order_number"],
        "—", "—", "—", "—", "—", "—",
        CASE_008["saludo"], CASE_008["mensaje"], CASE_008["palabras_clave"],
        CASE_008["criterios"], CASE_008["notas"], "", "", "",
    ])

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


def generate_sql():
    lines = []
    lines.append("-- =========================================================================")
    lines.append("-- ReFlow -- Kit de datos QA: PEDIDOS MIXTOS (varias categorias por pedido,")
    lines.append("-- elegibilidad de devolucion parcial)")
    lines.append("--")
    lines.append("-- Complementa a supabase/qa_manual_testing_seed.sql (que solo cubre pedidos de")
    lines.append("-- UN articulo). Reutiliza las mismas 13 categorias/return_policies ya insertadas")
    lines.append("-- por ese script -- EJECUTAR DESPUES de qa_manual_testing_seed.sql (o de")
    lines.append("-- seed_synthetic.sql), no antes.")
    lines.append("--")
    lines.append("-- Generado por dataset/generate_mixed_qa_kit.py. Guion de pruebas (mensaje a")
    lines.append("-- pegar en el chat por caso) en")
    lines.append("-- dataset/qa_manual_testing_casos_pedidos_mixtos.xlsx.")
    lines.append("--")
    lines.append("-- ADITIVO e IDEMPOTENTE (ON CONFLICT DO NOTHING). A PROPOSITO no inserta")
    lines.append("-- return_requests/return_items: los debe crear el propio agente al procesar la")
    lines.append("-- conversacion -- es justo lo que se quiere probar.")
    lines.append("-- =========================================================================")
    lines.append("")

    # 1) customers
    lines.append("-- -------------------------------------------------------------------------")
    lines.append("-- 1) Clientes de prueba (uno por caso mixto)")
    lines.append("-- -------------------------------------------------------------------------")
    lines.append("INSERT INTO customers (id, email, full_name, phone, address) VALUES")
    cust_rows = []
    for i, case in enumerate(CASES, start=1):
        n = case["num"]
        cats = " + ".join(CATEGORY_LABEL.get(c, c) for c, *_ in case["items"])
        phone = f"+3460000{int(n):04d}"
        cust_rows.append(
            f"    ('{IDS[n]['customer_id']}', 'qa.casomixto{n}@reflow-test.local', "
            f"'QA Mixto {n} ({cats})', '{phone}', "
            "'{\"street\": \"Calle de Pruebas QA Mixtos 1\", \"city\": \"Madrid\", "
            "\"postal_code\": \"28001\", \"country\": \"ES\"}'::jsonb)"
        )
    lines.append(",\n".join(cust_rows))
    lines.append("ON CONFLICT (email) DO NOTHING;")
    lines.append("")

    # 2) products
    lines.append("-- -------------------------------------------------------------------------")
    lines.append("-- 2) Productos de prueba (varios por caso, distinta categoria cada uno)")
    lines.append("-- -------------------------------------------------------------------------")
    lines.append("INSERT INTO products (id, sku, name, description, category, price, weight_kg, image_url) VALUES")
    prod_rows = []
    for case in CASES:
        n = case["num"]
        for idx, (cat, name, motivo, plazo, precio, ok, just) in enumerate(case["items"]):
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
    lines.append("-- -------------------------------------------------------------------------")
    lines.append("-- 3) Pedidos de prueba, YA ENTREGADOS hace 'dias_entrega' dias (ver Excel)")
    lines.append("-- -------------------------------------------------------------------------")
    lines.append(
        "INSERT INTO orders (id, customer_id, order_number, status, total_amount, "
        "shipping_address, ordered_at, delivered_at) VALUES"
    )
    order_rows = []
    for case in CASES:
        n = case["num"]
        total = total_amount(case["items"])
        dias = case["dias_entrega"]
        order_rows.append(
            f"    ('{IDS[n]['order_id']}', '{IDS[n]['customer_id']}', '{case['order_number']}', "
            f"'delivered', {total:.2f}, "
            "'{\"street\": \"Calle de Pruebas QA Mixtos 1\", \"city\": \"Madrid\", "
            "\"postal_code\": \"28001\", \"country\": \"ES\"}'::jsonb, "
            f"NOW() - INTERVAL '{dias + 3} days', NOW() - INTERVAL '{dias} days')"
        )
    lines.append(",\n".join(order_rows))
    lines.append("ON CONFLICT (order_number) DO NOTHING;")
    lines.append("")

    # 4) order_items
    lines.append("-- -------------------------------------------------------------------------")
    lines.append("-- 4) Lineas de pedido (varias por caso -- esto es lo que hace el pedido MIXTO)")
    lines.append("-- -------------------------------------------------------------------------")
    lines.append(
        "INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES"
    )
    item_rows = []
    for case in CASES:
        n = case["num"]
        for idx, (cat, name, motivo, plazo, precio, ok, just) in enumerate(case["items"]):
            oi_id = IDS[n]["order_items"][idx]
            pid = IDS[n]["products"][idx]
            item_rows.append(
                f"    ('{oi_id}', '{IDS[n]['order_id']}', '{pid}', 1, {precio:.2f}, {precio:.2f})"
            )
    lines.append(",\n".join(item_rows))
    lines.append("ON CONFLICT (id) DO NOTHING;")
    lines.append("")

    # 5) verificacion
    lines.append("-- -------------------------------------------------------------------------")
    lines.append("-- 5) Verificacion: un pedido = varias filas (una por order_item), con la")
    lines.append("--    categoria y el importe de cada articulo para contrastar con el Excel.")
    lines.append("-- -------------------------------------------------------------------------")
    lines.append("SELECT")
    lines.append("    o.order_number,")
    lines.append("    o.id            AS order_id,")
    lines.append("    oi.id           AS order_item_id,")
    lines.append("    c.email         AS customer_email,")
    lines.append("    p.name          AS product_name,")
    lines.append("    p.category,")
    lines.append("    p.price         AS importe,")
    lines.append("    o.delivered_at,")
    lines.append("    EXTRACT(DAY FROM NOW() - o.delivered_at)::int AS dias_desde_entrega_actual")
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
