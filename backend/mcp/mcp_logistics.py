"""
MCP Server: Logística

Tools:
- generate_shipping_label: Genera un PDF simulado de etiqueta de transporte.
- send_customer_notification: Simula envío de correo electrónico transaccional.
"""

# os: importado por compatibilidad con el resto del módulo (no se usa
# directamente, pathlib.Path cubre el manejo de rutas).
import os
# sys: solo para forzar la codificación de stdout/stderr a UTF-8 (ver abajo).
import sys
# uuid: genera identificadores únicos para el nº de seguimiento y las notificaciones.
import uuid
# datetime: para poner fecha/hora en la etiqueta y en el log de notificaciones.
from datetime import datetime
# Path: manejo de rutas de fichero independiente del sistema operativo.
from pathlib import Path

# En Windows, la consola por defecto usa el codepage cp1252 (no UTF-8), que
# no puede representar los emojis usados en los print() de este módulo. Sin
# esto, send_customer_notification lanza UnicodeEncodeError en el propio
# proceso servidor en cuanto intenta loguear el correo simulado.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# FastMCP: clase del SDK oficial "mcp" (paquete PyPI "mcp", serie 1.x; ver
# el comentario equivalente en mcp_supabase.py sobre por qué 1.x y no 2.x).
from mcp.server.fastmcp import FastMCP

# Instancia del servidor MCP de logística.
mcp = FastMCP("logistics", host="0.0.0.0", port=8002)

# Directory for generated labels
# Directorio donde se guardan los PDFs generados y el log de notificaciones.
# __file__ = .../backend/mcp/mcp_logistics.py, así que subir 3 niveles
# (parent.parent.parent) lleva a la raíz del proyecto.
LABELS_DIR = Path(__file__).parent.parent.parent / "generated_labels"
# Crea el directorio si no existe; exist_ok=True evita error si ya existía.
LABELS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Tool 1: generate_shipping_label
# ---------------------------------------------------------------------------


@mcp.tool()
async def generate_shipping_label(
    order_id: str,
    items: list[dict],
    customer_name: str = "",
    customer_address: str = "",
) -> dict:
    """
    Genera un archivo PDF simulado de la etiqueta de transporte utilizando reportlab.
    Usado por Agente 3.

    Args:
        order_id: UUID del pedido asociado.
        items: Lista de items a devolver [{"name": "...", "quantity": 1}].
        customer_name: Nombre del cliente para la etiqueta.
        customer_address: Dirección del cliente.
    """
    # Imports locales: reportlab solo se carga cuando esta tool se invoca,
    # no al arrancar el servidor.
    from reportlab.lib.pagesizes import A6
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    # Generate unique tracking number
    # Número de seguimiento legible: prefijo "RF-" + 10 caracteres hex en
    # mayúsculas tomados de un UUID4 aleatorio.
    tracking_number = f"RF-{uuid.uuid4().hex[:10].upper()}"
    filename = f"label_{tracking_number}.pdf"
    filepath = LABELS_DIR / filename

    # Create PDF label
    # Crea el lienzo del PDF con tamaño de página A6 (tamaño típico de etiqueta).
    c = canvas.Canvas(str(filepath), pagesize=A6)
    width, height = A6

    # Header
    # Título en negrita cerca del borde superior.
    c.setFont("Helvetica-Bold", 14)
    c.drawString(10 * mm, height - 15 * mm, "ETIQUETA DE DEVOLUCIÓN")

    # Tracking number
    c.setFont("Helvetica-Bold", 10)
    c.drawString(10 * mm, height - 25 * mm, f"Tracking: {tracking_number}")

    # Order info
    # Muestra solo los primeros 8 caracteres del UUID del pedido para que
    # quepa en el ancho de la etiqueta.
    c.setFont("Helvetica", 9)
    c.drawString(10 * mm, height - 35 * mm, f"Pedido: {order_id[:8]}...")

    # Customer info
    # "y" es la coordenada vertical que se va decrementando a medida que se
    # añaden líneas, para no solaparlas.
    y = height - 45 * mm
    if customer_name:
        c.drawString(10 * mm, y, f"De: {customer_name}")
        y -= 5 * mm
    if customer_address:
        # Se trunca a 50 caracteres para evitar que el texto se salga del ancho A6.
        c.drawString(10 * mm, y, f"Dir: {customer_address[:50]}")
        y -= 5 * mm

    # Destination (warehouse)
    # Dirección fija del almacén de devoluciones (destinatario del envío).
    y -= 5 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(10 * mm, y, "Para: Centro de Devoluciones ReFlow")
    y -= 5 * mm
    c.setFont("Helvetica", 9)
    c.drawString(10 * mm, y, "C/ Logística 42, Madrid 28001")

    # Items
    y -= 10 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(10 * mm, y, "Artículos:")
    y -= 5 * mm
    c.setFont("Helvetica", 8)
    # Limita a los primeros 5 items para que quepan en la etiqueta A6;
    # item.get(...) usa valores por defecto si faltan claves.
    for item in items[:5]:  # Max 5 items on label
        c.drawString(12 * mm, y, f"• {item.get('name', 'Item')} x{item.get('quantity', 1)}")
        y -= 4 * mm

    # Date
    # Marca de tiempo de generación, formateada como "YYYY-MM-DD HH:MM".
    y -= 5 * mm
    c.setFont("Helvetica", 7)
    c.drawString(10 * mm, y, f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Vuelca el contenido dibujado al fichero PDF en disco.
    c.save()

    return {
        "tracking_number": tracking_number,
        "label_path": str(filepath),
        "filename": filename,
        "order_id": order_id,
        "items_count": len(items),
    }


# ---------------------------------------------------------------------------
# Tool 2: send_customer_notification
# ---------------------------------------------------------------------------


@mcp.tool()
async def send_customer_notification(
    email: str,
    message: str,
    subject: str = "ReFlow - Actualización de tu devolución",
    attachment_path: str = "",
) -> dict:
    """
    Simula el envío de un correo electrónico transaccional con el enlace al PDF generado.
    Usado por Agente 3.

    Args:
        email: Dirección de correo electrónico del cliente.
        message: Cuerpo del mensaje.
        subject: Asunto del correo.
        attachment_path: Ruta al archivo adjunto (etiqueta PDF).
    """
    # Simulate email sending (in production, use SendGrid, SES, etc.)
    # No se envía correo real: se genera un id de notificación y una
    # marca de tiempo, y se deja constancia en un log en disco.
    notification_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()

    # Log the simulated email
    # Estructura del registro que se persiste, una línea JSON por notificación.
    log_entry = {
        "notification_id": notification_id,
        "to": email,
        "subject": subject,
        "message": message,
        "attachment": attachment_path if attachment_path else None,
        "status": "sent_simulated",
        "timestamp": timestamp,
    }

    # Write to a log file for traceability
    log_file = LABELS_DIR / "notifications_log.jsonl"
    # Import local: json solo se necesita aquí, para serializar el log_entry.
    import json

    # Modo "a" (append) + ensure_ascii=False para preservar tildes/ñ legibles
    # en vez de escaparlas como \uXXXX; una línea JSON por notificación (JSONL).
    with open(log_file, "a") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    # Salida por consola a modo de confirmación visual de que la
    # "notificación" (simulada) se generó correctamente.
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


# ---------------------------------------------------------------------------
# Run server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Igual que en mcp_supabase.py: se sirve por Streamable HTTP (no SSE,
    # deprecado) en http://0.0.0.0:8002/mcp. Host/puerto ya fijados en el
    # constructor de FastMCP (línea 34).
    mcp.run(transport="streamable-http")
