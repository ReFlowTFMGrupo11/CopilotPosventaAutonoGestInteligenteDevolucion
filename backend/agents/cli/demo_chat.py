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

# override=True: si la variable ya existe en el entorno del sistema, el
# valor del .env la sobreescribe (útil para no arrastrar valores viejos
# exportados manualmente en la terminal).
load_dotenv(override=True)

import logging
# WARNING: solo se mostrarán logs de nivel warning o superior, para no
# ensuciar la consola de la demo con logs informativos de las librerías.
logging.basicConfig(level=logging.WARNING)

from backend.agents.graph import build_return_graph
from backend.agents.infra.session_tracker import start_session, record_message, end_session


async def main():
    # Fuerza UTF-8 en la salida estándar (necesario en Windows para poder
    # imprimir emojis y caracteres especiales sin UnicodeEncodeError).
    sys.stdout.reconfigure(encoding="utf-8")

    print("═" * 60)
    print("  ReFlow – Demo del grafo de devoluciones")
    print("  Escribe 'salir' para terminar")
    print("═" * 60)

    # Construye el grafo compilado (con checkpointer PostgreSQL o memoria,
    # según haya o no SUPABASE_DB_URL en el .env).
    graph = await build_return_graph()
    # thread_id: identificador único de esta conversación; el checkpointer
    # de LangGraph lo usa como clave para guardar/recuperar el estado entre
    # cada llamada a graph.ainvoke().
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Registrar inicio de sesión para métricas
    try:
        await start_session(thread_id)
    except Exception as exc:
        # Si Supabase no está disponible, la demo debe poder seguir
        # funcionando igualmente: el registro de métricas es best-effort.
        logging.warning("No se pudo registrar sesión en BD: %s", exc)

    print(f"\n[Thread: {thread_id}]\n")

    # status/customer_id se van actualizando en el bucle y se usan al
    # final (bloque finally) para cerrar la sesión con el estado correcto.
    # Valor por defecto "abandoned": si el usuario cierra la demo de forma
    # anómala (Ctrl+C, excepción) sin pasar por el "salir" explícito, la
    # sesión se registrará como abandonada en vez de completada.
    status = "abandoned"
    customer_id = None

    try:
        # Bucle principal de la demo: se repite una vez por cada turno de
        # conversación, hasta que el usuario decide salir.
        while True:
            # input() bloquea el hilo esperando que el usuario escriba y
            # pulse Enter; strip() quita espacios/saltos de línea sobrantes.
            user_input = input("Tú: ").strip()

            # Condición de salida: entrada vacía (Enter sin escribir nada)
            # o alguna de las palabras clave de salida, sin distinguir
            # mayúsculas/minúsculas gracias a .lower().
            if not user_input or user_input.lower() in ("salir", "exit", "quit"):
                status = "completed"
                print("Adiós 👋")
                break

            # Cada iteración es un "turno": se envía el mensaje del usuario
            # y el grafo se ejecuta desde "triage" hasta el primer END,
            # recuperando automáticamente el estado acumulado de turnos
            # anteriores gracias al checkpointer y al thread_id fijo.
            # - HumanMessage(content=user_input): envuelve el texto del
            #   usuario en el formato de mensaje que espera LangGraph/
            #   LangChain para añadirlo a la lista "messages" del estado.
            # - config={"configurable": {"thread_id": ...}}: le dice al
            #   checkpointer qué conversación es esta, para que cargue el
            #   historial ya guardado antes de ejecutar el grafo.
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
            )

            # Mostrar último mensaje del agente
            # El último mensaje añadido a "messages" es la respuesta del
            # agente que haya actuado en último lugar en este turno (puede
            # ser un agente distinto en cada turno, según decida "triage").
            last_msg = result["messages"][-1]
            print(f"\nReFlow: {last_msg.content}\n")

            # Registrar mensajes para métricas
            agent = result.get("current_agent", "?")
            order = result.get("order_id", "-")
            eligible = result.get("is_eligible")
            # Una vez que customer_id aparece en el estado 
            # (tras fetch_order_data),
            # se conserva para poder cerrarlo en end_session más abajo.
            customer_id = result.get("customer_id") or customer_id

            # Persiste este turno en la tabla chat_messages de Supabase (ver
            # backend/agents/infra/session_tracker.py): una fila por cada
            # lado de la conversación, ambas enlazadas al mismo thread_id
            # para poder reconstruir el chat completo más tarde con fines
            # de métricas/depuración. No afecta al comportamiento del grafo
            # en sí — es solo registro histórico en paralelo.
            try:
                # Guarda lo que escribió el cliente en este turno.
                await record_message(thread_id, "user", user_input)
                # Guarda la respuesta del agente, con metadata extra (qué
                # agente respondió y con qué order_id) para poder filtrar
                # o analizar las conversaciones por esos campos después.
                await record_message(
                    thread_id, "assistant", last_msg.content,
                    metadata={"agent": agent, "order_id": order},
                )
            except Exception as exc:
                # Nivel debug (no warning): registrar métricas es secundario,
                # no queremos alarmar al usuario de la demo por esto.
                logging.debug("No se pudo registrar mensaje: %s", exc)

            # Mostrar estado (debug)
            # Línea de depuración pensada para ver, turno a turno, cómo va
            # evolucionando el estado interno del grafo sin tener que
            # inspeccionar el objeto "result" completo.
            print(f"  [agente={agent} | order_id={order} | elegible={eligible}]")
            print()
    finally:
        # Cerrar sesión con estado final
        # Se ejecuta tanto si el bucle termina normalmente ("salir") como
        # si se interrumpe con Ctrl+C o una excepción; así la sesión
        # siempre queda cerrada en Supabase con el mejor estado disponible.
        try:
            await end_session(thread_id, status=status, customer_id=customer_id)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
