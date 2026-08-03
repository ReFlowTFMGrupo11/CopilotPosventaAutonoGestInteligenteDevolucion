"""
Demo del flujo completo de ReFlow: Agente 1 (Triaje) -> Agente 2 (Evaluador) ->
Agente 3 (Resolucion), los tres encadenados igual que describe el "Flujo
Completo Paso a Paso" de doc/guia.md.

Incluye dos casos reales contra supabase/seed.sql (Casos A y B, solo lectura:
usan get_order_details / search_return_policy / get_customer_return_history
de verdad, ambos terminan en human_review) y dos casos simulados (Casos C y
D) con un pedido ficticio para completar los caminos "valid" (hasta el
Agente 3) e "invalid": como ningun pedido de supabase/seed.sql cae hoy
dentro de plazo con importe bajo y una unica categoria (las fechas de
entrega son fijas de 2026 y el reloj real avanza), los Casos C/D usan tools
MCP falsas (mismo patron de doble que los tests unitarios de cada agente,
pero invocadas por el LLM real a traves de create_agent) en vez de escribir
en la base de datos real.

Requiere:
- El servidor MCP de Supabase levantado (python -m backend.mcp.mcp_supabase)
  para los Casos A y B.
- OPENAI_API_KEY en .env (los tres agentes son LLMs reales en los cuatro
  casos; solo las tools de los Casos C/D son falsas, no el modelo).

Uso:
    python demo_flujo_completo.py
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone

from langchain_core.tools import StructuredTool

from agente1ConMCP.agente_triaje import build_triage_agent, run_agent_triaje
from agente2ConMCP.agente_evaluacion import EvaluationRequest, build_evaluation_agent, run_agent_evaluacion
from agente3ConMCP.agente_resolucion import ResolutionRequest, build_resolution_agent, run_agent_resolucion

sys.stdout.reconfigure(encoding="utf-8")


def _print_section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def _evaluation_to_resolution_request(evaluation, notes: str = "") -> ResolutionRequest:
    """Traduce la salida elegible del Agente 2 al formato que espera el Agente 3."""
    return ResolutionRequest(
        order_id=evaluation.order_id,
        customer_id=evaluation.customer_id,
        customer_email=evaluation.customer_email,
        customer_name=evaluation.customer_name,
        customer_address=evaluation.customer_address,
        reason=evaluation.reason,
        reason_category=evaluation.reason_category,
        refund_amount=evaluation.refund_amount,
        products=[
            {
                "order_item_id": p["order_item_id"],
                "quantity": p.get("quantity", 1),
                "condition": "unopened",
                "name": p.get("name", ""),
            }
            for p in evaluation.products
        ],
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Casos A y B: reales, contra el servidor MCP de Supabase y supabase/seed.sql
# (solo lectura: el Agente 1 y el Agente 2 no escriben nada en la BBDD).
# ---------------------------------------------------------------------------


async def run_live_case(title: str, message: str) -> None:
    _print_section(title)
    print(f"Cliente: {message!r}\n")

    triage = await run_agent_triaje(message)
    print("--- Agente 1 (Triaje) ---")
    print(triage.model_dump())

    if not triage.ready_for_evaluation or not triage.order_id:
        print("\nEl Agente 1 no considero el caso listo para evaluar (falta order_id o motivo).")
        return

    evaluation = await run_agent_evaluacion(
        EvaluationRequest(
            order_id=triage.order_id,
            reason=triage.reason or message,
            reason_category=triage.reason_category or "other",
        )
    )
    print("\n--- Agente 2 (Evaluador) ---")
    print(evaluation.model_dump())

    if not evaluation.eligible:
        print(f"\nCaso resuelto sin pasar por el Agente 3 (decision={evaluation.decision!r}).")
        return

    # Solo se alcanza este punto si la evaluacion real dio 'valid': el Agente
    # 3 SI escribe en la BBDD real (create_return_record, etiqueta PDF).
    print("\nEl caso es elegible: invocando al Agente 3 (esto SI escribe en la BBDD real)...")
    resolution = await run_agent_resolucion(_evaluation_to_resolution_request(evaluation))
    print("\n--- Agente 3 (Resolucion) ---")
    print(resolution.model_dump())


# ---------------------------------------------------------------------------
# Casos C y D: simulados con tools MCP falsas (sin tocar la BBDD real), pero
# con los tres LLM reales, para completar los caminos 'valid' -> Agente 3 e
# 'invalid'.
# ---------------------------------------------------------------------------


def _build_fake_tools(*, delivered_days_ago: int = 3) -> dict[str, StructuredTool]:
    """Tools MCP falsas (mismo patron de doble que los tests unitarios de cada
    agente, ver agenteNConMCP/tests/), parametrizadas por antiguedad del
    pedido para poder generar tanto un caso 'valid' (por defecto, entregado
    hace 3 dias) como uno 'invalid' (entregado hace mucho mas de los 21 dias
    de la categoria 'libros_papeleria')."""
    delivered_at = (datetime.now(timezone.utc) - timedelta(days=delivered_days_ago)).isoformat()

    async def fake_get_order_details(order_id: str) -> dict:
        return {
            "order": {
                "id": order_id,
                "customer_id": "demo-customer-0001",
                "status": "delivered",
                "delivered_at": delivered_at,
                "shipping_address": {
                    "street": "Calle Ficticia 1",
                    "city": "Madrid",
                    "postal_code": "28001",
                    "country": "ES",
                },
                "customer": {
                    "id": "demo-customer-0001",
                    "email": "cliente.demo@example.com",
                    "full_name": "Cliente Demo",
                },
            },
            "items": [
                {
                    "id": "demo-item-0001",
                    "order_id": order_id,
                    "product_id": "demo-product-0001",
                    "quantity": 1,
                    "unit_price": 24.90,
                    "total_price": 24.90,
                    "product": {
                        "name": "Cuaderno de Notas Premium ReFlow",
                        "sku": "DEMO-LIBR-001",
                        "category": "libros_papeleria",
                        "price": 24.90,
                        "weight_kg": 0.3,
                    },
                }
            ],
        }

    async def fake_search_return_policy(query: str, category: str = "") -> dict:
        return {
            "query": query,
            "category": category,
            "semantic_results": [],
            "policy_info": {
                "category": "libros_papeleria",
                "max_return_days": 21,
                "requires_original_packaging": False,
                "restocking_fee_percent": 0,
                "allowed_conditions": ["unopened", "wrong_item", "defective"],
                "policy_text": "Los libros y articulos de papeleria pueden devolverse en 21 dias.",
            },
        }

    async def fake_get_customer_return_history(customer_id: str) -> dict:
        return {"customer_id": customer_id, "total_returns": 0, "approved": 0, "rejected": 0, "returns": []}

    async def fake_create_return_record(
        order_id: str, customer_id: str, reason: str, reason_category: str,
        refund_amount: float, items: list[dict], notes: str = "",
    ) -> dict:
        return {
            "return_request": {
                "id": "demo-return-0001",
                "order_id": order_id,
                "customer_id": customer_id,
                "status": "pending",
                "reason": reason,
                "reason_category": reason_category,
                "refund_amount": refund_amount,
                "notes": notes,
            },
            "items_created": len(items),
        }

    async def fake_generate_shipping_label(
        order_id: str, items: list[dict], customer_name: str = "", customer_address: str = "",
    ) -> dict:
        return {
            "tracking_number": "RF-DEMOFAKE01",
            "label_path": "(simulado, no se ha escrito ningun fichero)",
            "filename": "label_RF-DEMOFAKE01.pdf",
            "order_id": order_id,
            "items_count": len(items),
        }

    async def fake_send_customer_notification(
        email: str, message: str, subject: str = "ReFlow - Actualizacion de tu devolucion",
        attachment_path: str = "",
    ) -> dict:
        return {
            "notification_id": "demo-notification-0001",
            "status": "sent_simulated",
            "to": email,
            "subject": subject,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Simulado por demo_flujo_completo.py, sin envio real.",
        }

    return {
        "get_order_details": StructuredTool.from_function(
            coroutine=fake_get_order_details,
            name="get_order_details",
            description="Consulta en PostgreSQL los detalles del pedido, fechas y productos comprados.",
        ),
        "search_return_policy": StructuredTool.from_function(
            coroutine=fake_search_return_policy,
            name="search_return_policy",
            description="Realiza una busqueda semantica RAG usando pgvector sobre la normativa de la tienda.",
        ),
        "get_customer_return_history": StructuredTool.from_function(
            coroutine=fake_get_customer_return_history,
            name="get_customer_return_history",
            description="Recupera el historial de devoluciones del cliente para detectar posibles abusos.",
        ),
        "create_return_record": StructuredTool.from_function(
            coroutine=fake_create_return_record,
            name="create_return_record",
            description="Inserta una solicitud de devolucion en la tabla devoluciones de Supabase.",
        ),
        "generate_shipping_label": StructuredTool.from_function(
            coroutine=fake_generate_shipping_label,
            name="generate_shipping_label",
            description="Genera un archivo PDF simulado de la etiqueta de transporte utilizando reportlab.",
        ),
        "send_customer_notification": StructuredTool.from_function(
            coroutine=fake_send_customer_notification,
            name="send_customer_notification",
            description="Simula el envio de un correo electronico transaccional con el enlace al PDF generado.",
        ),
    }


async def run_simulated_case(
    title: str, message: str, *, delivered_days_ago: int, expect_agente3: bool
) -> None:
    _print_section(title)
    fake_tools = _build_fake_tools(delivered_days_ago=delivered_days_ago)
    print(f"Cliente: {message!r}\n")

    triage_agent = await build_triage_agent(tools=[fake_tools["get_order_details"]])
    triage = await run_agent_triaje(message, agent=triage_agent)
    print("--- Agente 1 (Triaje) ---")
    print(triage.model_dump())

    evaluation_agent = await build_evaluation_agent(
        tools=[
            fake_tools["get_order_details"],
            fake_tools["search_return_policy"],
            fake_tools["get_customer_return_history"],
        ]
    )
    evaluation = await run_agent_evaluacion(
        EvaluationRequest(
            order_id=triage.order_id or "demo-0001",
            reason=triage.reason or message,
            reason_category=triage.reason_category or "changed_mind",
        ),
        agent=evaluation_agent,
    )
    print("\n--- Agente 2 (Evaluador) ---")
    print(evaluation.model_dump())

    if not evaluation.eligible:
        marker = "" if not expect_agente3 else " [INESPERADO para este caso simulado]"
        print(f"\nCaso resuelto sin pasar por el Agente 3 (decision={evaluation.decision!r}).{marker}")
        return
    if not expect_agente3:
        print("\n[INESPERADO para este caso simulado] el caso salio elegible.")

    resolution_agent = await build_resolution_agent(
        tools=[
            fake_tools["create_return_record"],
            fake_tools["generate_shipping_label"],
            fake_tools["send_customer_notification"],
        ]
    )
    resolution = await run_agent_resolucion(
        _evaluation_to_resolution_request(evaluation), agent=resolution_agent
    )
    print("\n--- Agente 3 (Resolucion) ---")
    print(resolution.model_dump())


async def main() -> None:
    # Caso A: pedido de Laura Fernandez, con DOS productos de categorias
    # distintas (batidora 'home_appliances' + libro 'books') => se espera
    # decision='human_review' por la regla de "categorias mixtas", con
    # independencia del plazo o la fecha real de hoy.
    await run_live_case(
        "CASO A (real, solo lectura): pedido con productos de categorias mixtas",
        "Hola, quiero devolver el pedido e1f2a3b4-c5d6-7890-efab-901234567890, "
        "ya no me convence, prefiero el reembolso",
    )

    # Caso B: pedido de Maria Garcia, un unico producto (portatil de 899.99
    # EUR) -> importe por encima del umbral HITL de 100 EUR => se espera
    # decision='human_review' (posiblemente tambien por zona frontera del
    # plazo, segun la fecha real de hoy).
    await run_live_case(
        "CASO B (real, solo lectura): importe por encima del umbral HITL",
        "Hola, quiero devolver el pedido c9d0e1f2-a3b4-5678-cdef-789012345678, "
        "ya no lo quiero",
    )

    # Caso C: simulado (sin tocar la BBDD real), pedido ficticio entregado
    # hace 3 dias, dentro del plazo de 21 dias de 'libros_papeleria' e
    # importe bajo => se espera decision='valid' -> se completa el camino
    # hasta el Agente 3 (con tools MCP falsas, no escribe nada real).
    await run_simulated_case(
        "CASO C (SIMULADO, sin tocar la BBDD real): dentro de plazo -> "
        "camino 'valid' completo hasta el Agente 3",
        "Hola, quiero devolver mi pedido demo-0001, ya no me hace falta",
        delivered_days_ago=3,
        expect_agente3=True,
    )

    # Caso D: simulado, mismo pedido ficticio pero entregado hace 60 dias
    # (muy por encima de los 21 dias de la categoria) => se espera
    # decision='invalid', sin llegar al Agente 3.
    await run_simulated_case(
        "CASO D (SIMULADO, sin tocar la BBDD real): plazo superado -> rechazo automatico",
        "Hola, quiero devolver mi pedido demo-0002, ya no me hace falta",
        delivered_days_ago=60,
        expect_agente3=False,
    )


if __name__ == "__main__":
    asyncio.run(main())
