"""
Agente 3: Resolucion y Logistica (LangChain + MCP)

Ultimo eslabon del flujo de devoluciones descrito en doc/guia.md (Epica 2,
US 2.4 y US 2.5). Recibe un caso que el Agente 2 (Evaluador) ya ha validado
como elegible y, si el importe no supera el umbral de aprobacion automatica,
lo ejecuta: registra la devolucion, genera la etiqueta de transporte y
notifica al cliente. Usa tres tools MCP repartidas en dos servidores:
- create_return_record (servidor mcp_supabase.py, puerto 8001).
- generate_shipping_label y send_customer_notification (servidor
  mcp_logistics.py, puerto 8002).

Regla de Human-in-the-Loop (HITL): si refund_amount > HITL_THRESHOLD_EUR
(100 EUR por defecto), el agente NO ejecuta ninguna tool. Esta comprobacion
se hace en Python, no se delega en el LLM: es una regla de negocio sobre
dinero y no queremos depender de que el modelo la respete en todas las
formulaciones posibles del caso.

Requiere los dos servidores MCP levantados:
    python -m backend.mcp.mcp_supabase
    python -m backend.mcp.mcp_logistics
"""

# os: para leer configuracion (URLs de los MCP, modelo, umbral HITL) desde
# variables de entorno.
import os
# Any: tipo del agente compilado por langgraph.
# Optional: parametros que pueden omitirse (None) en las firmas.
from typing import Any, Optional

# load_dotenv: lee el fichero .env de la raiz del proyecto y vuelca sus
# claves en os.environ, igual que en agente1ConMCP/agente_triaje.py.
from dotenv import load_dotenv
# create_agent: fabrica de LangChain 1.x que construye un agente (grafo de
# langgraph) con bucle modelo -> tools -> modelo hasta obtener respuesta final.
from langchain.agents import create_agent
# BaseChatModel: tipo comun de "modelo ya construido" que create_agent acepta
# ademas de un string "<provider>:<model>" (ver _resolve_model mas abajo).
from langchain_core.language_models import BaseChatModel
# Cliente que habla el protocolo MCP y expone las tools de varios servidores
# MCP a la vez como BaseTool de LangChain.
from langchain_mcp_adapters.client import MultiServerMCPClient
# ChatOpenAI: lo construimos "a mano" en vez de dejar que create_agent
# resuelva el string "openai:..." el solo (ver _resolve_model), igual que
# en agente2ConMCP/agente_evaluacion.py.
from langchain_openai import ChatOpenAI
# BaseModel/Field: definen los esquemas de entrada (ResolutionRequest) y de
# salida estructurada (ResolutionOutput) del agente.
from pydantic import BaseModel, Field

# Busca el .env subiendo desde este fichero (agente3ConMCP/ -> raiz del
# repo) y carga sus claves en os.environ.
load_dotenv()

# URLs de los servidores MCP (ver README.md raiz). Configurables por env var
# para poder apuntar a otro host/puerto sin tocar codigo.
MCP_SUPABASE_URL = os.getenv("MCP_SUPABASE_URL", "http://localhost:8001/mcp")
MCP_LOGISTICS_URL = os.getenv("MCP_LOGISTICS_URL", "http://localhost:8002/mcp")

# Modelo por defecto en formato "<provider>:<model>" que acepta create_agent
# directamente (ver requirements.txt: openai / langchain-openai).
DEFAULT_MODEL = os.getenv("AGENTE3_MODEL", "openai:gpt-4o-mini")

# Umbral de aprobacion automatica en euros (doc/guia.md, 100 euros): por
# encima de este importe el caso se deriva a un administrador en vez de
# ejecutarse automaticamente.
HITL_THRESHOLD_EUR = float(os.getenv("HITL_THRESHOLD_EUR", "100"))

# El Agente 3 solo necesita estas tres tools (una de mcp_supabase.py y dos
# de mcp_logistics.py); el resto de tools de esos servidores (historial,
# RAG de politicas, get_order_details, update_return_status) pertenecen a
# los Agentes 1, 2 y al panel de Admin/HITL.
RESOLUTION_TOOL_NAMES = {
    "create_return_record",
    "generate_shipping_label",
    "send_customer_notification",
}

# Prompt de sistema: solo se usa en el camino de aprobacion automatica (el
# camino HITL nunca invoca al LLM, ver run_agent_resolucion). Fija el orden
# exacto de llamadas a tools y prohibe inventar datos que deban venir de
# las herramientas (IDs, tracking numbers, rutas de fichero).
SYSTEM_PROMPT = """\
Eres el Agente de Resolucion y Logistica de ReFlow. Recibes una devolucion \
que el Agente Evaluador ya ha validado como elegible y cuyo importe esta \
dentro del limite de aprobacion automatica: tu trabajo es EJECUTARLA, no \
volver a decidir si es elegible.

Se te entrega un resumen del caso (pedido, cliente, motivo, importe y \
productos). Debes, en este orden:
1. Llamar a create_return_record para registrar la devolucion en Supabase.
2. Llamar a generate_shipping_label con el order_id y los productos para \
generar la etiqueta de transporte.
3. Llamar a send_customer_notification con el email del cliente, un \
mensaje claro sobre la devolucion aprobada y la ruta del PDF generado \
(label_path) como adjunto.
4. Redactar en response_to_customer la confirmacion final para el cliente, \
mencionando el numero de seguimiento (tracking_number).

No inventes IDs, tracking numbers ni rutas de fichero: usa unicamente lo \
que devuelvan las herramientas. Si una herramienta falla o devuelve un \
error, no sigas con los pasos siguientes y explica el problema en \
response_to_customer.
"""


class ResolutionRequest(BaseModel):
    """Caso de devolucion ya evaluado como elegible por el Agente 2, listo para resolverse."""

    order_id: str = Field(description="UUID del pedido, ya verificado por los Agentes 1 y 2.")
    customer_id: str = Field(description="UUID del cliente.")
    customer_email: str = Field(description="Email del cliente para la notificacion final.")
    reason: str = Field(description="Motivo de la devolucion en palabras del cliente.")
    reason_category: str = Field(
        description="defective, wrong_item, no_longer_needed, changed_mind u other."
    )
    refund_amount: float = Field(description="Importe a reembolsar, en euros.")
    products: list[dict] = Field(
        default_factory=list,
        description=(
            "Productos a devolver. Se envian tal cual como el parametro "
            "`items` de create_return_record "
            "([{'order_item_id', 'quantity', 'condition'}]) y de "
            "generate_shipping_label ([{'name', 'quantity'}])."
        ),
    )
    customer_name: str = Field(default="", description="Nombre del cliente, para la etiqueta.")
    customer_address: str = Field(default="", description="Direccion del cliente, para la etiqueta.")
    notes: str = Field(default="", description="Notas adicionales opcionales para el registro.")


class ResolutionOutput(BaseModel):
    """Salida estructurada del Agente de Resolucion."""

    # None si el caso quedo pendiente de aprobacion (no se llego a crear).
    return_id: Optional[str] = Field(
        default=None, description="ID de la devolucion creada con create_return_record."
    )
    # None si el caso quedo pendiente de aprobacion (no se genero etiqueta).
    tracking_number: Optional[str] = Field(
        default=None, description="Numero de seguimiento devuelto por generate_shipping_label."
    )
    label_path: Optional[str] = Field(
        default=None, description="Ruta local del PDF de la etiqueta generada."
    )
    # true = el importe superaba HITL_THRESHOLD_EUR, así que no se ha creado
    # ninguna devolución ni etiqueta: el caso se queda esperando a que un
    # administrador lo apruebe manualmente desde el panel de Admin/HITL.
    # false = ya se ha ejecutado todo (return_id/tracking_number/label_path
    # vienen rellenos) y no hace falta ninguna acción humana.
    requires_human_approval: bool = Field(
        default=False,
        description="True si el importe supera HITL_THRESHOLD_EUR y el caso se derivo a un administrador.",
    )
    # Se recalcula siempre a partir de ResolutionRequest.refund_amount (ver
    # run_agent_resolucion), nunca se confia en lo que "recuerde" el LLM.
    refund_amount: float = Field(description="Importe a reembolsar, en euros.")
    response_to_customer: str = Field(
        description="Mensaje final a mostrar al cliente en este turno."
    )


def _get_mcp_client(
    mcp_supabase_url: str = MCP_SUPABASE_URL,
    mcp_logistics_url: str = MCP_LOGISTICS_URL,
) -> MultiServerMCPClient:
    # Un unico cliente con los dos servidores registrados bajo un nombre
    # logico cada uno; get_tools() sin server_name trae las tools de ambos
    # en una sola lista.
    return MultiServerMCPClient(
        {
            "supabase": {
                "url": mcp_supabase_url,
                "transport": "streamable_http",
            },
            "logistics": {
                "url": mcp_logistics_url,
                "transport": "streamable_http",
            },
        }
    )


async def get_resolution_tools(
    mcp_supabase_url: str = MCP_SUPABASE_URL,
    mcp_logistics_url: str = MCP_LOGISTICS_URL,
) -> list:
    """Obtiene de ambos servidores MCP solo las tools que necesita el Agente 3."""
    # 1. Creamos el cliente que sabe hablar con los dos servidores MCP
    #    (supabase y logistics) a la vez.
    client = _get_mcp_client(mcp_supabase_url, mcp_logistics_url)

    # 2. Le pedimos TODAS las tools que ofrecen esos dos servidores. Como no
    #    le decimos server_name, va a preguntar a los dos (no solo a uno) y
    #    nos devuelve una única lista con las tools de ambos mezcladas.
    #    Aqui salen tools que el Agente 3 NO deberia usar, como
    #    get_order_details o update_return_status.
    tools = await client.get_tools()

    # 3. Nos quedamos solo con las 3 tools que el Agente 3 tiene permitido
    #    usar (RESOLUTION_TOOL_NAMES). Es una medida de seguridad: aunque el
    #    servidor ofrezca mas herramientas, este agente no debe poder
    #    tocarlas (por ejemplo, no debe poder cambiar el estado de una
    #    devolucion el mismo, eso es cosa del panel de Admin/HITL).
    return [tool for tool in tools if tool.name in RESOLUTION_TOOL_NAMES]


def _resolve_model(model: str | BaseChatModel) -> str | BaseChatModel:
    """Convierte "openai:<modelo>" en un ChatOpenAI normal (Chat Completions).

    Bug real que motivaba antes forzar use_responses_api=True: al llamar a
    create_agent(..., tools=[...], response_format=ResolutionOutput) con un
    modelo OpenAI normal, LangChain activa automaticamente el modo "strict"
    para TODAS las tools (ver langchain/agents/factory.py), que valida el
    JSON Schema de cada tool de forma muy exigente. create_return_record y
    generate_shipping_label tenian un parametro `items: list[dict]` (lista
    de diccionarios "libres", sin forma fija) que no pasaba esa validacion:

        openai.BadRequestError: Invalid schema for function
        'create_return_record': ... Extra required key 'items' supplied.

    Desde que `items` esta tipado (ver ReturnItem en
    backend/mcp/mcp_supabase.py y ShippingLabelItem en
    backend/mcp/mcp_logistics.py), el schema completo es compatible con el
    modo strict normal y ya no hace falta forzar la API de Responses (mismo
    motivo por el que agente2ConMCP.agente_evaluacion._resolve_model tampoco
    la necesita desde que Product esta tipado).

    Si `model` no es un string "openai:...", se devuelve tal cual (por
    ejemplo si ya nos pasan un BaseChatModel construido, o un modelo de
    otro proveedor).
    """
    if isinstance(model, str) and model.startswith("openai:"):
        model_name = model.removeprefix("openai:")
        return ChatOpenAI(model=model_name)
    return model


async def build_resolution_agent(
    model: str | BaseChatModel = DEFAULT_MODEL,
    mcp_supabase_url: str = MCP_SUPABASE_URL,
    mcp_logistics_url: str = MCP_LOGISTICS_URL,
    tools: Optional[list] = None,
) -> Any:
    """Construye el agente de resolucion (langgraph) con las tools de create_return_record,
    generate_shipping_label y send_customer_notification.

    `tools` permite inyectar tools ya resueltas (por ejemplo en tests) sin
    tener que conectar a servidores MCP reales.
    """
    resolved_tools = (
        tools
        if tools is not None
        else await get_resolution_tools(mcp_supabase_url, mcp_logistics_url)
    )
    return create_agent(
        model=_resolve_model(model),
        tools=resolved_tools,
        system_prompt=SYSTEM_PROMPT,
        response_format=ResolutionOutput,
    )


def _needs_human_approval(refund_amount: float) -> bool:
    """Regla HITL determinista (doc/guia.md, US 2.5): nunca delegada al LLM."""
    return refund_amount > HITL_THRESHOLD_EUR


def _pending_approval_output(request: ResolutionRequest) -> ResolutionOutput:
    """Salida para un caso derivado a un administrador: no se ha ejecutado nada."""
    return ResolutionOutput(
        requires_human_approval=True,
        refund_amount=request.refund_amount,
        response_to_customer=(
            f"Tu devolucion de {request.refund_amount:.2f}€ supera el "
            f"limite de aprobacion automatica ({HITL_THRESHOLD_EUR:.2f}€) "
            "y ha sido derivada a un administrador para su revision manual."
        ),
    )


def _get_resolution_request_with_format(request: ResolutionRequest) -> str:
    # Esta funcion solo convierte el ResolutionRequest (un objeto Python) en
    # un texto que se le manda al LLM como si fuera un mensaje de chat.
    #
    # Usamos texto plano con lineas "- campo: valor" en vez de JSON por dos
    # motivos:
    #   1. El LLM no necesita "parsear" el mensaje con codigo, solo leerlo,
    #      igual que leeria un email.
    #   2. Es mas facil de leer para una persona si en el futuro revisamos
    #      los logs/trazas de LangSmith (ver doc/guia.md, US 5.1).
    return (
        "Caso de devolucion aprobado por el Agente Evaluador. Ejecuta la resolucion:\n"
        f"- order_id: {request.order_id}\n"
        f"- customer_id: {request.customer_id}\n"
        f"- customer_email: {request.customer_email}\n"
        f"- customer_name: {request.customer_name}\n"
        f"- customer_address: {request.customer_address}\n"
        f"- reason: {request.reason}\n"
        f"- reason_category: {request.reason_category}\n"
        f"- refund_amount: {request.refund_amount}\n"
        f"- productos: {request.products}\n"
        f"- notes: {request.notes}\n"
    )


async def run_agent_resolucion(
    request: ResolutionRequest,
    *,
    agent: Optional[Any] = None,
    model: str = DEFAULT_MODEL,
    mcp_supabase_url: str = MCP_SUPABASE_URL,
    mcp_logistics_url: str = MCP_LOGISTICS_URL,
) -> ResolutionOutput:
    """Resuelve un caso ya evaluado como elegible por el Agente 2.

    Args:
        request: Caso a resolver (pedido, cliente, motivo, importe, productos).
        agent: Agente ya construido (permite reutilizarlo entre casos o
            inyectar un doble de prueba en tests). Si no se pasa, se
            construye uno nuevo conectando a los servidores MCP.
        model: Modelo a usar si hay que construir el agente.
        mcp_supabase_url: URL del servidor MCP de datos si hay que construir el agente.
        mcp_logistics_url: URL del servidor MCP de logistica si hay que construir el agente.
    """
    # 1. Regla de negocio primero, sin pasar por el LLM: si el importe es
    #    demasiado alto, no se ejecuta nada (ni tools ni modelo) y se
    #    devuelve directamente el caso como "pendiente de aprobacion".
    if _needs_human_approval(request.refund_amount):
        return _pending_approval_output(request)

    # 2. Si no nos han dado un agente ya construido (por ejemplo en los
    #    tests, con un doble de prueba), creamos uno nuevo conectando a
    #    los dos servidores MCP.
    resolved_agent = agent
    if resolved_agent is None:
        resolved_agent = await build_resolution_agent(
            model=model,
            mcp_supabase_url=mcp_supabase_url,
            mcp_logistics_url=mcp_logistics_url,
        )

    # 3. El agente solo entiende mensajes de chat, no objetos Python. Por
    #    eso convertimos el caso de devolucion en un texto (con todos sus
    #    datos: pedido, cliente, importe...) y se lo mandamos como si fuera
    #    el primer mensaje que escribe un usuario. A partir de ahi es el
    #    propio agente quien decide, siguiendo el SYSTEM_PROMPT, en que
    #    orden llamar a las tools.
    return_case_summary = _get_resolution_request_with_format(request)
    result = await resolved_agent.ainvoke({"messages": [{"role": "user", "content": return_case_summary}]})
    output = result["structured_response"]

    # 4. El LLM devuelve su propia version de "output", pero hay dos campos
    #    que NO nos podemos fiar de que haya rellenado bien, asi que los
    #    pisamos nosotros con el valor correcto:
    #
    #    - output.refund_amount: el LLM podria escribir un numero distinto
    #      al real (por ejemplo si se "olvida" un decimal). Para evitarlo,
    #      ignoramos lo que haya puesto y ponemos siempre el importe que
    #      nos llego en la peticion original (request.refund_amount).
    #
    #    - output.requires_human_approval: el LLM podria marcarlo como
    #      True por error. No pasa nada si lo hace: lo forzamos a False
    #      porque, si de verdad hiciera falta aprobacion humana, el codigo
    #      ya habria terminado en el paso 1 (antes de llegar aqui).
    output.refund_amount = request.refund_amount
    output.requires_human_approval = False
    return output


if __name__ == "__main__":
    import asyncio
    import sys

    # En Windows la consola usa cp1252 por defecto, que no soporta los
    # acentos/euros de la respuesta del LLM (mismo fix que
    # agente1ConMCP/agente_triaje.py y tests/test_mcp_supabase.py).
    sys.stdout.reconfigure(encoding="utf-8")

    async def _demo() -> None:
        # ATENCION: a diferencia del demo de solo lectura del Agente 1,
        # este demo con un importe <= HITL_THRESHOLD_EUR ejecuta las tools
        # de verdad: crea un registro real en return_requests (Supabase),
        # un PDF en generated_labels/ y una linea en
        # generated_labels/notifications_log.jsonl.
        #
        # Caso real de supabase/seed.sql: pedido ORD-2026-00163 de Laura
        # Fernandez, devolviendo el libro "Clean Code" (34.99 EUR, bajo el
        # umbral HITL por defecto de 100 EUR).
        request = ResolutionRequest(
            order_id="e1f2a3b4-c5d6-7890-efab-901234567890",
            customer_id="c3d4e5f6-a7b8-9012-cdef-123456789012",
            customer_email="laura.fernandez@email.com",
            customer_name="Laura Fernandez Soto",
            customer_address="Calle Sierpes 15, Sevilla",
            reason="No era lo que esperaba",
            reason_category="changed_mind",
            refund_amount=34.99,
            products=[
                {
                    "order_item_id": "d6e7f8a9-b0c1-2345-defa-456789012345",
                    "quantity": 1,
                    "condition": "unopened",
                    "name": "Clean Code (Edicion Espanol)",
                }
            ],
        )
        output = await run_agent_resolucion(request)
        print(output.model_dump())

    asyncio.run(_demo())
