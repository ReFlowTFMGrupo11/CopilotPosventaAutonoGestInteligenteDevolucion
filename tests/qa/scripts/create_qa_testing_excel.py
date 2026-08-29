#!/usr/bin/env python3
"""
Generador de Excel QA para pruebas manuales end-to-end del chatbot
Basado en qa_manual_testing_seed_v2.sql (24 casos de prueba)
"""

import os
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Crear workbook
wb = Workbook()
ws = wb.active
ws.title = "Casos de Prueba QA"

# Estilos
header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
header_font = Font(name="Arial", size=10, bold=True, color="FFFFFF")

valid_fill = PatternFill(start_color="C6E0B4", end_color="C6E0B4", fill_type="solid")
invalid_fill = PatternFill(start_color="F8CBAD", end_color="F8CBAD", fill_type="solid")
hitl_fill = PatternFill(start_color="FFE699", end_color="FFE699", fill_type="solid")

center_alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)
left_alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)

border = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

# Encabezados
headers = [
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
]

for col, header in enumerate(headers, 1):
    cell = ws.cell(row=1, column=col)
    cell.value = header
    cell.fill = header_fill
    cell.font = header_font
    cell.alignment = center_alignment
    cell.border = border

# Datos de los 24 casos (simplificados del CSV)
casos = [
    (
        "QA-001",
        "✅ VÁLIDO",
        "ORD-QA-0001",
        "alimentacion",
        "Alimento",
        "defective",
        "14 días",
        "5",
        "29.99€",
        "Hola, tengo un problema",
        "Es el pedido ORD-QA-0001. El alimento llegó defectuoso",
        "aprobada, 29.99€, dentro de plazo",
        "Plazo OK, estado válido, importe <100€",
        "Caso simple: aprobación automática",
    ),
    (
        "QA-002",
        "🔄 HITL",
        "ORD-QA-0002",
        "bebe_puericultura",
        "Cochecito",
        "defective",
        "30 días",
        "7",
        "299.99€",
        "Necesito ayuda con una devolución",
        "Es el pedido ORD-QA-0002. El cochecito tiene defecto en rueda",
        "derivado a HITL, importe > 100€",
        "Plazo OK, pero importe 299.99€ > 100€",
        "HITL por importe alto",
    ),
    (
        "QA-003",
        "✅ VÁLIDO",
        "ORD-QA-0003",
        "calzado",
        "Zapatillas",
        "wrong_size",
        "30 días",
        "12",
        "79.99€",
        "Quiero cambiar un artículo",
        "Es el pedido ORD-QA-0003. Las zapatillas me quedan pequeñas",
        "aprobada, cambio sin recargo, 79.99€",
        "Calzado: talla equivocada sin penalización",
        "Talla equivocada: aprobación automática",
    ),
    (
        "QA-004",
        "❌ INVÁLIDO",
        "ORD-QA-0004",
        "cosmetica_perfumeria",
        "Perfume",
        "changed_mind",
        "21 días",
        "0",
        "49.99€",
        "Buenos días, tengo un problema",
        "Es el pedido ORD-QA-0004. El perfume no me gusta, cambié opinión",
        "rechazado, higiene sensible, Art. 103",
        "Cosmética + cambio opinión + abierto = rechazo legal",
        "Exclusión legal Art. 103 TRLGDCU",
    ),
    (
        "QA-005",
        "🔄 HITL",
        "ORD-QA-0005",
        "deportes_aire_libre",
        "Bicicleta",
        "defective",
        "30 días",
        "17",
        "399.99€",
        "Necesito ayuda urgente",
        "Es el pedido ORD-QA-0005. La bicicleta tiene defecto en el cambio",
        "derivado a HITL, importe > 100€",
        "Plazo OK pero 399.99€ >> 100€",
        "HITL: importe muy alto",
    ),
    (
        "QA-006",
        "❌ INVÁLIDO",
        "ORD-QA-0006",
        "drogueria_salud",
        "Champú",
        "changed_mind",
        "21 días",
        "25",
        "12.99€",
        "Quiero devolver un producto",
        "Es el pedido ORD-QA-0006. El champú no me gustó, lo usé",
        "rechazado, higiene sensible, usado",
        "Droguería + usado + cambio opinión",
        "Exclusión legal: higiene sensible + usado",
    ),
    (
        "QA-007",
        "❌ INVÁLIDO",
        "ORD-QA-0007",
        "libros_papeleria",
        "Libro",
        "changed_mind",
        "21 días",
        "42",
        "24.99€",
        "Hola buenos días",
        "Es el pedido ORD-QA-0007. Cambié de opinión, el libro no lo necesito",
        "rechazado, fuera de plazo, 42 vs 21",
        "Plazo 42 días > 21 máximo",
        "Caso clásico: FUERA DE PLAZO",
    ),
    (
        "QA-008",
        "✅ VÁLIDO",
        "ORD-QA-0008",
        "mascotas",
        "Comida mascotas",
        "defective",
        "21 días",
        "3",
        "39.99€",
        "Buenos días, tengo un problema",
        "Es el pedido ORD-QA-0008. La comida tiene olor extraño, defectuosa",
        "aprobada, defectuoso, 39.99€",
        "Plazo OK, estado válido, importe <100€",
        "Mascotas defectuosa: aprobación automática",
    ),
    (
        "QA-009",
        "🔄 HITL",
        "ORD-QA-0009",
        "electrodomesticos",
        "Nevera",
        "defective",
        "30 días",
        "9",
        "849.99€",
        "Acabo de recibir",
        "Es el pedido ORD-QA-0009. La nevera hace ruido extraño, tiene defecto",
        "derivado a HITL, importe 849.99€",
        "Electrodoméstico defectuoso pero 849.99€ >> 100€",
        "HITL: electrodoméstico muy caro",
    ),
    (
        "QA-010",
        "🔄 HITL",
        "ORD-QA-0010",
        "electronica_informatica",
        "Portátil",
        "missing_parts",
        "30 días",
        "15",
        "899.99€",
        "Acabo de abrir el portátil",
        "Es el pedido ORD-QA-0010. Falta el cargador en la caja",
        "derivado a HITL, importe 899.99€",
        "Piezas faltantes pero 899.99€ >> 100€",
        "HITL: portátil muy caro + piezas faltantes",
    ),
    (
        "QA-011",
        "✅ VÁLIDO",
        "ORD-QA-0011",
        "jardineria_bricolaje",
        "Herramientas",
        "wrong_item",
        "30 días",
        "4",
        "69.99€",
        "Tengo un problema",
        "Es el pedido ORD-QA-0011. Recibí herramientas equivocadas",
        "aprobada, artículo equivocado, 69.99€",
        "Plazo OK, estado válido, importe <100€",
        "Artículo equivocado: aprobación automática",
    ),
    (
        "QA-012",
        "✅ VÁLIDO",
        "ORD-QA-0012",
        "juguetes",
        "Juguete",
        "defective",
        "30 días",
        "19",
        "89.99€",
        "El juguete está roto",
        "Es el pedido ORD-QA-0012. El juguete llegó roto, no funciona",
        "aprobada, defectuoso, 89.99€",
        "Plazo OK, estado válido, importe <100€",
        "Juguete defectuoso: aprobación automática",
    ),
    (
        "QA-013",
        "✅ VÁLIDO",
        "ORD-QA-0013",
        "moda_ropa",
        "Camiseta",
        "wrong_size",
        "30 días",
        "0",
        "34.99€",
        "Acabo de recibir",
        "Es el pedido ORD-QA-0013. La camiseta es M pero pedí L",
        "aprobada, talla incorrecta, sin recargo",
        "Moda: talla equivocada sin penalización",
        "Moda: talla = aprobación automática",
    ),
    (
        "QA-014",
        "🔄 HITL",
        "ORD-QA-0014",
        "muebles",
        "Sofá",
        "defective",
        "14 días",
        "2",
        "1299.99€",
        "Acabo de recibir el sofá",
        "Es el pedido ORD-QA-0014. El sofá tiene una costura rota",
        "derivado a HITL, importe 1299.99€, cliente frecuente",
        "Cliente frecuente (cust-14) + importe muy alto",
        "HITL: cliente frecuente ⚠️ + mueble caro",
    ),
    (
        "QA-015",
        "✅ VÁLIDO",
        "ORD-QA-0015",
        "hogar_decoracion",
        "Lámpara",
        "defective",
        "30 días",
        "8",
        "59.99€",
        "La lámpara no enciende",
        "Es el pedido ORD-QA-0015. La lámpara no enciende, cable dañado",
        "aprobada, defectuoso, 59.99€",
        "Plazo OK, estado válido, importe <100€",
        "Lámpara defectuosa: aprobación automática",
    ),
    (
        "QA-016",
        "❌ INVÁLIDO",
        "ORD-QA-0016",
        "joyeria_relojes",
        "Reloj",
        "defective",
        "15 días",
        "29",
        "299.99€",
        "Tengo un problema",
        "Es el pedido ORD-QA-0016. El reloj se detiene cada pocas horas",
        "rechazado, joyería plazo corto (15), 29 días",
        "Joyería: plazo muy corto (15 días), 29 días >>",
        "Joyería: FUERA DE PLAZO (15 vs 29)",
    ),
    (
        "QA-017",
        "❌ INVÁLIDO",
        "ORD-QA-0017",
        "alimentacion",
        "Aceite",
        "wrong_item",
        "14 días",
        "16",
        "15.99€",
        "Problema con el pedido",
        "Es el pedido ORD-QA-0017. Recibí aceite de oliva, pedí girasol",
        "rechazado, alimentación plazo 14 días, 16 días",
        "Alimentación: 16 días > 14 máximo",
        "Alimentación: FUERA DE PLAZO (14 vs 16)",
    ),
    (
        "QA-018",
        "🔄 HITL",
        "ORD-QA-0018",
        "electrodomesticos",
        "Lavadora",
        "defective",
        "30 días",
        "24",
        "549.99€",
        "Acabo de comprar una lavadora",
        "Es el pedido ORD-QA-0018. La lavadora no centrifuga bien",
        "derivado a HITL, importe 549.99€",
        "Electrodoméstico defectuoso pero 549.99€ > 100€",
        "HITL: electrodoméstico caro + defecto válido",
    ),
    (
        "QA-019",
        "✅ VÁLIDO",
        "ORD-QA-0019",
        "calzado",
        "Botas",
        "wrong_size",
        "30 días",
        "25",
        "119.99€",
        "Cambiar las botas",
        "Es el pedido ORD-QA-0019. Las botas son 41, pedí 42",
        "aprobada, talla incorrecta, importe 119.99€",
        "Calzado: talla equivocada sin penalización (aunque >100€)",
        "Nota: Importe >100€ pero talla válida",
    ),
    (
        "QA-020",
        "🔄 HITL",
        "ORD-QA-0020",
        "bebe_puericultura",
        "Silla coche",
        "defective",
        "30 días",
        "6",
        "199.99€",
        "Problema urgente",
        "Es el pedido ORD-QA-0020. La silla de coche tiene defecto en arnés",
        "derivado a HITL, importe 199.99€, seguridad bebé",
        "Equipo de seguridad defectuoso + importe alto",
        "HITL: silla de seguridad bebé + importe >100€",
    ),
    (
        "QA-021",
        "✅ VÁLIDO",
        "ORD-QA-0021",
        "drogueria_salud",
        "Loción",
        "defective",
        "21 días",
        "11",
        "19.99€",
        "La loción tiene un problema",
        "Es el pedido ORD-QA-0021. La loción parece contaminada",
        "aprobada o rechazado según si está abierta",
        "Higiene sensible: diferencia si sin abrir o abierta",
        "NOTA: Ambiguo si sin abrir vs abierta",
    ),
    (
        "QA-022",
        "✅ VÁLIDO",
        "ORD-QA-0022",
        "alimentacion",
        "Alimento gourmet",
        "defective",
        "14 días",
        "5",
        "59.99€",
        "Alimento gourmet",
        "Es el pedido ORD-QA-0022. El alimento llegó en mal estado, fermentado",
        "aprobada, defectuoso, 59.99€",
        "Plazo OK, estado válido, importe <100€",
        "Alimento defectuoso: aprobación automática",
    ),
    (
        "QA-023",
        "❌ INVÁLIDO",
        "ORD-QA-0023",
        "cosmetica_perfumeria",
        "Esmalte",
        "changed_mind",
        "21 días",
        "8",
        "14.99€",
        "Problema con el pedido",
        "Es el pedido ORD-QA-0023. El esmalte no me gusta, color diferente",
        "rechazado, higiene sensible, Art. 103",
        "Cosmética + cambio opinión + abierto = rechazo legal",
        "Cosmética: cambio opinión = rechazo por higiene",
    ),
    (
        "QA-024",
        "🔄 HITL",
        "ORD-QA-0024",
        "electronica_informatica",
        "Teclado",
        "defective",
        "30 días",
        "23",
        "129.99€",
        "El teclado está defectuoso",
        "Es el pedido ORD-QA-0024. El teclado tiene teclas que no funcionan",
        "derivado a HITL, importe 129.99€",
        "Defecto válido pero 129.99€ > 100€",
        "HITL: electrónica con defecto + importe >100€",
    ),
]

# Escribir datos
for row_idx, caso in enumerate(casos, 2):
    tipo = caso[1]
    if "VÁLIDO" in tipo:
        fill = valid_fill
    elif "INVÁLIDO" in tipo:
        fill = invalid_fill
    else:
        fill = hitl_fill

    for col_idx, value in enumerate(caso, 1):
        cell = ws.cell(row=row_idx, column=col_idx)
        cell.value = value
        cell.fill = fill
        cell.border = border

        if col_idx in [1, 2]:  # ID y Resultado
            cell.alignment = center_alignment
            cell.font = Font(name="Arial", size=9, bold=True)
        else:
            cell.alignment = left_alignment
            cell.font = Font(name="Arial", size=9)

# Ajustar anchos
column_widths = {
    "A": 8,  # ID
    "B": 12,  # Resultado
    "C": 15,  # Nº Pedido
    "D": 18,  # Categoría
    "E": 15,  # Producto
    "F": 15,  # Motivo
    "G": 12,  # Plazo
    "H": 6,  # Días
    "I": 10,  # Importe
    "J": 20,  # Saludo
    "K": 30,  # Mensaje
    "L": 30,  # Keywords
    "M": 25,  # Criterios
    "N": 25,  # Notas
}

for col, width in column_widths.items():
    ws.column_dimensions[col].width = width

# Altura de filas
ws.row_dimensions[1].height = 25
for i in range(2, len(casos) + 2):
    ws.row_dimensions[i].height = 35

# Congelar encabezado
ws.freeze_panes = "A2"

# Crear pestaña de leyenda
ws_legend = wb.create_sheet("Leyenda y Guía")

legend_content = [
    ("GUÍA DE PRUEBAS END-TO-END QA v2", "Arial", 12, True),
    ("", "Arial", 10, False),
    ("ESTRUCTURA DEL EXCEL:", "Arial", 11, True),
    ("", "Arial", 10, False),
    ("• Pestaña 'Casos de Prueba QA': 24 casos listos para probar", "Arial", 10, False),
    (
        "• Colores: Verde = VÁLIDO | Naranja = INVÁLIDO | Amarillo = REVISIÓN HUMANA",
        "Arial",
        10,
        False,
    ),
    ("", "Arial", 10, False),
    ("CÓMO EJECUTAR UNA PRUEBA:", "Arial", 11, True),
    ("", "Arial", 10, False),
    (
        "1. Ejecuta el SQL: qa_manual_testing_seed_v2.sql en Supabase",
        "Arial",
        10,
        False,
    ),
    ("2. Para cada caso en el Excel:", "Arial", 10, False),
    ("   a) Copia el 'Saludo del Chat' (columna J)", "Arial", 10, False),
    ("   b) Pégalo en el chat del bot", "Arial", 10, False),
    (
        "   c) Cuando el bot pida nº de pedido, copia 'Mensaje con Nº Pedido' (columna K)",
        "Arial",
        10,
        False,
    ),
    ("   d) Pégalo en el chat", "Arial", 10, False),
    (
        "   e) Verifica que la respuesta contenga 'Palabras Clave Esperadas' (columna L)",
        "Arial",
        10,
        False,
    ),
    ("   f) Marca ✓ o ✗ en la columna de resultado", "Arial", 10, False),
    ("", "Arial", 10, False),
    ("TIPOS DE RESULTADO:", "Arial", 11, True),
    ("", "Arial", 10, False),
    ("✅ VÁLIDO (Verde):", "Arial", 10, True),
    ("   El bot debe APROBAR automáticamente la devolución", "Arial", 10, False),
    (
        "   Criterios: dentro de plazo + estado aceptado + importe ≤100€ + sin motivos sensibles",
        "Arial",
        10,
        False,
    ),
    ("", "Arial", 10, False),
    ("❌ INVÁLIDO (Naranja):", "Arial", 10, True),
    ("   El bot debe RECHAZAR automáticamente", "Arial", 10, False),
    (
        "   Motivos: plazo superado (>5-10 días del límite) | exclusión legal | estado prohibido",
        "Arial",
        10,
        False,
    ),
    ("", "Arial", 10, False),
    ("🔄 REVISIÓN HUMANA (Amarillo):", "Arial", 10, True),
    ("   El bot debe DERIVAR a agente humano (HITL)", "Arial", 10, False),
    (
        "   Motivos: importe >100€ | zona frontera de plazo | motivo sensible | cliente frecuente",
        "Arial",
        10,
        False,
    ),
    ("", "Arial", 10, False),
    ("NOTAS IMPORTANTES:", "Arial", 11, True),
    ("", "Arial", 10, False),
    (
        "• Clientes 'frecuentes' (QA-014, QA-21): marcar en notas si el bot aplica reglas de abuso",
        "Arial",
        10,
        False,
    ),
    (
        "• Categorías 'sensibles' (cosmética, droguería, mascotas): higieneprohibida si abierta",
        "Arial",
        10,
        False,
    ),
    (
        "• Umbrales: importe >100€ SIEMPRE activa HITL, incluso si es válido por otros criterios",
        "Arial",
        10,
        False,
    ),
    (
        "• Plazos varían: muebles 14 días, joyería 15 días, la mayoría 30 días",
        "Arial",
        10,
        False,
    ),
    (
        "• Zona frontera: ±2 a ±5 días del límite = HITL (incluso si es válido)",
        "Arial",
        10,
        False,
    ),
]

for row_idx, (text, font_name, font_size, bold) in enumerate(legend_content, 1):
    cell = ws_legend.cell(row=row_idx, column=1)
    cell.value = text
    cell.font = Font(name=font_name, size=font_size, bold=bold)
    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)

    if text.startswith(("GUÍA", "ESTRUCTURA", "CÓMO", "TIPOS", "NOTAS")):
        cell.fill = PatternFill(
            start_color="D9E1F2", end_color="D9E1F2", fill_type="solid"
        )

ws_legend.column_dimensions["A"].width = 100

# Guardar workbook
output_path = Path(__file__).parent.parent / "cases" / "qa_manual_testing_cases_v2.xlsx"
output_path.parent.mkdir(parents=True, exist_ok=True)
wb.save(output_path)
print(f"✓ Archivo creado: {output_path}")
print(f"  - Pestaña 'Casos de Prueba QA': {len(casos)} casos")
print(f"  - Pestaña 'Leyenda y Guía': Instrucciones completas")
print(f"  - Colores: Verde (VÁLIDO) | Naranja (INVÁLIDO) | Amarillo (HITL)")
