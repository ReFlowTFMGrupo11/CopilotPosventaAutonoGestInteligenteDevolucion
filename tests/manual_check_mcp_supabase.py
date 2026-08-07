"""
Manual check script for MCP Supabase server via Streamable HTTP.
Not a pytest test (needs a live server) — run it directly:
Start the server first: python -m backend.mcp.mcp_supabase
Then run this: python tests/manual_check_mcp_supabase.py
"""

import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# En Windows la consola usa cp1252 por defecto, que no soporta los emojis
# de los print() de este script (ver mismo fix en mcp_logistics.py).
sys.stdout.reconfigure(encoding="utf-8")

MCP_SUPABASE_URL = "http://localhost:8001/mcp"


async def test():
    async with streamablehttp_client(MCP_SUPABASE_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List tools
            tools = await session.list_tools()
            print("🔧 Available tools:", [t.name for t in tools.tools])

            # Test get_customer_return_history
            print("\n--- Testing get_customer_return_history ---")
            result = await session.call_tool(
                "get_customer_return_history",
                arguments={
                    "customer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                },
            )
            print("📋 Result:", result)


if __name__ == "__main__":
    asyncio.run(test())
