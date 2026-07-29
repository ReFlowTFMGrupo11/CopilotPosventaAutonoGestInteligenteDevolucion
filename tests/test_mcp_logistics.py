"""
Test script for MCP logistics server via SSE.
Start the server first: python -m backend.mcp.mcp_logistics
Then run this: python tests/test_mcp_logistics.py
"""

import asyncio

from mcp import ClientSession
from mcp.client.sse import sse_client

MCP_LOGISTICS_URL = "http://localhost:8002/sse"


async def test():
    async with sse_client(MCP_LOGISTICS_URL) as (read, write):
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
