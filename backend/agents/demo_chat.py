"""
Demo interactiva del grafo de devoluciones.

Ejecutar:
    python -m backend.agents.demo_chat

Requiere:
    - .env con SUPABASE_DB_URL y OPENAI_API_KEY
    - Servidores MCP levantados (mcp_supabase en puerto 8001)
"""

import asyncio
import sys
import uuid

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

load_dotenv(override=True)

import logging
logging.basicConfig(level=logging.WARNING)

from backend.agents.graph import build_return_graph


async def main():
    sys.stdout.reconfigure(encoding="utf-8")

    print("═" * 60)
    print("  ReFlow – Demo del grafo de devoluciones")
    print("  Escribe 'salir' para terminar")
    print("═" * 60)

    graph = await build_return_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print(f"\n[Thread: {thread_id}]\n")

    while True:
        user_input = input("Tú: ").strip()
        if not user_input or user_input.lower() in ("salir", "exit", "quit"):
            print("Adiós 👋")
            break

        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config,
        )

        # Mostrar último mensaje del agente
        last_msg = result["messages"][-1]
        print(f"\nReFlow: {last_msg.content}\n")

        # Mostrar estado (debug)
        agent = result.get("current_agent", "?")
        order = result.get("order_id", "-")
        eligible = result.get("is_eligible")
        print(f"  [agente={agent} | order_id={order} | elegible={eligible}]")
        print()


if __name__ == "__main__":
    asyncio.run(main())
