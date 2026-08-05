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
from backend.agents.infra.session_tracker import start_session, record_message, end_session


async def main():
    sys.stdout.reconfigure(encoding="utf-8")

    print("═" * 60)
    print("  ReFlow – Demo del grafo de devoluciones")
    print("  Escribe 'salir' para terminar")
    print("═" * 60)

    graph = await build_return_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Registrar inicio de sesión para métricas
    try:
        await start_session(thread_id)
    except Exception as exc:
        logging.warning("No se pudo registrar sesión en BD: %s", exc)

    print(f"\n[Thread: {thread_id}]\n")

    status = "abandoned"
    customer_id = None

    try:
        while True:
            user_input = input("Tú: ").strip()
            if not user_input or user_input.lower() in ("salir", "exit", "quit"):
                status = "completed"
                print("Adiós 👋")
                break

            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
            )

            # Mostrar último mensaje del agente
            last_msg = result["messages"][-1]
            print(f"\nReFlow: {last_msg.content}\n")

            # Registrar mensajes para métricas
            agent = result.get("current_agent", "?")
            order = result.get("order_id", "-")
            eligible = result.get("is_eligible")
            customer_id = result.get("customer_id") or customer_id

            try:
                await record_message(thread_id, "user", user_input)
                await record_message(
                    thread_id, "assistant", last_msg.content,
                    metadata={"agent": agent, "order_id": order},
                )
            except Exception as exc:
                logging.debug("No se pudo registrar mensaje: %s", exc)

            # Mostrar estado (debug)
            print(f"  [agente={agent} | order_id={order} | elegible={eligible}]")
            print()
    finally:
        # Cerrar sesión con estado final
        try:
            await end_session(thread_id, status=status, customer_id=customer_id)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
