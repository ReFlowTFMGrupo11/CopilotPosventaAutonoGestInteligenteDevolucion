
"""MCP Server: Logística

Wrapper fino sobre backend.services.logistics_service.
Expone las funciones como herramientas MCP via Streamable HTTP.
"""

from dotenv import load_dotenv
load_dotenv(override=True)

import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from mcp.server.fastmcp import FastMCP

from backend.services.logistics_service import (
    generate_shipping_label as _generate_shipping_label,
    send_customer_notification as _send_customer_notification,
)

mcp = FastMCP("logistics", host="0.0.0.0", port=8002)


@mcp.tool()
async def generate_shipping_label(
    order_id: str,
    items: list[dict],
    customer_name: str = "",
    customer_address: str = "",
) -> dict:
    """Genera un archivo PDF simulado de la etiqueta de transporte.

    Args:
        order_id: UUID del pedido asociado.
        items: Lista de items a devolver [{"name": "...", "quantity": 1}].
        customer_name: Nombre del cliente para la etiqueta.
        customer_address: Dirección del cliente.
    """
    return await _generate_shipping_label(
        order_id=order_id,
        items=items,
        customer_name=customer_name,
        customer_address=customer_address,
    )


@mcp.tool()
async def send_customer_notification(
    email: str,
    message: str,
    subject: str = "ReFlow - Actualización de tu devolución",
    attachment_path: str = "",
) -> dict:
    """Simula el envío de un correo electrónico transaccional.

    Args:
        email: Dirección de correo electrónico del cliente.
        message: Cuerpo del mensaje.
        subject: Asunto del correo.
        attachment_path: Ruta al archivo adjunto (etiqueta PDF).
    """
    return await _send_customer_notification(
        email=email,
        message=message,
        subject=subject,
        attachment_path=attachment_path,
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
