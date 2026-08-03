"""
Agente 2: Evaluador de Politicas (LangChain + MCP)

Segundo eslabon del flujo de devoluciones descrito en doc/guia.md (Epica 2,
US 2.3). Recibe el caso que el Agente 1 (Triaje) ya extrajo del cliente
(order_id, reason, reason_category) y actua como auditor: consulta el
pedido, la politica de devolucion de la categoria del producto y el
historial de devoluciones del cliente para decidir si la solicitud es
"valid" (aprobacion automatica), "invalid" (rechazo automatico) o
"human_review" (revision manual, HITL). Usa tres tools del servidor
mcp_supabase.py (puerto 8001):
- get_order_details
- search_return_policy
- get_customer_return_history

Regla de negocio determinista (doc/policies/00_marco_general_devoluciones.md,
seccion 5; replicada en dataset/generate_dataset.py::classify_case): el LLM
solo llama a las tools y transcribe los hechos que devuelven (pedido,
productos, categoria, fecha de entrega, plazo de la politica, devoluciones
aprobadas del cliente). NUNCA decide el veredicto ni redacta el mensaje
final: eso lo hace _classify_return, una funcion Python pura, exactamente
igual que el Agente 3 recalcula refund_amount/requires_human_approval en vez
de confiar en lo que "recuerde" el modelo.

Simplificacion deliberada de alcance: el Agente 1 no captura el estado
fisico del articulo (`condition`) ni evidencia fotografica, asi que esta
version no reproduce las ramas de "estado no admitido" ni "exclusion de
higiene/perecederos" de classify_case (que dependen de esos datos). Se
asume el estado mas favorable ('unopened', admitido por las 16 categorias
del dataset). El resto de reglas (plazo, importe > 100 EUR, zona frontera,
motivo sensible, cliente con historial de abuso) si se replican y estan
validadas contra dataset/eval_cases.csv en agente2ConMCP/tests/.

Requiere el servidor MCP de Supabase levantado:
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

# Umbral de aprobacion automatica en euros (doc/policies/00_marco_general_devoluciones.md,
# seccion 5): mismo umbral fijo de la plataforma que usa el Agente 3 para el
# corte HITL, pero aqui decide si el caso se deriva a revision humana en vez
# de bloquear la ejecucion de tools.
HITL_THRESHOLD_EUR = float(os.getenv("HITL_THRESHOLD_EUR", "100"))

# Mas de N devoluciones aprobadas (historial completo, ver limitacion en el
# docstring de _classify_return) activa la señal de posible abuso.
FREQUENT_RETURNER_THRESHOLD = int(os.getenv("FREQUENT_RETURNER_THRESHOLD", "3"))

# Mas de estos dias por encima del plazo de la categoria => rechazo
# automatico (fuera de cualquier zona de ambiguedad). Igual que
# classify_case() en dataset/generate_dataset.py.
REJECTION_MARGIN_DAYS = 5

# Zona frontera del plazo: entre "3 dias antes del limite" y el margen de
# rechazo automatico de arriba. Igual que classify_case().
BOUNDARY_ZONE_LOWER_DAYS = -2

# Motivos que siempre requieren valoracion humana, con independencia de
# plazo o importe (doc/policies, seccion 5).
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
        description="defective, wrong_item, no_longer_needed, changed_mind u other."
    )


class EvaluationOutput(BaseModel):
    """Salida estructurada del Agente Evaluador, lista para pasar al Agente de Resolucion.

    Todos los campos con valor por defecto son Optional, aunque conceptualmente
    nunca deban quedar en None una vez procesados: al usar create_agent con
    schema estricto de OpenAI, el modelo a veces devuelve explicitamente
    `null` en vez de omitir un campo que no sabe rellenar (visto en
    produccion con decision/eligible/refund_amount/rationale/
    response_to_customer), y un tipo no-Optional con default rechaza ese
    `null` con un ValidationError. run_agent_evaluacion y
    _apply_deterministic_decision normalizan cualquier None a un valor por
    defecto seguro antes de usarlo.
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
    products: Optional[list[dict]] = Field(
        default=None,
        description=(
            "Productos comprados en el pedido, uno por order_item: "
            "[{'order_item_id', 'name', 'category', 'quantity', 'unit_price', 'total_price'}]."
        ),
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
    """Convierte "openai:<modelo>" en un ChatOpenAI con use_responses_api=True.

    Mismo bug/fix que agente3ConMCP.agente_resolucion._resolve_model: al usar
    tools + response_format con un modelo OpenAI normal (Chat Completions),
    LangChain activa el modo "strict" para todas las tools, y el schema de
    EvaluationOutput.products (list[dict] "libre") no pasa esa validacion.
    La API de Responses (use_responses_api=True) no fuerza ese modo.
    """
    if isinstance(model, str) and model.startswith("openai:"):
        model_name = model.removeprefix("openai:")
        return ChatOpenAI(model=model_name, use_responses_api=True)
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
    """Dias transcurridos desde delivered_at hasta ahora, o None si no se pudo parsear."""
    if not delivered_at:
        return None
    try:
        parsed = datetime.fromisoformat(delivered_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).days


def _sum_refund_amount(products: list[dict]) -> float:
    total = 0.0
    for product in products:
        total_price = product.get("total_price")
        if total_price is None:
            total_price = float(product.get("unit_price", 0)) * float(product.get("quantity", 1))
        total += float(total_price)
    return round(total, 2)


def _classify_return(
    days_since_delivery: int,
    max_return_days: int,
    reason_category: str,
    refund_amount: float,
    customer_approved_returns: int,
) -> tuple[str, str]:
    """Replica reducida de classify_case() en dataset/generate_dataset.py, aplicando
    la seccion 5 de dataset/policies/00_marco_general_devoluciones.md.

    No modela las ramas de "estado del articulo no admitido" ni "exclusion de
    higiene/perecederos" (dependen de `condition`, que el Agente 1 no capta
    hoy) ni "falta de evidencia fotografica". Tampoco distingue devoluciones
    aprobadas en los ultimos 90 dias del historial completo, porque
    get_customer_return_history no filtra por fecha. Documentado como
    trabajo futuro; el resto de reglas esta validado 1:1 contra
    dataset/eval_cases.csv (ver agente2ConMCP/tests/test_agente_evaluacion.py).
    """
    diff = days_since_delivery - max_return_days

    if diff > REJECTION_MARGIN_DAYS:
        return "invalid", (
            f"Plazo de devolucion superado ampliamente: {days_since_delivery} dias desde la "
            f"entrega frente a un maximo de {max_return_days} dias para esta categoria (mas de "
            f"{REJECTION_MARGIN_DAYS} dias de margen excedido)."
        )

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

    return "valid", (
        f"Solicitud dentro de plazo ({days_since_delivery} de {max_return_days} dias) e importe "
        f"de {refund_amount:.2f} EUR dentro del umbral de aprobacion automatica "
        f"(<={HITL_THRESHOLD_EUR:.0f} EUR)."
    )


def _response_to_customer(decision: str, rationale: str, refund_amount: float) -> str:
    if decision == "valid":
        return (
            f"Tu devolucion ha sido validada. Vamos a generar tu etiqueta de transporte y "
            f"te confirmaremos el reembolso de {refund_amount:.2f} EUR en breve."
        )
    if decision == "invalid":
        return f"Lo sentimos, no podemos tramitar esta devolucion de forma automatica: {rationale}"
    return (
        f"Tu solicitud de devolucion ha sido derivada a un administrador para su revision "
        f"manual. Te avisaremos en cuanto se resuelva. Motivo: {rationale}"
    )


def _apply_deterministic_decision(output: EvaluationOutput) -> None:
    """Recalcula decision/eligible/refund_amount/rationale/response_to_customer en Python,
    sobrescribiendo lo que haya puesto el LLM (que solo debia transcribir hechos).
    Mutacion in-place, igual de espiritu que run_agent_resolucion en agente3ConMCP.
    """
    # products/customer_approved_returns pueden llegar en None (ver docstring
    # de EvaluationOutput) en vez de la lista/0 vacios que serian su default.
    output.products = output.products or []
    output.customer_approved_returns = output.customer_approved_returns or 0
    output.refund_amount = _sum_refund_amount(output.products)

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

    categories = {p.get("category") for p in output.products if p.get("category")}
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

    Args:
        request: Caso a evaluar (order_id, reason, reason_category).
        agent: Agente ya construido (permite reutilizarlo entre casos o
            inyectar un doble de prueba en tests). Si no se pasa, se
            construye uno nuevo conectando al servidor MCP.
        model: Modelo a usar si hay que construir el agente.
        mcp_supabase_url: URL del servidor MCP de datos y politicas si hay que construir el agente.
    """
    resolved_agent = agent
    if resolved_agent is None:
        resolved_agent = await build_evaluation_agent(model=model, mcp_supabase_url=mcp_supabase_url)

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
