"""
Test script for MCP logistics server via Streamable HTTP.
Start the server first: python -m backend.mcp.mcp_logistics
Then run this (from repo root, module mode -- a plain `python
scripts/manual_checks/check_mcp_logistics.py` fails with ModuleNotFoundError:
sys.path[0] becomes this script's own directory, not the repo root, so
`backend` isn't importable):
    python -m scripts.manual_checks.check_mcp_logistics
"""

import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# En Windows la consola usa cp1252 por defecto, que no soporta los emojis
# de los print() de este script (ver mismo fix en mcp_logistics.py).
sys.stdout.reconfigure(encoding="utf-8")

MCP_LOGISTICS_URL = "http://localhost:8002/mcp"


async def test():
    """Ejecuta un smoke test manual contra el MCP de logística en ejecución.

    No es un test de pytest (el nombre es engañoso, ver `if __name__ ==
    "__main__"` al final del fichero): conecta por Streamable HTTP a un
    servidor MCP de logística real y ejercita a mano las tools
    `generate_shipping_label` y `send_customer_notification`, imprimiendo
    sus resultados por consola en vez de hacer asserts.
    """
    async with streamablehttp_client(MCP_LOGISTICS_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List tools
            tools = await session.list_tools()
            print("🔧 Available tools:", [t.name for t in tools.tools])

            # Test generate_shipping_label
            print("\n--- Testing generate_shipping_label ---")
            result = await session.call_tool(
                "generate_shipping_label",
                arguments={
                    "order_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "items": [{"name": "Camiseta azul", "quantity": 1}],
                    "customer_name": "Juan García",
                    "customer_address": "Calle Mayor 10, Madrid",
                },
            )
            print("📦 Result:", result)

            # Test send_customer_notification
            print("\n--- Testing send_customer_notification ---")
            result2 = await session.call_tool(
                "send_customer_notification",
                arguments={
                    "email": "juan@example.com",
                    "message": "Tu etiqueta de devolución está lista.",
                    "subject": "ReFlow - Tu devolución",
                },
            )
            print("📧 Result:", result2)


if __name__ == "__main__":
    asyncio.run(test())
