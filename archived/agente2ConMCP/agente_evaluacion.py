"""
Agente 2: Evaluador de Politicas (LangChain + MCP)

Que hace: es el "auditor" del flujo de devoluciones (doc/guia.md, Epica 2,
US 2.3). Recibe de Agente 1 (Triaje) los datos basicos del caso (order_id,
reason, reason_category) y decide si la devolucion se:
- aprueba sola      -> "valid"
- rechaza sola      -> "invalid"
- manda a una persona -> "human_review" (HITL)

Como decide: llama a tres tools del servidor mcp_supabase.py (puerto 8001)
para reunir los hechos del caso:
- get_order_details          -> datos del pedido
- search_return_policy       -> plazo/politica de esa categoria de producto
- get_customer_return_history -> devoluciones previas del cliente

Regla clave (para no confundirse leyendo el codigo): el LLM NUNCA decide el
veredicto ni escribe el mensaje final. Solo usa las tools y transcribe lo
que devuelven (pedido, productos, categoria, fecha de entrega, plazo,
devoluciones aprobadas). El veredicto lo calcula _classify_return, una
funcion Python normal y determinista (misma logica que
dataset/generate_dataset.py::classify_case, seccion 5 de
dataset/policies/00_marco_general_devoluciones.md). Es el mismo patron que usa
el Agente 3 para refund_amount/requires_human_approval: nunca fiarse de lo
que el modelo "recuerde", siempre recalcular en Python.

Que falta a proposito (no es un bug): Agente 1 no recoge el estado fisico
del articulo (`condition`) ni fotos, asi que aqui no se aplican las reglas
de classify_case que dependen de eso ("estado no admitido", exclusion de
higiene/perecederos). Se asume el mejor caso posible ('unopened'), valido
para las 16 categorias del dataset. El resto de reglas si estan
implementadas y probadas contra dataset/eval_cases.csv (ver
agente2ConMCP/tests/):
- plazo de devolucion
- importe > 100 EUR
- zona frontera
- motivo sensible
- cliente con historial de abuso

Antes de arrancar, hace falta el servidor MCP de Supabase corriendo:
    python -m backend.mcp.mcp_supabase
"""

import os
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

load_dotenv()

MCP_SUPABASE_URL = os.getenv("MCP_SUPABASE_URL", "http://localhost:8001/mcp")

DEFAULT_MODEL = os.getenv("AGENTE2_MODEL", "openai:gpt-4o-mini")

# Umbral de aprobacion automatica en euros (dataset/policies/00_marco_general_devoluciones.md,
# seccion 5): mismo umbral fijo de la plataforma que usa el Agente 3 para el
# corte HITL, pero aqui decide si el caso se deriva a revision humana en vez
# de bloquear la ejecucion de tools.
HITL_THRESHOLD_EUR = float(os.getenv("HITL_THRESHOLD_EUR", "100"))

# Mas de N devoluciones aprobadas (historial completo, ver limitacion en el
# docstring de _classify_return) activa la señal de posible abuso.
FREQUENT_RETURNER_THRESHOLD = int(os.getenv("FREQUENT_RETURNER_THRESHOLD", "3"))

# Si han pasado mas de estos dias desde que se acabo el plazo de devolucion
# de la categoria, se rechaza directamente: ya no hay duda posible. Misma
# regla que classify_case() en dataset/generate_dataset.py.
REJECTION_MARGIN_DAYS = 5

# Ventana de duda alrededor del limite del plazo: empieza este numero de
# dias antes de que se cumpla el plazo y termina donde empieza el rechazo
# automatico (REJECTION_MARGIN_DAYS). Si la solicitud cae en esta ventana no
# esta claro si aprobar o rechazar, asi que se manda a revision humana en
# vez de decidir sola. Igual que classify_case().
BOUNDARY_ZONE_LOWER_DAYS = -2

# Motivos que van SIEMPRE a revision humana, aunque el plazo y el importe
# esten dentro de lo normal (dataset/policies/00_marco_general_devoluciones.md,
# seccion 5):
# - allergic_reaction: el cliente dice haber tenido una reaccion alergica.
#   Puede implicar un riesgo de salud, no solo un reembolso. La politica
#   solo exige revision humana si los sintomas son "graves"; el Agente 1 no
#   captura esa gravedad, asi que aqui se simplifica y CUALQUIER reaccion
#   alergica declarada va a revision humana (mas prudente que decidir sola).
# - counterfeit_suspicion: se sospecha que el producto es una falsificacion.
#   Puede implicar un problema del proveedor, no solo del cliente.
SENSITIVE_REASON_CATEGORIES = {"allergic_reaction", "counterfeit_suspicion"}

# El Agente 2 solo necesita estas tres tools de mcp_supabase.py; el resto
# (create_return_record, update_return_status) pertenecen al Agente 3 y al
# panel de Admin/HITL.
EVALUATION_TOOL_NAMES = {
    "get_order_details",
    "search_return_policy",
    "get_customer_return_history",
}

SYSTEM_PROMPT = """\
Eres el Agente Evaluador de Politicas de ReFlow. Actuas como auditor: el \
Agente de Triaje ya identifico el pedido y el motivo de la devolucion, y tu \
trabajo es reunir los hechos necesarios para poder evaluarla. NO decides si \
la devolucion es valida, invalida o requiere revision humana: esa decision \
la toma un proceso Python posterior con reglas deterministas. Rellenar mal \
un hecho puede hacer que ese proceso apruebe algo que no debia, asi que no \
inventes ni calcules nada: usa unicamente lo que devuelvan las tools.

Debes, en este orden:
1. Llamar a get_order_details con el order_id para obtener el pedido, el \
cliente (customer_id, email, nombre) y los productos comprados (uno por \
cada order_item: order_item_id, nombre, categoria, cantidad, precio \
unitario e importe total). Copia tambien delivered_at tal cual lo devuelve \
la tool (no lo reformatees ni calcules cuantos dias han pasado, eso lo hace \
Python). Compón customer_address a partir de shipping_address del pedido \
(calle, ciudad, codigo postal); si no hay datos, dejalo vacio.
2. A partir de los productos devueltos, identifica la categoria del primer \
producto y llama a search_return_policy con query=el motivo de la \
devolucion y category=esa categoria, para obtener policy_info.max_return_days.
3. Llamar a get_customer_return_history con el customer_id para obtener el \
numero de devoluciones aprobadas del cliente (campo "approved" de la tool).
4. Rellenar los campos de hechos de la salida estructurada (order_id, \
customer_id, customer_email, customer_name, customer_address, category, \
delivered_at, products, policy_max_return_days, customer_approved_returns) \
exactamente con lo que devolvieron las tools. Deja decision, eligible, \
refund_amount, rationale y response_to_customer en sus valores por \
defecto: un proceso posterior los calculara.

Si una tool falla o no encuentra el pedido, deja los campos que no pudiste \
obtener vacios (None o listas vacias) en vez de inventarlos.
"""


class EvaluationRequest(BaseModel):
    """Caso recibido del Agente 1 (Triaje), listo para evaluar elegibilidad."""

    order_id: str = Field(description="UUID del pedido, ya verificado por el Agente 1.")
    reason: str = Field(description="Motivo de la devolucion en palabras del cliente.")
    reason_category: str = Field(
        description=(
            "Motivo elegido de la lista cerrada de dataset/policies/"
            "00_marco_general_devoluciones.md (seccion 3): defective (defectuoso), "
            "wrong_item_shipped (se envio otro articulo), wrong_size (talla/medida "
            "incorrecta), not_as_described (no coincide con la descripcion), "
            "damaged_in_transit (llego danado por el transporte), missing_parts "
            "(faltan piezas), changed_mind (cambio de opinion), duplicate_order "
            "(pedido duplicado por error), arrived_late (llego tarde y ya no se "
            "necesita), better_price_found (encontro mejor precio), "
            "allergic_reaction (reaccion alergica), quality_issue (baja calidad "
            "percibida sin defecto), assembly_issue (problema de montaje), "
            "incompatible (incompatibilidad tecnica) o counterfeit_suspicion "
            "(sospecha de producto falsificado)."
        )
    )


class Product(BaseModel):
    """Un producto del pedido, tal y como lo copia el LLM de get_order_details.

    Todos los campos son Optional por el mismo motivo que en EvaluationOutput
    (ver su docstring): con el schema estricto de OpenAI, el LLM puede rellenar
    un campo con `null` explicito en vez de omitirlo, y un tipo no-Optional
    rechazaria ese `null` con un ValidationError.
    """

    order_item_id: Optional[str] = Field(default=None, description="UUID del order_item.")
    name: Optional[str] = Field(default=None, description="Nombre del producto.")
    category: Optional[str] = Field(default=None, description="Categoria del producto.")
    quantity: Optional[int] = Field(default=None, description="Unidades devueltas.")
    unit_price: Optional[float] = Field(default=None, description="Precio unitario, en euros.")
    total_price: Optional[float] = Field(
        default=None, description="Importe total de la linea (unit_price x quantity), en euros."
    )


class EvaluationOutput(BaseModel):
    """Salida estructurada del Agente Evaluador, lista para pasar al Agente de Resolucion.

    Todos los campos con valor por defecto estan marcados como Optional, aunque
    en teoria nunca deberian quedar en None una vez procesados. Es un workaround
    para un bug visto en produccion: al usar create_agent con el schema estricto
    de OpenAI, el modelo a veces devuelve `null` de forma explicita en vez de
    simplemente omitir un campo que no sabe rellenar (nos ha pasado con
    decision/eligible/refund_amount/rationale/response_to_customer). Si el
    campo no fuera Optional, ese `null` haria fallar la validacion con un
    ValidationError. Por eso son Optional: para poder aceptar ese `null` sin
    que explote. Despues, run_agent_evaluacion y _apply_deterministic_decision
    se encargan de sustituir cualquier None por un valor por defecto seguro
    antes de usarlo.
    """

    # --- Hechos transcritos por el LLM a partir de las tools (paso 1-3 del SYSTEM_PROMPT) ---
    order_id: Optional[str] = Field(default=None, description="UUID del pedido.")
    customer_id: Optional[str] = Field(default=None, description="UUID del cliente.")
    customer_email: Optional[str] = Field(default=None, description="Email del cliente.")
    customer_name: Optional[str] = Field(default="", description="Nombre del cliente, para la etiqueta.")
    customer_address: Optional[str] = Field(default="", description="Direccion de envio del pedido.")
    reason: Optional[str] = Field(
        default="", description="Motivo de la devolucion, copiado de la peticion del Agente 1."
    )
    reason_category: Optional[str] = Field(
        default="", description="Categoria del motivo, copiada de la peticion del Agente 1."
    )
    category: Optional[str] = Field(
        default=None, description="Categoria del primer producto devuelto."
    )
    delivered_at: Optional[str] = Field(
        default=None, description="Fecha/hora de entrega del pedido, tal cual la devuelve get_order_details."
    )
    products: Optional[list[Product]] = Field(
        default=None,
        description="Productos comprados en el pedido, uno por order_item (ver Product).",
    )
    policy_max_return_days: Optional[int] = Field(
        default=None, description="Plazo maximo de devolucion (dias) de la categoria, de search_return_policy."
    )
    customer_approved_returns: Optional[int] = Field(
        default=0, description="Numero de devoluciones aprobadas del cliente (historial completo)."
    )

    # --- Recalculados SIEMPRE en Python tras la llamada al LLM (ver _classify_return) ---
    decision: Optional[str] = Field(
        default="human_review",
        description="Veredicto determinista: 'valid', 'invalid' o 'human_review'.",
    )
    eligible: Optional[bool] = Field(
        default=False, description="True unicamente cuando decision == 'valid'."
    )
    refund_amount: Optional[float] = Field(
        default=0.0, description="Suma de total_price de los productos devueltos."
    )
    rationale: Optional[str] = Field(
        default="", description="Explicacion de la regla de negocio que determino el veredicto."
    )
    response_to_customer: Optional[str] = Field(
        default="", description="Mensaje final a mostrar al cliente en este turno."
    )


def _get_mcp_client(mcp_supabase_url: str = MCP_SUPABASE_URL) -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "supabase": {
                "url": mcp_supabase_url,
                "transport": "streamable_http",
            }
        }
    )


async def get_evaluation_tools(mcp_supabase_url: str = MCP_SUPABASE_URL) -> list:
    """Obtiene del servidor MCP de Supabase solo las tools que necesita el Agente 2."""
    client = _get_mcp_client(mcp_supabase_url)
    tools = await client.get_tools(server_name="supabase")
    return [tool for tool in tools if tool.name in EVALUATION_TOOL_NAMES]


def _resolve_model(model: str | BaseChatModel) -> str | BaseChatModel:
    """Convierte "openai:<modelo>" en un ChatOpenAI normal (Chat Completions).

    agente3ConMCP.agente_resolucion._resolve_model tiene el mismo aspecto y
    por el mismo motivo: antes, EvaluationOutput.products era un dict
    "libre" que no pasaba el modo "strict" que LangChain activa al combinar
    tools + response_format, y ese era el motivo de forzar la API de
    Responses (use_responses_api=True). Desde que products esta tipado (ver
    clase Product), el schema completo es compatible con el modo estricto
    normal. Verificado con una llamada real (create_agent + tools +
    response_format=EvaluationOutput sin use_responses_api) que devuelve
    structured_response sin error.
    """
    if isinstance(model, str) and model.startswith("openai:"):
        model_name = model.removeprefix("openai:")
        return ChatOpenAI(model=model_name)
    return model


async def build_evaluation_agent(
    model: str | BaseChatModel = DEFAULT_MODEL,
    mcp_supabase_url: str = MCP_SUPABASE_URL,
    tools: Optional[list] = None,
) -> Any:
    """Construye el agente evaluador (langgraph) con las tools de get_order_details,
    search_return_policy y get_customer_return_history.

    `tools` permite inyectar tools ya resueltas (por ejemplo en tests) sin
    tener que conectar a un servidor MCP real.
    """
    resolved_tools = tools if tools is not None else await get_evaluation_tools(mcp_supabase_url)
    return create_agent(
        model=_resolve_model(model),
        tools=resolved_tools,
        system_prompt=SYSTEM_PROMPT,
        response_format=EvaluationOutput,
    )


def _parse_days_since(delivered_at: Optional[str]) -> Optional[int]:
    """Dias transcurridos desde delivered_at(entrega del pedido) hasta ahora, o None si no se pudo parsear."""
    if not delivered_at:
        return None
    try:
        parsed = datetime.fromisoformat(delivered_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).days


def _sum_refund_amount(products: list[Product]) -> float:
    """Todos los campos de Product son Optional (ver su docstring): el LLM puede
    devolver unit_price/quantity con `null` explicito en vez de omitirlos, asi
    que hace falta el `or` para no acabar haciendo float(None).
    """
    total = 0.0
    for product in products:
        total_price = product.total_price
        if total_price is None:
            unit_price = product.unit_price or 0
            quantity = product.quantity or 1
            total_price = float(unit_price) * float(quantity)
        total += float(total_price)
    return round(total, 2)


def _classify_return(
    days_since_delivery: int,
    max_return_days: int,
    reason_category: str,
    refund_amount: float,
    customer_approved_returns: int,
) -> tuple[str, str]:
    """Decide el veredicto de una devolucion y explica por que.

    Devuelve una pareja (veredicto, explicacion):
    - "invalid": se rechaza sola. Solo ocurre si el plazo se superó de forma
      clara, sin ningun margen de duda.
    - "human_review": pasa a que la revise una persona, porque se ha detectado
      al menos una señal de alerta (ver mas abajo). El caso no se rechaza ni
      se aprueba automaticamente.
    - "valid": se aprueba sola, porque no se detecto ninguna señal de alerta.

    El orden de las comprobaciones importa: primero se descarta el rechazo
    claro, y solo si no aplica se buscan señales de alerta.

    Simplificaciones conocidas (no son bugs, son limitaciones asumidas a
    proposito por ahora):
    - No tiene en cuenta el estado fisico del articulo (roto, usado, sin
      abrir...) ni si hay fotos del defecto, porque esa informacion todavia
      no se recoge en pasos anteriores del proceso. Se asume siempre el mejor
      caso posible para el cliente.
    - Cuenta TODAS las devoluciones aprobadas del historial del cliente, no
      solo las de los ultimos meses, porque no hay forma de filtrar por fecha
      con los datos disponibles hoy.
    """
    # diff > 0 significa que la entrega ya lleva mas dias de los permitidos;
    # diff <= 0 significa que todavia esta dentro de plazo.
    diff = days_since_delivery - max_return_days

    # Plazo superado con mucho margen: no hay duda posible, se rechaza sin
    # mirar el resto de señales.
    if diff > REJECTION_MARGIN_DAYS:
        return "invalid", (
            f"Plazo de devolucion superado ampliamente: {days_since_delivery} dias desde la "
            f"entrega frente a un maximo de {max_return_days} dias para esta categoria (mas de "
            f"{REJECTION_MARGIN_DAYS} dias de margen excedido)."
        )

    # A partir de aqui el caso no se rechaza directamente. Se van acumulando
    # todas las señales de alerta que se cumplan (puede haber varias a la
    # vez); si aparece alguna, el caso se manda a revision humana con todas
    # las razones juntas.
    reasons: list[str] = []
    if reason_category in SENSITIVE_REASON_CATEGORIES:
        reasons.append(f"motivo sensible ('{reason_category}') que requiere valoracion humana")
    if BOUNDARY_ZONE_LOWER_DAYS <= diff <= REJECTION_MARGIN_DAYS:
        reasons.append(
            f"solicitud en zona frontera del plazo ({days_since_delivery} de {max_return_days} "
            f"dias, diferencia {diff:+d})"
        )
    if refund_amount > HITL_THRESHOLD_EUR:
        reasons.append(
            f"importe a reembolsar de {refund_amount:.2f} EUR supera el umbral de "
            f"{HITL_THRESHOLD_EUR:.0f} EUR (HITL fijo de la plataforma)"
        )
    if customer_approved_returns > FREQUENT_RETURNER_THRESHOLD:
        reasons.append(
            f"cliente con {customer_approved_returns} devoluciones aprobadas (posible abuso)"
        )

    if reasons:
        return "human_review", "Revision humana obligatoria: " + "; ".join(reasons) + "."

    # Ninguna señal de alerta: se aprueba automaticamente.
    return "valid", (
        f"Solicitud dentro de plazo ({days_since_delivery} de {max_return_days} dias) e importe "
        f"de {refund_amount:.2f} EUR dentro del umbral de aprobacion automatica "
        f"(<={HITL_THRESHOLD_EUR:.0f} EUR)."
    )


def _response_to_customer(decision: str, rationale: str, refund_amount: float) -> str:
    """Construye el mensaje en lenguaje natural que se le muestra al cliente,
    en funcion de la decision ya tomada sobre su devolucion.

    Args:
        decision: resultado de la evaluacion ("valid", "invalid" o cualquier
            otro valor, tratado como "human_review").
        rationale: explicacion tecnica de por que se tomo la decision; se
            reutiliza tal cual en los casos "invalid" y "human_review".
        refund_amount: importe a reembolsar, solo se muestra si es valida.

    Returns:
        Texto ya formateado listo para mostrar al cliente.
    """
    if decision == "valid":
        # Devolucion aprobada automaticamente: se informa del importe a reembolsar.
        return (
            f"Tu devolucion ha sido validada. Vamos a generar tu etiqueta de transporte y "
            f"te confirmaremos el reembolso de {refund_amount:.2f} EUR en breve."
        )
    if decision == "invalid":
        # Rechazo automatico: se explica el motivo (rationale) sin dar pie a mas gestion.
        return f"Lo sentimos, no podemos tramitar esta devolucion de forma automatica: {rationale}"
    # Cualquier otro caso ("human_review"): no hay decision automatica, se avisa
    # de que un administrador revisara el caso manualmente.
    return (
        f"Tu solicitud de devolucion ha sido derivada a un administrador para su revision "
        f"manual. Te avisaremos en cuanto se resuelva. Motivo: {rationale}"
    )


def _apply_deterministic_decision(output: EvaluationOutput) -> None:
    """Recalcula decision/eligible/refund_amount/rationale/response_to_customer en Python,
    sobrescribiendo lo que haya puesto el LLM (que solo debia transcribir hechos).
    Mutacion in-place, igual de espiritu que run_agent_resolucion en agente3ConMCP.

    Aplica, en orden, tres comprobaciones que pueden cortar la evaluacion
    devolviendo "invalid" o "human_review"; si ninguna aplica, delega la
    clasificacion final en `_classify_return`. En todos los casos deja
    `output` completamente relleno (decision, eligible, rationale y
    response_to_customer) antes de retornar.
    """
    # products/customer_approved_returns pueden llegar en None (ver docstring
    # de EvaluationOutput) en vez de la lista/0 vacios que serian su default.
    output.products = output.products or []
    output.customer_approved_returns = output.customer_approved_returns or 0
    output.refund_amount = _sum_refund_amount(output.products)

    # 1) Datos minimos ausentes: sin pedido, fecha de entrega o productos no
    # hay nada que evaluar, se rechaza directamente (no llega a revision manual).
    if not output.order_id or not output.delivered_at or not output.products:
        output.decision = "invalid"
        output.eligible = False
        output.rationale = (
            "No se pudo verificar el pedido, sus productos o su fecha de entrega."
        )
        output.response_to_customer = _response_to_customer(
            output.decision, output.rationale, output.refund_amount
        )
        return

    # 2) Mezcla de categorias en la misma devolucion: la politica puede variar
    # por categoria, asi que no se puede decidir de forma automatica.
    categories = {p.category for p in output.products if p.category}
    if len(categories) > 1:
        output.decision = "human_review"
        output.eligible = False
        output.rationale = (
            "La devolucion incluye productos de varias categorias distintas "
            f"({', '.join(sorted(categories))}); se deriva a revision manual."
        )
        output.response_to_customer = _response_to_customer(
            output.decision, output.rationale, output.refund_amount
        )
        return

    # 3) No se puede calcular el plazo de devolucion (fecha invalida o falta
    # el plazo maximo segun politica): tampoco se puede decidir automaticamente.
    days_since_delivery = _parse_days_since(output.delivered_at)
    if days_since_delivery is None or output.policy_max_return_days is None:
        output.decision = "human_review"
        output.eligible = False
        output.rationale = (
            "No se pudo determinar el plazo de devolucion aplicable; se deriva a revision manual."
        )
        output.response_to_customer = _response_to_customer(
            output.decision, output.rationale, output.refund_amount
        )
        return

    # Con todos los datos disponibles, la clasificacion final (valid/invalid/
    # human_review) se delega en _classify_return.
    decision, rationale = _classify_return(
        days_since_delivery=days_since_delivery,
        max_return_days=output.policy_max_return_days,
        reason_category=output.reason_category,
        refund_amount=output.refund_amount,
        customer_approved_returns=output.customer_approved_returns,
    )
    output.decision = decision
    output.eligible = decision == "valid"
    output.rationale = rationale
    output.response_to_customer = _response_to_customer(decision, rationale, output.refund_amount)


def _get_evaluation_request_with_format(request: EvaluationRequest) -> str:
    return (
        "Caso derivado por el Agente de Triaje. Reune los hechos necesarios para "
        "poder evaluarlo (tu no decides si es elegible):\n"
        f"- order_id: {request.order_id}\n"
        f"- reason: {request.reason}\n"
        f"- reason_category: {request.reason_category}\n"
    )


async def run_agent_evaluacion(
    request: EvaluationRequest,
    *,
    agent: Optional[Any] = None,
    model: str = DEFAULT_MODEL,
    mcp_supabase_url: str = MCP_SUPABASE_URL,
) -> EvaluationOutput:
    """Evalua un caso ya triado por el Agente 1.

    El LLM solo se usa para reunir hechos (consultar Supabase/politicas via
    MCP y rellenar EvaluationOutput); la decision final (valid/invalid/
    human_review) la recalcula despues `_apply_deterministic_decision` en
    Python puro, para que sea determinista y no dependa de lo que "opine"
    el modelo.

    Args:
        request: Caso a evaluar (order_id, reason, reason_category).
        agent: Agente ya construido (permite reutilizarlo entre casos o
            inyectar un doble de prueba en tests). Si no se pasa, se
            construye uno nuevo conectando al servidor MCP.
        model: Modelo a usar si hay que construir el agente.
        mcp_supabase_url: URL del servidor MCP de datos y politicas si hay que construir el agente.

    Returns:
        EvaluationOutput ya con la decision determinista aplicada, listo
        para pasar al Agente 3 (resolucion) o al Agente de Triaje.
    """
    # Si no se inyecto un agente (p.ej. en tests), se construye uno nuevo
    # conectado al MCP; permite reutilizar la misma instancia entre llamadas.
    resolved_agent = agent
    if resolved_agent is None:
        resolved_agent = await build_evaluation_agent(model=model, mcp_supabase_url=mcp_supabase_url)

    # Se le pasa al agente un resumen del caso en texto y se recupera la
    # respuesta ya parseada como EvaluationOutput (structured output).
    case_summary = _get_evaluation_request_with_format(request)
    result = await resolved_agent.ainvoke({"messages": [{"role": "user", "content": case_summary}]})
    output: EvaluationOutput = result["structured_response"]

    # El motivo lo conocemos con certeza desde la peticion original (viene
    # del Agente 1), no hace falta confiar en que el LLM lo transcriba bien.
    output.order_id = output.order_id or request.order_id
    output.reason = request.reason
    output.reason_category = request.reason_category
    # Normaliza campos que el modelo puede dejar en null explicito en vez de
    # omitir (ver docstring de EvaluationOutput) y que se usan tal cual mas
    # adelante (por ejemplo al construir un ResolutionRequest para el Agente 3).
    output.customer_name = output.customer_name or ""
    output.customer_address = output.customer_address or ""

    _apply_deterministic_decision(output)
    return output


if __name__ == "__main__":
    import asyncio
    import sys

    sys.stdout.reconfigure(encoding="utf-8")

    async def _demo() -> None:
        # Caso real de supabase/seed.sql: pedido ORD-2026-00163 de Laura
        # Fernandez. Ese pedido tiene DOS productos de categorias distintas
        # (la batidora es 'home_appliances', el libro es 'books'), asi que
        # get_order_details devuelve ambos y se espera decision='human_review'
        # por la regla de "categorias mixtas" (ver _apply_deterministic_decision),
        # con independencia del plazo. Requiere el servidor MCP levantado
        # (python -m backend.mcp.mcp_supabase) y OPENAI_API_KEY configurada.
        request = EvaluationRequest(
            order_id="e1f2a3b4-c5d6-7890-efab-901234567890",
            reason="Ya no me convence, prefiero devolverlo",
            reason_category="changed_mind",
        )
        output = await run_agent_evaluacion(request)
        print(output.model_dump())

    asyncio.run(_demo())
