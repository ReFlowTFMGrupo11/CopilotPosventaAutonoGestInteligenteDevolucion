"""
Servicio de logística: generación de la etiqueta de transporte (PDF) y notificación
al cliente. Contiene la lógica que antes vivía dentro de las funciones `@mcp.tool()`
de backend/mcp/mcp_logistics.py (ver backend/services/supabase_service.py para la
explicación completa de por qué existe esta capa).
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

# __file__ = .../backend/services/logistics_service.py, así que subir 3 niveles
# (parent.parent.parent) lleva a la raíz del proyecto.
# Path(__file__): ruta de este propio archivo. .parent x3 sube:
# services/ -> backend/ -> raíz del proyecto. Ahí se crea la carpeta de salida.
LABELS_DIR = Path(__file__).parent.parent.parent / "generated_labels"
# exist_ok=True: no falla si la carpeta ya existe (se ejecuta al importar el módulo).
LABELS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Generación de etiqueta de transporte
# ---------------------------------------------------------------------------


async def generate_shipping_label(
    order_id: str,
    items: list[dict],
    customer_name: str = "",
    customer_address: str = "",
) -> dict:
    """Genera un archivo PDF simulado de la etiqueta de transporte utilizando reportlab.

    Args:
        order_id: UUID del pedido asociado.
        items: Lista de items a devolver, cada uno con "name" y "quantity".
        customer_name: Nombre del cliente para la etiqueta.
        customer_address: Dirección del cliente.
    """
    # Imports locales: reportlab solo se carga cuando esta función se invoca,
    # no al arrancar el servidor MCP que la envuelve.
    from reportlab.lib.pagesizes import A6   # tamaño de página (etiqueta pequeña).
    from reportlab.lib.units import mm       # unidad de medida en milímetros.
    from reportlab.pdfgen import canvas      # API de "lienzo" para dibujar el PDF.

    # Número de seguimiento legible: prefijo "RF-" + 10 caracteres hex en
    # mayúsculas tomados de un UUID4 aleatorio.
    # uuid4() genera un identificador aleatorio; .hex lo da como string
    # hexadecimal sin guiones; [:10] se queda solo con los 10 primeros
    # caracteres (suficiente para que sea único y corto de leer).
    tracking_number = f"RF-{uuid.uuid4().hex[:10].upper()}"
    filename = f"label_{tracking_number}.pdf"
    filepath = LABELS_DIR / filename

    # Crea el lienzo PDF apuntando directamente al archivo de destino.
    c = canvas.Canvas(str(filepath), pagesize=A6)
    # width/height: dimensiones de la página A6 en puntos, para calcular
    # coordenadas relativas al tamaño real del papel.
    width, height = A6

    # setFont: elige tipografía y tamaño para el siguiente texto dibujado.
    c.setFont("Helvetica-Bold", 14)
    # drawString(x, y, texto): dibuja texto en la posición (x, y), donde y se
    # mide desde ABAJO de la página (por eso se resta desde "height").
    c.drawString(10 * mm, height - 15 * mm, "ETIQUETA DE DEVOLUCIÓN")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(10 * mm, height - 25 * mm, f"Tracking: {tracking_number}")

    # Muestra solo los primeros 8 caracteres del UUID del pedido para que
    # quepa en el ancho de la etiqueta.
    c.setFont("Helvetica", 9)
    c.drawString(10 * mm, height - 35 * mm, f"Pedido: {order_id[:8]}...")

    # "y" se va decrementando manualmente línea a línea para simular un
    # layout vertical (reportlab no tiene flujo automático de texto).
    y = height - 45 * mm
    if customer_name:
        c.drawString(10 * mm, y, f"De: {customer_name}")
        y -= 5 * mm
    if customer_address:
        # Se trunca a 50 caracteres para evitar que el texto se salga del ancho A6.
        c.drawString(10 * mm, y, f"Dir: {customer_address[:50]}")
        y -= 5 * mm

    y -= 5 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(10 * mm, y, "Para: Centro de Devoluciones ReFlow")
    y -= 5 * mm
    c.setFont("Helvetica", 9)
    # Dirección de destino "hardcodeada": es un centro de devoluciones
    # ficticio, no un dato real del sistema.
    c.drawString(10 * mm, y, "C/ Logística 42, Madrid 28001")

    y -= 10 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(10 * mm, y, "Artículos:")
    y -= 5 * mm
    c.setFont("Helvetica", 8)
    # Limita a los primeros 5 items para que quepan en la etiqueta A6.
    for item in items[:5]:
        c.drawString(12 * mm, y, f"• {item.get('name', 'Item')} x{item.get('quantity', 1)}")
        y -= 4 * mm

    y -= 5 * mm
    c.setFont("Helvetica", 7)
    c.drawString(10 * mm, y, f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # save(): vuelca el contenido dibujado al archivo PDF en disco.
    c.save()

    return {
        "tracking_number": tracking_number,
        "label_path": str(filepath),
        "filename": filename,
        "order_id": order_id,
        "items_count": len(items),
    }


# ---------------------------------------------------------------------------
# Notificaciones al cliente
# ---------------------------------------------------------------------------


async def send_customer_notification(
    email: str,
    message: str,
    subject: str = "ReFlow - Actualización de tu devolución",
    attachment_path: str = "",
) -> dict:
    """Simula el envío de un correo electrónico transaccional con el enlace al PDF generado.

    Args:
        email: Dirección de correo electrónico del cliente.
        message: Cuerpo del mensaje.
        subject: Asunto del correo.
        attachment_path: Ruta al archivo adjunto (etiqueta PDF).
    """
    # No se envía correo real: se genera un id de notificación y una
    # marca de tiempo, y se deja constancia en un log en disco.
    notification_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()

    # Registro que se persiste como si fuera la entrada de un proveedor de
    # email transaccional (SendGrid, SES...) para poder auditar qué se
    # "envió" sin depender de un servicio externo real.
    log_entry = {
        "notification_id": notification_id,
        "to": email,
        "subject": subject,
        "message": message,
        "attachment": attachment_path if attachment_path else None,
        "status": "sent_simulated",
        "timestamp": timestamp,
    }

    log_file = LABELS_DIR / "notifications_log.jsonl"

    # Modo "a" (append) + ensure_ascii=False para preservar tildes/ñ legibles
    # en vez de escaparlas como \uXXXX; una línea JSON por notificación (JSONL).
    # Abrir en modo "a" en cada llamada (en vez de mantener el archivo abierto)
    # es más simple y evita corrupción si varias llamadas se solapan.
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    # print() de depuración: útil al ejecutar el servidor MCP a mano en una
    # terminal, para ver en tiempo real qué correo se "enviaría".
    print(f"📧 [SIMULATED] Email sent to {email}")
    print(f"   Subject: {subject}")
    print(f"   Attachment: {attachment_path or 'None'}")

    return {
        "notification_id": notification_id,
        "status": "sent_simulated",
        "to": email,
        "subject": subject,
        "timestamp": timestamp,
        "note": "Email sending is simulated. In production, integrate with a transactional email service.",
    }
