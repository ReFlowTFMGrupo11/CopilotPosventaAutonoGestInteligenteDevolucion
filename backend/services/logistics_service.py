"""
Servicio de logística.

Contiene la lógica de generación de etiquetas PDF y envío de notificaciones.
Consumido por: agentes, MCP server, API REST.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Directorio de etiquetas generadas (raíz del proyecto / generated_labels)
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
    """Genera un archivo PDF simulado de la etiqueta de transporte.

    Args:
        order_id: UUID del pedido asociado.
        items: Lista de items [{"name": "...", "quantity": 1}].
        customer_name: Nombre del cliente.
        customer_address: Dirección del cliente.

    Returns:
        Dict con tracking_number, label_path, filename, etc.
    """
    from reportlab.lib.pagesizes import A6
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    tracking_number = f"RF-{uuid.uuid4().hex[:10].upper()}"
    filename = f"label_{tracking_number}.pdf"
    filepath = LABELS_DIR / filename

    c = canvas.Canvas(str(filepath), pagesize=A6)
    width, height = A6

    c.setFont("Helvetica-Bold", 14)
    c.drawString(10 * mm, height - 15 * mm, "ETIQUETA DE DEVOLUCIÓN")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(10 * mm, height - 25 * mm, f"Tracking: {tracking_number}")

    c.setFont("Helvetica", 9)
    c.drawString(10 * mm, height - 35 * mm, f"Pedido: {order_id[:8]}...")

    y = height - 45 * mm
    if customer_name:
        c.drawString(10 * mm, y, f"De: {customer_name}")
        y -= 5 * mm
    if customer_address:
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
    for item in items[:5]:
        c.drawString(12 * mm, y, f"• {item.get('name', 'Item')} x{item.get('quantity', 1)}")
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
    """Simula el envío de un correo electrónico transaccional.

    Args:
        email: Dirección de correo del cliente.
        message: Cuerpo del mensaje.
        subject: Asunto del correo.
        attachment_path: Ruta al archivo adjunto (etiqueta PDF).

    Returns:
        Dict con notification_id, status y timestamp.
    """
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
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    logger.info("📧 [SIMULATED] Email sent to %s | Subject: %s", email, subject)

    return {
        "notification_id": notification_id,
        "status": "sent_simulated",
        "to": email,
        "subject": subject,
        "timestamp": timestamp,
        "note": "Email sending is simulated. In production, integrate with a transactional email service.",
    }
