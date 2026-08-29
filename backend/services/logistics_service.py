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
LABELS_DIR = Path(__file__).parent.parent.parent / "generated_labels"
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
    from reportlab.lib.pagesizes import A6
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    # Número de seguimiento legible: prefijo "RF-" + 10 caracteres hex en
    # mayúsculas tomados de un UUID4 aleatorio.
    tracking_number = f"RF-{uuid.uuid4().hex[:10].upper()}"
    filename = f"label_{tracking_number}.pdf"
    filepath = LABELS_DIR / filename

    c = canvas.Canvas(str(filepath), pagesize=A6)
    width, height = A6

    c.setFont("Helvetica-Bold", 14)
    c.drawString(10 * mm, height - 15 * mm, "ETIQUETA DE DEVOLUCIÓN")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(10 * mm, height - 25 * mm, f"Tracking: {tracking_number}")

    # Muestra solo los primeros 8 caracteres del UUID del pedido para que
    # quepa en el ancho de la etiqueta.
    c.setFont("Helvetica", 9)
    c.drawString(10 * mm, height - 35 * mm, f"Pedido: {order_id[:8]}...")

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
    c.drawString(10 * mm, y, "C/ Logística 42, Madrid 28001")

    y -= 10 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(10 * mm, y, "Artículos:")
    y -= 5 * mm
    c.setFont("Helvetica", 8)
    # Limita a los primeros 5 items para que quepan en la etiqueta A6.
    for item in items[:5]:
        c.drawString(
            12 * mm, y, f"• {item.get('name', 'Item')} x{item.get('quantity', 1)}"
        )
        y -= 4 * mm

    y -= 5 * mm
    c.setFont("Helvetica", 7)
    c.drawString(10 * mm, y, f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

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
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

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
