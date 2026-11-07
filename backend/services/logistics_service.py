"""
Servicio de logística: generación de la etiqueta de transporte (PDF) y notificación
al cliente. Contiene la lógica que antes vivía dentro de las funciones `@mcp.tool()`
de backend/mcp/mcp_logistics.py (ver backend/services/orders_service.py para la
explicación completa de por qué existe esta capa).
"""

import json
import uuid
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from backend.config import get_settings

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
    """Envía la notificación al cliente (AWS SES) o la simula si no hay SES.

    - Si ``SES_SENDER_EMAIL`` está configurado, envía un correo real con el
      PDF adjunto usando AWS SES. No hay contraseñas: boto3 obtiene
      credenciales temporales del IAM task role en ECS (o del perfil de
      ``~/.aws/credentials`` en local).
    - Si no está configurado, mantiene el modo simulado: solo escribe una
      línea en ``generated_labels/notifications_log.jsonl``.

    Args:
        email: Dirección de correo electrónico del cliente.
        message: Cuerpo del mensaje.
        subject: Asunto del correo.
        attachment_path: Ruta al archivo adjunto (etiqueta PDF).
    """
    settings = get_settings()

    notification_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()

    # En demos se puede redirigir todo a un buzón propio en vez de al email
    # real del cliente.
    recipient = settings.ses_recipient_override or email
    sender = settings.ses_sender_email

    status = "sent_simulated"
    message_id: str | None = None
    error: str | None = None

    if sender:
        try:
            message_id = _send_via_ses(
                sender=sender,
                recipient=recipient,
                subject=subject,
                message=message,
                attachment_path=attachment_path,
                region=settings.ses_region or "eu-west-1",
            )
            status = "sent"
        except Exception as exc:  # noqa: BLE001 - degradación controlada
            # No se interrumpe el flujo de resolución si SES falla: se deja
            # constancia en el log y se devuelve status="failed".
            status = "failed"
            error = str(exc)
            print(f"⚠️  [EMAIL] Fallo al enviar vía SES: {exc}")

    log_entry = {
        "notification_id": notification_id,
        "to": recipient,
        "subject": subject,
        "message": message,
        "attachment": attachment_path if attachment_path else None,
        "status": status,
        "timestamp": timestamp,
    }
    if message_id:
        log_entry["message_id"] = message_id
    if error:
        log_entry["error"] = error

    log_file = LABELS_DIR / "notifications_log.jsonl"

    # Modo "a" (append) + ensure_ascii=False para preservar tildes/ñ legibles
    # en vez de escaparlas como \uXXXX; una línea JSON por notificación (JSONL).
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    if status == "sent":
        print(f"📧 [SES] Email sent to {recipient} (message_id={message_id})")
    elif status == "sent_simulated":
        print(f"📧 [SIMULATED] Email sent to {recipient}")
    print(f"   Subject: {subject}")
    print(f"   Attachment: {attachment_path or 'None'}")

    result = {
        "notification_id": notification_id,
        "status": status,
        "to": recipient,
        "subject": subject,
        "timestamp": timestamp,
    }
    if message_id:
        result["message_id"] = message_id
    if error:
        result["error"] = error
    if status == "sent_simulated":
        result["note"] = (
            "Email sending is simulated (SES_SENDER_EMAIL no configurado). "
            "Configúralo para enviar correos reales vía AWS SES."
        )
    return result


def _send_via_ses(
    *,
    sender: str,
    recipient: str,
    subject: str,
    message: str,
    attachment_path: str,
    region: str,
) -> str | None:
    """Envía un correo con el PDF adjunto usando AWS SES.

    Returns:
        El ``MessageId`` devuelto por SES (o ``None`` si no lo incluye).

    Raises:
        Exception: Cualquier error de boto3/SES se propaga para que el
            llamador lo registre como ``status="failed"``.
    """
    import boto3  # import perezoso: boto3 solo hace falta si SES está activo

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(message)

    attachment = Path(attachment_path) if attachment_path else None
    if attachment and attachment.is_file():
        msg.add_attachment(
            attachment.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=attachment.name,
        )

    client = boto3.client("ses", region_name=region)
    response = client.send_raw_email(
        Source=sender,
        Destinations=[recipient],
        RawMessage={"Data": msg.as_bytes()},
    )
    return response.get("MessageId")
