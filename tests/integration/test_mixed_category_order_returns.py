"""Tests de integración: pedido con productos de varias categorías donde
solo ALGUNOS artículos cumplen la política de devolución.

Escenario de negocio a validar:
    Un cliente hace UNA sola solicitud de devolución sobre un pedido que
    contiene productos de categorías distintas, cada una con su propia
    política. Se espera que la app decida la elegibilidad POR ARTÍCULO
    (algunos se marcan como "se devuelven", otros como "no se pueden
    devolver") y que se lo comunique así al cliente en una única respuesta.

Estos tests prueban la implementación de la Opción B (ver
``CoberturaDevoluvionMixta.md``): salida estructurada por artículo en
``evaluator_agent`` + filtrado por artículo en ``resolution_agent``.
Antes de este fix, un fichero con el mismo nombre demostraba el bug
(la categoría del primer artículo "ganaba" y toda la solicitud se
aprobaba/rechazaba como bloque); ahora demuestra que quedó corregido.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from backend.agents.nodes.evaluator import evaluator_agent
from backend.agents.nodes.resolution import resolution_agent
from backend.models import ItemEligibility, PolicyEvaluationOutput


def _mock_llm_with_structured_output(output: PolicyEvaluationOutput) -> MagicMock:
    """Forma real de include_raw=True (ver usage_tracking.py::invoke_structured_tracked)."""
    structured = MagicMock()
    structured.ainvoke = AsyncMock(
        return_value={"raw": AIMessage(content=""), "parsed": output, "parsing_error": None}
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


class TestPolicyEvaluatorMixedCategories:
    """El evaluador de políticas ante un pedido con >1 categoría."""

    @pytest.mark.asyncio
    async def test_rag_search_queries_each_distinct_category(
        self,
        mock_order_details_mixed_categories,
        mock_return_history_clean,
        sample_items_to_return_mixed,
        mock_policy_results_electronics,
        mock_policy_results_cosmetics,
    ):
        """Se hace una búsqueda RAG por CADA categoría distinta presente en
        ``items_to_return`` (electrónica y cosmética), no solo por la
        categoría del primer artículo del pedido.
        """
        mock_output = PolicyEvaluationOutput(items=[
            ItemEligibility(
                order_item_id="oi-electronics-uuid", is_eligible=True,
                eligibility_reason="Defectuoso, dentro de plazo", refund_amount=79.99,
                policy_category="electronica_informatica",
            ),
            ItemEligibility(
                order_item_id="oi-cosmetics-uuid", is_eligible=False,
                eligibility_reason="Precinto de higiene retirado por cambio de opinión",
                refund_amount=0.0, policy_category="cosmetica_perfumeria",
            ),
        ])
        mock_llm = _mock_llm_with_structured_output(mock_output)

        async def search_side_effect(query, category):
            return {
                "electronica_informatica": mock_policy_results_electronics,
                "cosmetica_perfumeria": mock_policy_results_cosmetics,
            }[category]

        search_mock = AsyncMock(side_effect=search_side_effect)

        state = {
            "messages": [],
            "order_details": mock_order_details_mixed_categories,
            "return_history": mock_return_history_clean,
            "reason": "Uno está roto y del otro no quiero saber nada",
            "reason_category": "defective",
            "items_to_return": sample_items_to_return_mixed,
        }

        with patch("backend.agents.nodes.evaluator._build_llm", return_value=mock_llm), \
             patch("backend.agents.nodes.evaluator.search_return_policy", search_mock):
            await evaluator_agent(state)

        assert search_mock.await_count == 2
        queried_categories = {call.kwargs["category"] for call in search_mock.await_args_list}
        assert queried_categories == {"electronica_informatica", "cosmetica_perfumeria"}

    @pytest.mark.asyncio
    async def test_mixed_eligibility_marks_each_item_independently(
        self,
        mock_order_details_mixed_categories,
        mock_return_history_clean,
        sample_items_to_return_mixed,
        mock_policy_results_electronics,
        mock_policy_results_cosmetics,
    ):
        """Con un pedido mixto, el resultado final tiene UNA decisión por
        artículo: auriculares elegibles, perfume no elegible. El reembolso
        agregado solo cuenta el artículo elegible.
        """
        mock_output = PolicyEvaluationOutput(items=[
            ItemEligibility(
                order_item_id="oi-electronics-uuid", is_eligible=True,
                eligibility_reason="Defectuoso, dentro de plazo de 30 días", refund_amount=79.99,
                policy_category="electronica_informatica",
            ),
            ItemEligibility(
                order_item_id="oi-cosmetics-uuid", is_eligible=False,
                eligibility_reason="Precinto de higiene retirado por cambio de opinión",
                refund_amount=0.0, policy_category="cosmetica_perfumeria",
            ),
        ])
        mock_llm = _mock_llm_with_structured_output(mock_output)

        async def search_side_effect(query, category):
            return {
                "electronica_informatica": mock_policy_results_electronics,
                "cosmetica_perfumeria": mock_policy_results_cosmetics,
            }[category]

        state = {
            "messages": [],
            "order_details": mock_order_details_mixed_categories,
            "return_history": mock_return_history_clean,
            "reason": "Uno está roto y del otro no quiero saber nada",
            "reason_category": "defective",
            "items_to_return": sample_items_to_return_mixed,
        }

        with patch("backend.agents.nodes.evaluator._build_llm", return_value=mock_llm), \
             patch("backend.agents.nodes.evaluator.search_return_policy", new_callable=AsyncMock, side_effect=search_side_effect):
            result = await evaluator_agent(state)

        by_item = {e["order_item_id"]: e for e in result["items_eligibility"]}
        assert by_item["oi-electronics-uuid"]["is_eligible"] is True
        assert by_item["oi-cosmetics-uuid"]["is_eligible"] is False

        # Al menos un artículo elegible -> la solicitud avanza a resolución.
        assert result["any_eligible"] is True
        # El reembolso agregado solo cuenta el artículo elegible.
        assert result["refund_amount"] == 79.99
        # El resumen textual menciona ambos artículos y su desenlace.
        assert "elegible" in result["eligibility_reason"]
        assert "no elegible" in result["eligibility_reason"]


class TestResolutionMixedCategories:
    """El agente de Resolución ante un pedido con elegibilidad mixta."""

    @pytest.mark.asyncio
    async def test_only_eligible_item_is_shipped_and_refunded(
        self,
        mock_order_details_mixed_categories,
        sample_items_to_return_mixed,
        mock_label_result,
    ):
        """Solo el artículo elegible (auriculares) entra en la etiqueta de
        envío y en el registro de devolución; el perfume (no elegible)
        queda excluido de ambos, pero su motivo de rechazo se traslada al
        mensaje final para el cliente.
        """
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(
                content=(
                    "Buenas noticias parciales: aprobamos la devolución de tus "
                    "auriculares, pero no podemos aceptar el perfume porque el "
                    "precinto de higiene ya fue retirado."
                )
            )
        )

        label_mock = AsyncMock(return_value=mock_label_result)
        create_return_mock = AsyncMock(
            return_value={"return_request": {"id": "ret-mixed-uuid"}}
        )
        update_status_mock = AsyncMock(return_value={"updated": True})
        notify_mock = AsyncMock(return_value={"sent": True})

        items_eligibility = [
            {
                "order_item_id": "oi-electronics-uuid",
                "is_eligible": True,
                "eligibility_reason": "Defectuoso, dentro de plazo",
                "refund_amount": 79.99,
                "policy_category": "electronica_informatica",
            },
            {
                "order_item_id": "oi-cosmetics-uuid",
                "is_eligible": False,
                "eligibility_reason": "Precinto de higiene retirado por cambio de opinión",
                "refund_amount": 0.0,
                "policy_category": "cosmetica_perfumeria",
            },
        ]

        state = {
            "refund_amount": 79.99,  # umbral HITL no superado
            "order_id": "ord-mixed-uuid",
            "customer_id": "cust-mixed-uuid",
            "customer_name": "Laura Pérez",
            "customer_email": "laura.perez@example.com",
            "reason": "Uno está roto y del otro no quiero saber nada",
            "reason_category": "defective",
            "items_to_return": sample_items_to_return_mixed,
            "items_eligibility": items_eligibility,
            "order_details": mock_order_details_mixed_categories,
        }

        with patch("backend.agents.nodes.resolution._build_llm", return_value=mock_llm), \
             patch("backend.agents.nodes.resolution.generate_shipping_label", label_mock), \
             patch("backend.agents.nodes.resolution.create_return_record", create_return_mock), \
             patch("backend.agents.nodes.resolution.update_return_status", update_status_mock), \
             patch("backend.agents.nodes.resolution.send_customer_notification", notify_mock):
            command = await resolution_agent(state)

        # La etiqueta de envío SOLO incluye el artículo elegible.
        label_call_items = label_mock.await_args.kwargs["items"]
        item_names = {item["name"] for item in label_call_items}
        assert item_names == {"Auriculares Bluetooth Pro"}

        # El registro de devolución en Supabase también excluye el perfume.
        return_record_items = create_return_mock.await_args.kwargs["items"]
        returned_ids = {item["order_item_id"] for item in return_record_items}
        assert returned_ids == {"oi-electronics-uuid"}

        # El estado final refleja que fue una aprobación PARCIAL.
        assert command.update["resolution"] == "partially_approved"
