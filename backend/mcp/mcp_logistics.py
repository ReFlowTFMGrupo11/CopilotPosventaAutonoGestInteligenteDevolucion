"""
MCP Server: Logística

Tools:
- generate_shipping_label: Genera un PDF simulado de etiqueta de transporte.
- send_customer_notification: Simula envío de correo electrónico transaccional.
"""

import os
import uuid
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("logistics")

# Directory for generated labels
LABELS_DIR = Path(__file__).parent.parent.parent / "generated_labels"
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
    from reportlab.lib.pagesizes import A6
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    # Generate unique tracking number
    tracking_number = f"RF-{uuid.uuid4().hex[:10].upper()}"
    filename = f"label_{tracking_number}.pdf"
    filepath = LABELS_DIR / filename

    # Create PDF label
    c = canvas.Canvas(str(filepath), pagesize=A6)
    width, height = A6

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(10 * mm, height - 15 * mm, "ETIQUETA DE DEVOLUCIÓN")

    # Tracking number
    c.setFont("Helvetica-Bold", 10)
    c.drawString(10 * mm, height - 25 * mm, f"Tracking: {tracking_number}")

    # Order info
    c.setFont("Helvetica", 9)
    c.drawString(10 * mm, height - 35 * mm, f"Pedido: {order_id[:8]}...")

    # Customer info
    y = height - 45 * mm
    if customer_name:
        c.drawString(10 * mm, y, f"De: {customer_name}")
        y -= 5 * mm
    if customer_address:
        c.drawString(10 * mm, y, f"Dir: {customer_address[:50]}")
        y -= 5 * mm

    # Destination (warehouse)
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
    for item in items[:5]:  # Max 5 items on label
        c.drawString(12 * mm, y, f"• {item.get('name', 'Item')} x{item.get('quantity', 1)}")
        y -= 4 * mm

    # Date
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
    notification_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()

    # Log the simulated email
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
    import json

    with open(log_file, "a") as f:
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


# ---------------------------------------------------------------------------
# Run server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8002)
