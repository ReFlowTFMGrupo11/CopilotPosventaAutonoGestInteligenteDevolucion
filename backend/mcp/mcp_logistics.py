"""
MCP Server: Logística

Tools:
- generate_shipping_label: Genera un PDF simulado de etiqueta de transporte.
- send_customer_notification: Simula envío de correo electrónico transaccional.
"""

# os: importado por compatibilidad con el resto del módulo (no se usa
# directamente, pathlib.Path cubre el manejo de rutas).
import os
import sys
import uuid
from datetime import datetime
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
# BaseModel/Field: tipan `items` de generate_shipping_label (ver
# ShippingLabelItem mas abajo) para que el JSON Schema de la tool tenga
# forma fija (mismo motivo que ReturnItem en mcp_supabase.py).
from pydantic import BaseModel, Field

mcp = FastMCP("logistics", host="0.0.0.0", port=8002)

# __file__ = .../backend/mcp/mcp_logistics.py, así que subir 3 niveles
# (parent.parent.parent) lleva a la raíz del proyecto.
LABELS_DIR = Path(__file__).parent.parent.parent / "generated_labels"
LABELS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Tool 1: generate_shipping_label
# ---------------------------------------------------------------------------


class ShippingLabelItem(BaseModel):
    """Item mostrado en la etiqueta de transporte generada.

    Mismo motivo que ReturnItem en mcp_supabase.py: con `items: list[dict]`
    (forma libre) el modo "strict" de OpenAI (activado por LangChain al
    combinar tools + response_format, ver _resolve_model en
    agente3ConMCP/agente_resolucion.py) rechazaba la tool con un 400.
    """

    name: str = Field(default="Item", description="Nombre del producto, para la etiqueta.")
    quantity: int = Field(default=1, description="Unidades del producto.")


@mcp.tool()
async def generate_shipping_label(
    order_id: str,
    items: list[ShippingLabelItem],
    customer_name: str = "",
    customer_address: str = "",
) -> dict:
    """
    Genera un archivo PDF simulado de la etiqueta de transporte utilizando reportlab.
    Usado por Agente 3.

    Args:
        order_id: UUID del pedido asociado.
        items: Lista de items a devolver (ver ShippingLabelItem).
        customer_name: Nombre del cliente para la etiqueta.
        customer_address: Dirección del cliente.
    """
    # Imports locales: reportlab solo se carga cuando esta tool se invoca,
    # no al arrancar el servidor.
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
    # Limita a los primeros 5 items para que quepan en la etiqueta A6; los
    # valores por defecto de ShippingLabelItem cubren nombre/cantidad ausentes.
    for item in items[:5]:
        c.drawString(12 * mm, y, f"• {item.name} x{item.quantity}")
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
    import json

    # Modo "a" (append) + ensure_ascii=False para preservar tildes/ñ legibles
    # en vez de escaparlas como \uXXXX; una línea JSON por notificación (JSONL).
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
    # Igual que en mcp_supabase.py: se sirve por Streamable HTTP (no SSE,
    # deprecado) en http://0.0.0.0:8002/mcp. Host/puerto ya fijados en el
    # constructor de FastMCP (línea 21).
    mcp.run(transport="streamable-http")
