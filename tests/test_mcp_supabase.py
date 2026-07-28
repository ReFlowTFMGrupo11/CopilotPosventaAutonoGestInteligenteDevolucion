"""
Test script for MCP Supabase server via Streamable HTTP.
Start the server first: python -m backend.mcp.mcp_supabase
Then run this: python tests/test_mcp_supabase.py
"""

# asyncio: necesario porque todo el cliente MCP es asíncrono.
import asyncio

# ClientSession: gestiona el handshake y las llamadas del protocolo MCP
# sobre un par de streams (lectura/escritura) ya abiertos por el transporte.
from mcp import ClientSession
# streamable_http_client: abre la conexión Streamable HTTP (el transporte
# vigente; sustituye a SSE, deprecado en la spec 2025-03-26 y con EOL el
# 1 de abril de 2026) y expone los streams read/write que consume
# ClientSession. (Existe también "streamablehttp_client", pero está
# marcada deprecada en favor de esta.)
from mcp.client.streamable_http import streamable_http_client

# Ruta por defecto del servidor FastMCP: "/mcp".
MCP_SUPABASE_URL = "http://localhost:8001/mcp"


async def test():
    # streamable_http_client entrega 3 valores: streams de lectura/escritura
    # y una función get_session_id (no usada aquí, de ahí el "_").
    async with streamable_http_client(MCP_SUPABASE_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            # Handshake inicial del protocolo MCP (intercambio de
            # capacidades cliente/servidor); obligatorio antes de listar o
            # llamar tools.
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
