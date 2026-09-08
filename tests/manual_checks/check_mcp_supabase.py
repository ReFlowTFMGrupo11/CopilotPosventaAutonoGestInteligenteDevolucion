"""
Test script for MCP Supabase server via Streamable HTTP.
Start the server first: python -m backend.mcp.mcp_supabase
Then run this: python tests/test_mcp_supabase.py

Requiere que la base de datos tenga al menos un cliente cargado (p. ej.
supabase/seed_synthetic.sql, ver data/README.md): este script resuelve un
customer_id válido con una consulta directa a Supabase (independiente de MCP,
solo para preparar el dato de prueba) en vez de hardcodear un UUID fijo, así
no depende de ningún fixture concreto ni se rompe si se regenera el dataset.
"""

import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from backend.db.supabase_client import get_supabase_client

# En Windows la consola usa cp1252 por defecto, que no soporta los emojis
# de los print() de este script (ver mismo fix en mcp_logistics.py).
sys.stdout.reconfigure(encoding="utf-8")

MCP_SUPABASE_URL = "http://localhost:8001/mcp"


async def _pick_any_customer_id() -> str:
    """Devuelve el id de cualquier cliente existente, para usar como fixture
    de prueba (no importa cuál, solo que exista de verdad en la BD)."""
    client = await get_supabase_client()
    resp = await client.table("customers").select("id").limit(1).execute()
    if not resp.data:
        raise RuntimeError(
            "No hay ningún cliente en la base de datos. Carga "
            "supabase/seed_synthetic.sql (o supabase/run_all.sql) antes de "
            "ejecutar este smoke test."
        )
    return resp.data[0]["id"]


async def test():
    """Ejecuta un smoke test manual contra el MCP de Supabase en ejecución.

    No es un test de pytest (el nombre es engañoso, ver `if __name__ ==
    "__main__"` al final del fichero): conecta por Streamable HTTP a un
    servidor MCP de Supabase real y ejercita a mano la tool
    `get_customer_return_history` con un customer_id real de la BD,
    imprimiendo el resultado por consola en vez de hacer asserts.
    """
    customer_id = await _pick_any_customer_id()

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
                arguments={"customer_id": customer_id},
            )
            print("📋 Result:", result)


if __name__ == "__main__":
    asyncio.run(test())
