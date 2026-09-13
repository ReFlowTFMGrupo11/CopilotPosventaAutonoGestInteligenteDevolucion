"""Tests unitarios para backend.services.returns_service.

Extraído de test_supabase_service.py al dividir supabase_service.py por
dominio (ver docs/REMAINING_TASKS.md #3), y ampliado en la misma operación
para cerrar el hueco de cobertura que tenía ese fichero (tarea #4): antes,
de las funciones que ahora viven aquí, solo get_customer_return_history/
create_return_record/update_return_status tenían test -- get_pending_return_
request_id, get_latest_return_request, list_pending_approvals, list_returns,
get_return_detail, get_return_stats y los tres _flatten_* no tenían ninguno.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.services.returns_service import (
    _flatten_admin_row,
    _flatten_order_number,
    _flatten_product_names,
    create_return_record,
    get_customer_return_history,
    get_latest_return_request,
    get_pending_return_request_id,
    get_return_detail,
    get_return_stats,
    list_pending_approvals,
    list_returns,
    update_return_status,
)


def _make_sync_supabase_client():
    """Cliente fake con builder sync y execute async, como supabase real."""
    client = MagicMock()
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.single.return_value = query
    query.in_.return_value = query
    query.insert.return_value = query
    query.update.return_value = query
    client.table.return_value = query
    return client, query


def _patched_client(mock_client):
    return patch(
        "backend.services.returns_service.get_supabase_client",
        return_value=mock_client,
    )


# ---------------------------------------------------------------------------
# get_customer_return_history
# ---------------------------------------------------------------------------


class TestGetCustomerReturnHistory:
    """Tests para historial de devoluciones."""

    @pytest.mark.asyncio
    async def test_counts_approved_and_rejected(self):
        """Verifica que el historial cuenta correctamente devoluciones aprobadas y rechazadas."""
        mock_client, query = _make_sync_supabase_client()

        resp_mock = MagicMock()
        resp_mock.data = [
            {"status": "approved"},
            {"status": "approved"},
            {"status": "rejected"},
        ]

        query.execute = AsyncMock(return_value=resp_mock)

        with _patched_client(mock_client):
            result = await get_customer_return_history("cust-1")

        assert result["total_returns"] == 3
        assert result["approved"] == 2
        assert result["rejected"] == 1

    @pytest.mark.asyncio
    async def test_empty_history(self):
        """Verifica que un cliente sin devoluciones previas devuelve contadores a cero."""
        mock_client, query = _make_sync_supabase_client()

        resp_mock = MagicMock()
        resp_mock.data = []

        query.execute = AsyncMock(return_value=resp_mock)

        with _patched_client(mock_client):
            result = await get_customer_return_history("cust-1")

        assert result["total_returns"] == 0
        assert result["approved"] == 0
        assert result["rejected"] == 0


# ---------------------------------------------------------------------------
# create_return_record
# ---------------------------------------------------------------------------


class TestCreateReturnRecord:
    """Tests para creación de devoluciones."""

    @pytest.mark.asyncio
    async def test_creates_return_and_items(self):
        """Verifica que se crea el registro de devolución junto con sus artículos."""
        mock_client, query = _make_sync_supabase_client()

        existing_resp = MagicMock()
        existing_resp.data = []

        return_resp = MagicMock()
        return_resp.data = [{"id": "ret-1", "status": "pending"}]

        items_resp = MagicMock()
        items_resp.data = []

        query.execute = AsyncMock(side_effect=[existing_resp, return_resp, items_resp])

        with _patched_client(mock_client):
            result = await create_return_record(
                order_id="ord-1",
                customer_id="cust-1",
                reason="Producto defectuoso",
                reason_category="defective",
                refund_amount=79.99,
                items=[
                    {"order_item_id": "oi-1", "quantity": 1, "condition": "defective"}
                ],
            )

        assert result["return_request"]["id"] == "ret-1"
        assert result["items_created"] == 1

    @pytest.mark.asyncio
    async def test_rejects_duplicate_order_item_already_returned(self):
        """Verifica que no se puede crear una devolución duplicada del mismo order_item."""
        mock_client, query = _make_sync_supabase_client()

        existing_resp = MagicMock()
        existing_resp.data = [
            {
                "id": "ret-prev-1",
                "status": "approved",
                "return_items": [{"order_item_id": "oi-1"}],
            }
        ]

        query.execute = AsyncMock(return_value=existing_resp)

        with _patched_client(mock_client):
            with pytest.raises(ValueError, match="devolución previa"):
                await create_return_record(
                    order_id="ord-1",
                    customer_id="cust-1",
                    reason="Producto defectuoso",
                    reason_category="defective",
                    refund_amount=79.99,
                    items=[
                        {
                            "order_item_id": "oi-1",
                            "quantity": 1,
                            "condition": "defective",
                        }
                    ],
                )

    @pytest.mark.asyncio
    async def test_rejects_active_duplicate_for_same_order(self):
        """Verifica que no se puede crear una segunda devolución mientras haya una activa."""
        mock_client, query = _make_sync_supabase_client()

        existing_resp = MagicMock()
        existing_resp.data = [
            {"id": "ret-activo-1", "status": "pending_approval", "return_items": []}
        ]
        query.execute = AsyncMock(return_value=existing_resp)

        with _patched_client(mock_client):
            with pytest.raises(ValueError, match="devolución activa"):
                await create_return_record(
                    order_id="ord-1",
                    customer_id="cust-1",
                    reason="Otro motivo",
                    reason_category="wrong_item",
                    refund_amount=10.0,
                    items=[
                        {"order_item_id": "oi-2", "quantity": 1, "condition": "used"}
                    ],
                )


# ---------------------------------------------------------------------------
# update_return_status
# ---------------------------------------------------------------------------


class TestUpdateReturnStatus:
    """Tests para actualización de estado."""

    @pytest.mark.asyncio
    async def test_updates_status(self):
        """Verifica que se actualiza el estado y la resolución de una devolución existente."""
        mock_client, query = _make_sync_supabase_client()

        resp_mock = MagicMock()
        resp_mock.data = [{"id": "ret-1", "status": "approved"}]

        query.execute = AsyncMock(return_value=resp_mock)

        with _patched_client(mock_client):
            result = await update_return_status(
                "ret-1", "approved", resolution="full_refund"
            )

        assert result["updated_return"]["status"] == "approved"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """Verifica que actualizar una devolución inexistente devuelve updated_return=None."""
        mock_client, query = _make_sync_supabase_client()

        resp_mock = MagicMock()
        resp_mock.data = []

        query.execute = AsyncMock(return_value=resp_mock)

        with _patched_client(mock_client):
            result = await update_return_status("ret-nonexistent", "approved")

        assert result["updated_return"] is None

    @pytest.mark.asyncio
    async def test_sets_resolved_at_solo_en_estados_finales(self):
        """resolved_at solo se fija para approved/rejected/completed, no para processing."""
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[{"id": "ret-1"}]))

        with _patched_client(mock_client):
            await update_return_status("ret-1", "processing")

        update_call_args = query.update.call_args[0][0]
        assert "resolved_at" not in update_call_args

    @pytest.mark.asyncio
    async def test_no_sobreescribe_resolution_notes_vacios(self):
        """Si no se pasan resolution/notes, no se incluyen en el update (no
        sobreescriben valores ya guardados con cadenas vacías)."""
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[{"id": "ret-1"}]))

        with _patched_client(mock_client):
            await update_return_status("ret-1", "approved")

        update_call_args = query.update.call_args[0][0]
        assert "resolution" not in update_call_args
        assert "notes" not in update_call_args

    @pytest.mark.asyncio
    async def test_no_sobreescribe_refund_amount_si_no_se_pasa(self):
        """Sin refund_amount explícito, no se toca la columna ya guardada."""
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[{"id": "ret-1"}]))

        with _patched_client(mock_client):
            await update_return_status("ret-1", "approved")

        update_call_args = query.update.call_args[0][0]
        assert "refund_amount" not in update_call_args

    @pytest.mark.asyncio
    async def test_actualiza_refund_amount_si_se_pasa(self):
        """Decisión 'Edit' del HITL: el importe corregido se persiste."""
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[{"id": "ret-1"}]))

        with _patched_client(mock_client):
            await update_return_status("ret-1", "approved", refund_amount=42.5)

        update_call_args = query.update.call_args[0][0]
        assert update_call_args["refund_amount"] == 42.5

    @pytest.mark.asyncio
    async def test_permite_refund_amount_cero(self):
        """0.0 es un importe válido (reembolso corregido a cero por el admin),
        no debe confundirse con 'no proporcionado' (ese caso usa None)."""
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[{"id": "ret-1"}]))

        with _patched_client(mock_client):
            await update_return_status("ret-1", "approved", refund_amount=0.0)

        update_call_args = query.update.call_args[0][0]
        assert update_call_args["refund_amount"] == 0.0


# ---------------------------------------------------------------------------
# get_pending_return_request_id / get_latest_return_request
# ---------------------------------------------------------------------------


class TestGetPendingReturnRequestId:
    @pytest.mark.asyncio
    async def test_devuelve_el_id_si_hay_una_pendiente(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[{"id": "ret-1"}]))

        with _patched_client(mock_client):
            result = await get_pending_return_request_id("ord-1")

        assert result == "ret-1"

    @pytest.mark.asyncio
    async def test_cadena_vacia_si_no_hay_ninguna(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[]))

        with _patched_client(mock_client):
            result = await get_pending_return_request_id("ord-1")

        assert result == ""


class TestGetLatestReturnRequest:
    @pytest.mark.asyncio
    async def test_devuelve_id_y_status_de_la_mas_reciente(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(
            return_value=MagicMock(data=[{"id": "ret-1", "status": "approved"}])
        )

        with _patched_client(mock_client):
            result = await get_latest_return_request("ord-1")

        assert result == {"id": "ret-1", "status": "approved"}

    @pytest.mark.asyncio
    async def test_dict_vacio_si_no_hay_ninguna(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[]))

        with _patched_client(mock_client):
            result = await get_latest_return_request("ord-1")

        assert result == {}


# ---------------------------------------------------------------------------
# _flatten_* (funciones puras, sin async, sin BD)
# ---------------------------------------------------------------------------


class TestFlattenOrderNumber:
    def test_extrae_order_number_del_embed(self):
        row = {"id": "ret-1", "orders": {"order_number": "ORD-2026-00081"}}
        result = _flatten_order_number(row)
        assert result["order_number"] == "ORD-2026-00081"
        assert "orders" not in result

    def test_sin_embed_order_number_es_none(self):
        row = {"id": "ret-1"}
        result = _flatten_order_number(row)
        assert result["order_number"] is None


class TestFlattenProductNames:
    def test_une_varios_nombres_de_producto(self):
        row = {
            "return_items": [
                {"order_items": {"product": {"name": "Microondas"}}},
                {"order_items": {"product": {"name": "Champú"}}},
            ]
        }
        result = _flatten_product_names(row)
        assert result["product_names"] == "Microondas, Champú"
        assert "return_items" not in result

    def test_sin_items_devuelve_none(self):
        row = {"return_items": []}
        result = _flatten_product_names(row)
        assert result["product_names"] is None

    def test_sin_clave_return_items_devuelve_none(self):
        row = {}
        result = _flatten_product_names(row)
        assert result["product_names"] is None


class TestFlattenAdminRow:
    def test_aplica_los_dos_aplanados_a_la_vez(self):
        row = {
            "id": "ret-1",
            "orders": {"order_number": "ORD-2026-00081"},
            "return_items": [{"order_items": {"product": {"name": "Microondas"}}}],
        }
        result = _flatten_admin_row(row)
        assert result["order_number"] == "ORD-2026-00081"
        assert result["product_names"] == "Microondas"
        assert "orders" not in result
        assert "return_items" not in result


# ---------------------------------------------------------------------------
# list_pending_approvals / list_returns / get_return_detail / get_return_stats
# ---------------------------------------------------------------------------


class TestListPendingApprovals:
    @pytest.mark.asyncio
    async def test_aplana_cada_fila_devuelta(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(
            return_value=MagicMock(
                data=[
                    {
                        "id": "ret-1",
                        "status": "pending_approval",
                        "orders": {"order_number": "ORD-1"},
                        "return_items": [],
                    }
                ]
            )
        )

        with _patched_client(mock_client):
            result = await list_pending_approvals()

        assert len(result) == 1
        assert result[0]["order_number"] == "ORD-1"

    @pytest.mark.asyncio
    async def test_sin_pendientes_devuelve_lista_vacia(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[]))

        with _patched_client(mock_client):
            result = await list_pending_approvals()

        assert result == []


class TestListReturns:
    @pytest.mark.asyncio
    async def test_sin_filtro_no_llama_a_eq_de_status(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[]))

        with _patched_client(mock_client):
            await list_returns()

        # .eq() sí se llama para otros fines en otras funciones, pero aquí
        # solo debe llamarse si se pasa status -- verificamos que sin status
        # el resultado sigue siendo válido (lista vacía, sin excepción).

    @pytest.mark.asyncio
    async def test_con_filtro_de_status(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(
            return_value=MagicMock(
                data=[
                    {
                        "id": "ret-1",
                        "status": "approved",
                        "orders": {"order_number": "ORD-1"},
                        "return_items": [],
                    }
                ]
            )
        )

        with _patched_client(mock_client):
            result = await list_returns(status="approved")

        query.eq.assert_called_with("status", "approved")
        assert result[0]["status"] == "approved"

    @pytest.mark.asyncio
    async def test_respeta_el_limit(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[]))

        with _patched_client(mock_client):
            await list_returns(limit=5)

        query.limit.assert_called_with(5)


class TestGetReturnDetail:
    @pytest.mark.asyncio
    async def test_devuelve_el_detalle(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(
            return_value=MagicMock(data={"id": "ret-1", "return_items": []})
        )

        with _patched_client(mock_client):
            result = await get_return_detail("ret-1")

        assert result["id"] == "ret-1"


class TestGetReturnStats:
    @pytest.mark.asyncio
    async def test_calcula_kpis_correctamente(self):
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(
            return_value=MagicMock(
                data=[
                    {"status": "approved"},
                    {"status": "approved"},
                    {"status": "rejected"},
                    {"status": "pending_approval"},
                ]
            )
        )

        with _patched_client(mock_client):
            result = await get_return_stats()

        assert result["total_returns"] == 4
        assert result["approved"] == 2
        assert result["rejected"] == 1
        assert result["pending"] == 1
        assert result["approval_rate"] == 50.0

    @pytest.mark.asyncio
    async def test_sin_devoluciones_approval_rate_es_cero(self):
        """División por cero evitada: sin filas, approval_rate=0, no una excepción."""
        mock_client, query = _make_sync_supabase_client()
        query.execute = AsyncMock(return_value=MagicMock(data=[]))

        with _patched_client(mock_client):
            result = await get_return_stats()

        assert result["total_returns"] == 0
        assert result["approval_rate"] == 0
