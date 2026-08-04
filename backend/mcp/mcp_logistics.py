"""
MCP Server: Logística

Wrapper fino sobre backend/services/logistics_service.py: cada tool solo traduce
argumentos y delega en la función de servicio equivalente. Toda la lógica real
(generación del PDF, log de notificaciones) vive en services/, no aquí — ver el
docstring de logistics_service.py y doc/AUDITORIA_RAMAS.md (punto 6) para el porqué
de esta separación.

Tools:
- generate_shipping_label: Genera un PDF simulado de etiqueta de transporte.
- send_customer_notification: Simula envío de correo electrónico transaccional.
"""

import sys

# En Windows, la consola por defecto usa el codepage cp1252 (no UTF-8), que
# no puede representar los emojis usados en los print() de logistics_service.py.
# Sin esto, send_customer_notification lanza UnicodeEncodeError en el propio
# proceso servidor en cuanto intenta loguear el correo simulado.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# FastMCP: clase del SDK oficial "mcp" (paquete PyPI "mcp", serie 1.x; ver
# el comentario equivalente en mcp_supabase.py sobre por qué 1.x y no 2.x).
from mcp.server.fastmcp import FastMCP
# BaseModel/Field: tipan `items` de generate_shipping_label (ver
# ShippingLabelItem mas abajo) para que el JSON Schema de la tool tenga
# forma fija (mismo motivo que ReturnItem en mcp_supabase.py). Frontera
# propia de MCP: logistics_service.py se queda con `items: list[dict]`.
from pydantic import BaseModel, Field

from backend.services import logistics_service

mcp = FastMCP("logistics", host="0.0.0.0", port=8002)


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
    return await logistics_service.generate_shipping_label(
        order_id=order_id,
        items=[item.model_dump() for item in items],
        customer_name=customer_name,
        customer_address=customer_address,
    )


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
    return await logistics_service.send_customer_notification(
        email=email,
        message=message,
        subject=subject,
        attachment_path=attachment_path,
    )


# ---------------------------------------------------------------------------
# Run server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Igual que en mcp_supabase.py: se sirve por Streamable HTTP (no SSE,
    # deprecado) en http://0.0.0.0:8002/mcp. Host/puerto ya fijados en el
    # constructor de FastMCP.
    mcp.run(transport="streamable-http")
