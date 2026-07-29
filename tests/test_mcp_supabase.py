"""
Test script for MCP Supabase server via SSE.
Start the server first: python -m backend.mcp.mcp_supabase
Then run this: python tests/test_mcp_supabase.py
"""

import asyncio

from mcp import ClientSession
from mcp.client.sse import sse_client

MCP_SUPABASE_URL = "http://localhost:8001/sse"


async def test():
    async with sse_client(MCP_SUPABASE_URL) as (read, write):
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
