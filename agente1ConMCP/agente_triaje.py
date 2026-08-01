"""
Agente 1: Triaje y Empatia (LangChain + MCP)

Primer punto de contacto del flujo de devoluciones descrito en doc/guia.md
(Epica 2, US 2.2). Atiende al cliente, entiende el motivo de su
insatisfaccion y extrae el order_id de forma conversacional. Usa la tool
MCP `get_order_details`, expuesta por el servidor `backend/mcp/mcp_supabase.py`,
para verificar que el pedido existe antes de marcarlo listo para el
Agente 2 (Evaluador de Politicas).

Requiere el servidor MCP de Supabase levantado:
    python -m backend.mcp.mcp_supabase
"""

# os: para leer configuracion (URL del MCP y modelo) desde variables de entorno.
import os
# Any: tipo del agente compilado por langgraph (create_agent no expone una clase publica simple).
# Optional: parametros que pueden omitirse (None) en las firmas de las funciones.
from typing import Any, Optional

# load_dotenv: lee el fichero .env de la raiz del proyecto y vuelca sus
# claves en os.environ, para que os.getenv() las encuentre igual que si
# fueran variables de entorno reales del sistema.
from dotenv import load_dotenv
# create_agent: fabrica de LangChain 1.x que construye un agente (grafo de
# langgraph) con bucle modelo -> tools -> modelo hasta obtener respuesta final.
from langchain.agents import create_agent
# Cliente que habla el protocolo MCP y expone las tools de un servidor MCP
# como BaseTool de LangChain, listas para pasarle a create_agent.
from langchain_mcp_adapters.client import MultiServerMCPClient  # ultima version de mcp-adapter (0.1.3) requiere importacion de MultiServerMCPClient, no de MCPClient
# BaseModel/Field: definen el esquema de salida estructurada (TriageOutput)
# que el LLM debe rellenar en su respuesta final.
from pydantic import BaseModel, Field

# Busca el .env subiendo desde este fichero (agente1ConMCP/ -> raiz del
# repo) y carga sus claves en os.environ. No sobreescribe variables que ya
# existan en el entorno (por ejemplo las que ponga el propio despliegue).
load_dotenv()

# URL del servidor MCP de datos y politicas (puerto 8001, ver README.md).
# Configurable via MCP_SUPABASE_URL en .env para apuntar a otro host/puerto
# sin tocar codigo.
MCP_SUPABASE_URL = os.getenv("MCP_SUPABASE_URL", "http://localhost:8001/mcp")

# Modelo por defecto en formato "<provider>:<model>" que acepta create_agent
# directamente (ver requirements.txt: openai / langchain-openai).
# create_agent resuelve este string internamente a un BaseChatModel concreto.
# Configurable via AGENTE1_MODEL en .env.
DEFAULT_MODEL = os.getenv("AGENTE1_MODEL", "openai:gpt-4o-mini")

# El Agente 1 solo necesita confirmar que el pedido existe; el resto de
# tools de mcp_supabase.py (historial, RAG de politicas, creacion de
# devoluciones) pertenecen a los Agentes 2 y 3.
# Set (no list) porque solo se usa para comprobar pertenencia (`in`).
TRIAGE_TOOL_NAMES = {"get_order_details"}

# Prompt de sistema: fija el rol, el orden de pasos a seguir en la
# conversacion y los limites de responsabilidad del agente (no evalua
# elegibilidad, eso es cosa del Agente 2). El "\" al final de cada linea
# evita que las saltos de linea del triple-quote se cuelen en el prompt.
SYSTEM_PROMPT = """\
Eres el Agente de Triaje y Empatia de ReFlow, el copiloto de posventa de una \
tienda online. Eres el primer punto de contacto cuando un cliente quiere \
devolver un pedido.

Tu trabajo:
1. Saluda con calidez y reconoce la molestia del cliente.
2. Averigua el order_id del pedido que quiere devolver. Pideselo si no lo \
menciona.
3. En cuanto tengas un order_id, llama a la herramienta get_order_details \
para confirmar que el pedido existe. No inventes datos del pedido: usa \
solo lo que devuelva la herramienta.
4. Averigua el motivo de la devolucion en palabras del cliente y \
clasificalo en una categoria (defective, wrong_item, no_longer_needed, \
changed_mind, other).
5. No decidas si la devolucion es elegible ni menciones plazos o \
politicas: esa validacion la hace el Agente Evaluador, no tu.
6. Marca ready_for_evaluation=true unicamente cuando el order_id haya sido \
verificado con la herramienta y el motivo este claro. En caso contrario \
mantenlo en false y pide en response_to_customer la informacion que falte.
"""


class TriageOutput(BaseModel):
    """Salida estructurada del Agente de Triaje, lista para pasar al Agente Evaluador."""

    # None mientras el cliente no ha dado el order_id o get_order_details
    # todavia no lo ha confirmado.
    order_id: Optional[str] = Field(
        default=None,
        description="UUID del pedido, verificado con get_order_details. None si aun no se conoce.",
    )
    # Texto libre tal cual lo cuenta el cliente (no normalizado).
    reason: Optional[str] = Field(
        default=None, description="Motivo de la devolucion en palabras del cliente."
    )
    # Clasificacion cerrada del motivo, para que el Agente 2 pueda razonar
    # sobre categorias sin tener que interpretar texto libre.
    reason_category: Optional[str] = Field(
        default=None,
        description="defective, wrong_item, no_longer_needed, changed_mind u other.",
    )
    # Flag de "handoff": solo pasa a true cuando hay order_id verificado y
    # motivo claro; es la senal que usaria un orquestador para invocar al
    # Agente 2.
    ready_for_evaluation: bool = Field(
        default=False,
        description="True si order_id fue verificado y el motivo esta claro.",
    )
    # Unico campo obligatorio: siempre hay que responder algo al cliente,
    # aunque sea para pedirle mas informacion.
    response_to_customer: str = Field(
        description="Respuesta empatica a mostrar al cliente en este turno."
    )


def _get_mcp_client(mcp_url: str = MCP_SUPABASE_URL) -> MultiServerMCPClient:
    # Se crea un cliente nuevo en cada llamada (no es un singleton): abrir
    # una conexion HTTP streamable es barato y evita mantener estado global
    # que complicaria los tests. "supabase" es el nombre logico del
    # servidor dentro del dict de conexiones (puede haber varios servidores
    # MCP registrados en un mismo cliente).
    return MultiServerMCPClient(
        {
            "supabase": {
                "url": mcp_url,
                "transport": "streamable_http",
            }
        }
    )


async def get_triage_tools(mcp_url: str = MCP_SUPABASE_URL) -> list:
    """Obtiene del servidor MCP solo las tools que necesita el Agente 1."""
    client = _get_mcp_client(mcp_url)
    # get_tools hace el handshake MCP (initialize + list_tools) y devuelve
    # TODAS las tools del servidor "supabase" (get_order_details,
    # create_return_record, etc.) ya envueltas como BaseTool de LangChain.
    tools = await client.get_tools(server_name="supabase")
    # Principio de menor privilegio: el Agente 1 solo debe poder llamar a
    # get_order_details, aunque el servidor MCP exponga mas herramientas.
    return [tool for tool in tools if tool.name in TRIAGE_TOOL_NAMES]


async def build_triage_agent(
    model: str = DEFAULT_MODEL,
    mcp_url: str = MCP_SUPABASE_URL,
    tools: Optional[list] = None,
) -> Any:
    """Construye el agente de triaje (langgraph) con la tool MCP get_order_details.

    `tools` permite inyectar tools ya resueltas (por ejemplo en tests) sin
    tener que conectar a un servidor MCP real.
    """
    # Si el llamante ya paso una lista de tools (tests, u otro caller que
    # las cachea), se usa tal cual y no se toca la red; si no, se resuelven
    # ahora mismo contra el servidor MCP.
    resolved_tools = tools if tools is not None else await get_triage_tools(mcp_url)
    # create_agent monta el grafo langgraph: nodo modelo -> (si hay tool
    # calls) nodo tools -> vuelta al modelo, hasta que responda con
    # response_format relleno (TriageOutput) en vez de una tool call.
    return create_agent(
        model=model,
        tools=resolved_tools,
        system_prompt=SYSTEM_PROMPT,
        response_format=TriageOutput,
    )


async def run_agent_triaje(
    message: str,
    history: Optional[list[dict]] = None,
    *,
    agent: Optional[Any] = None,
    model: str = DEFAULT_MODEL,
    mcp_url: str = MCP_SUPABASE_URL,
) -> TriageOutput:
    """Ejecuta un turno de conversacion del Agente de Triaje.

    Args:
        message: Ultimo mensaje del cliente.
        history: Mensajes previos de la conversacion (formato {"role", "content"}).
        agent: Agente ya construido (permite reutilizarlo entre turnos o
            inyectar un doble de prueba en tests). Si no se pasa, se
            construye uno nuevo conectando al servidor MCP.
        model: Modelo a usar si hay que construir el agente.
        mcp_url: URL del servidor MCP si hay que construir el agente.
    """
    # Reutiliza el agente recibido (mismo grafo/tools entre turnos, o doble
    # de test) o construye uno nuevo solo si hace falta.
    resolved_agent = agent if agent is not None else await build_triage_agent(model=model, mcp_url=mcp_url)
    # El estado de entrada de un agente langgraph es {"messages": [...]}:
    # se reconstruye el historial completo + el mensaje nuevo del cliente
    # en cada turno (no hay memoria implicita entre llamadas a ainvoke).
    messages = [*(history or []), {"role": "user", "content": message}]
    # ainvoke ejecuta el grafo de principio a fin (incluye las posibles
    # llamadas a get_order_details) y devuelve el estado final.
    result = await resolved_agent.ainvoke({"messages": messages})
    # "structured_response" es la clave que create_agent añade al estado
    # cuando se configura response_format: ahi va la instancia TriageOutput.
    return result["structured_response"]


# Bloque de demo manual: solo se ejecuta con `python -m agente1ConMCP.agente_triaje`,
# nunca al importar el modulo (por ejemplo desde los tests).
if __name__ == "__main__":
    import asyncio
    import sys

    # En Windows la consola usa cp1252 por defecto y rompe los acentos de
    # la respuesta del LLM (mismo fix que tests/test_mcp_supabase.py).
    sys.stdout.reconfigure(encoding="utf-8")

    async def _demo() -> None:
        # order_id real de supabase/seed.sql (ORD-2026-00142, pedido de
        # Maria Garcia). Requiere el servidor MCP levantado
        # (python -m backend.mcp.mcp_supabase) y OPENAI_API_KEY configurada.
        output = await run_agent_triaje(
            "Hola, quiero devolver mi pedido "
            "c9d0e1f2-a3b4-5678-cdef-789012345678, llego roto"
        )
        print(output.model_dump())

    asyncio.run(_demo())
