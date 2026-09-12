"""Fixtures compartidos para todos los tests."""

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def _no_real_langfuse():
    """Evita que los tests llamen a LangFuse de verdad.

    Sin esto, cualquier test que ejercite un except real (p. ej.
    test_send_message_graph_error) hace un create_score/create_event real
    si el .env local tiene credenciales de LangFuse -- pasó exactamente
    eso: quedó un score con session_id="test-thread-123" en el proyecto de
    LangFuse Cloud real. Los tests no deben depender de qué haya (o no)
    en el .env local para ser deterministas y no ensuciar datos reales.
    """
    with patch("backend.services.observability.get_langfuse", return_value=None):
        yield


@pytest.fixture
def mock_order_details():
    """Pedido de ejemplo con un artículo de electrónica.

    Fechas relativas a "ahora" (no absolutas): con fechas fijas, este
    fixture se convierte en una bomba de relojería que deja de representar
    "entregado hace pocos días, dentro de plazo" en cuanto pasan suficientes
    días reales -- nos pasó (delivered_at="2026-07-25" acabó siendo >35 días
    en el pasado, tumbando test_eligible_return con
    "assert False is True" sin que nadie tocara evaluator.py).
    """
    delivered_at = datetime.now(timezone.utc) - timedelta(days=5)
    created_at = delivered_at - timedelta(days=5)
    return {
        "order": {
            "id": "ord-001-uuid",
            "status": "delivered",
            "delivered_at": delivered_at.isoformat(),
            "created_at": created_at.isoformat(),
            # Precalculado, como lo entregaría get_order_details() (MCP) de
            # verdad -- evaluator_agent ya no lo calcula él mismo, ver
            # orders_service.get_order_details().
            "days_since_delivery": 5,
            "customer": {
                "id": "cust-001-uuid",
                "email": "ana.garcia@example.com",
                "full_name": "Ana García",
            },
        },
        "items": [
            {
                "id": "oi-001-uuid",
                "order_id": "ord-001-uuid",
                "quantity": 1,
                "unit_price": 79.99,
                "product": {
                    "name": "Auriculares Bluetooth Pro",
                    "sku": "AUR-BT-001",
                    "category": "electronics",
                    "price": 79.99,
                    "weight_kg": 0.3,
                },
            },
            {
                "id": "oi-002-uuid",
                "order_id": "ord-001-uuid",
                "quantity": 2,
                "unit_price": 15.00,
                "product": {
                    "name": "Funda Protectora",
                    "sku": "FUN-001",
                    "category": "accessories",
                    "price": 15.00,
                    "weight_kg": 0.1,
                },
            },
        ],
    }


@pytest.fixture
def mock_return_history_clean():
    """Cliente sin devoluciones previas."""
    return {
        "customer_id": "cust-001-uuid",
        "total_returns": 0,
        "approved": 0,
        "rejected": 0,
        "returns": [],
    }


@pytest.fixture
def mock_return_history_suspicious():
    """Cliente con historial de devoluciones sospechoso (>5)."""
    return {
        "customer_id": "cust-002-uuid",
        "total_returns": 7,
        "approved": 6,
        "rejected": 1,
        "returns": [
            {"id": f"ret-{i}", "status": "approved", "refund_amount": 50.0}
            for i in range(6)
        ]
        + [{"id": "ret-7", "status": "rejected", "refund_amount": 0.0}],
    }


@pytest.fixture
def mock_policy_results():
    """Resultados de búsqueda RAG de políticas."""
    return {
        "query": "devolución defective auriculares",
        "category": "electronics",
        "semantic_results": [
            {
                "id": "pe-001",
                "policy_id": "pol-001",
                "chunk_text": "Los productos electrónicos defectuosos pueden devolverse en un plazo de 30 días desde la entrega.",
                "similarity": 0.91,
            },
            {
                "id": "pe-002",
                "policy_id": "pol-001",
                "chunk_text": "No se aplica cargo por restock en productos defectuosos.",
                "similarity": 0.85,
            },
        ],
        "policy_info": {
            "id": "pol-001",
            "category": "electronics",
            "max_return_days": 30,
            "requires_original_packaging": False,
            "restocking_fee_percent": 0.0,
            "allowed_conditions": ["unopened", "defective", "wrong_item"],
            "active": True,
        },
    }


@pytest.fixture
def mock_label_result():
    """Resultado de generación de etiqueta."""
    return {
        "tracking_number": "RF-ABC1234567",
        "label_path": "/tmp/generated_labels/label_RF-ABC1234567.pdf",
        "filename": "label_RF-ABC1234567.pdf",
        "order_id": "ord-001-uuid",
        "items_count": 1,
    }


@pytest.fixture
def sample_items_to_return():
    """Items que el cliente quiere devolver."""
    return [
        {
            "order_item_id": "oi-001-uuid",
            "quantity": 1,
            "condition": "defective",
        }
    ]


# ── Escenario: pedido con múltiples categorías y elegibilidad mixta ────────
#
# Un mismo pedido con dos artículos de categorías distintas, cada una regida
# por una política distinta (dataset/policies/01_electronica_informatica.md
# y dataset/policies/12_cosmetica_perfumeria.md):
#   - Auriculares (electronica_informatica): defectuosos, entregados hace 10
#     días, dentro del plazo de 30 días -> SÍ debería ser elegible.
#   - Perfume (cosmetica_perfumeria): el cliente simplemente cambió de
#     opinión y ya retiró el precinto de higiene -> NO debería ser elegible
#     (exclusión legal de higiene, aplica con independencia del plazo).


@pytest.fixture
def mock_order_details_mixed_categories():
    """Pedido con un artículo elegible (electrónica) y otro no elegible (cosmética).

    Fechas relativas a "ahora" (ver docstring de mock_order_details más
    arriba sobre por qué no deben ser absolutas): delivered_at = hace 10
    días, para que coincida con lo que dice el comentario de más abajo
    ("entregados hace 10 días, dentro del plazo de 30 días").
    """
    delivered_at = datetime.now(timezone.utc) - timedelta(days=10)
    created_at = delivered_at - timedelta(days=6)
    return {
        "order": {
            "id": "ord-mixed-uuid",
            "status": "delivered",
            "delivered_at": delivered_at.isoformat(),
            "created_at": created_at.isoformat(),
            # Precalculado, como lo entregaría get_order_details() (MCP) de
            # verdad -- evaluator_agent ya no lo calcula él mismo, ver
            # orders_service.get_order_details().
            "days_since_delivery": 10,
            "customer": {
                "id": "cust-mixed-uuid",
                "email": "laura.perez@example.com",
                "full_name": "Laura Pérez",
            },
        },
        "items": [
            {
                "id": "oi-electronics-uuid",
                "order_id": "ord-mixed-uuid",
                "quantity": 1,
                "unit_price": 79.99,
                "product": {
                    "name": "Auriculares Bluetooth Pro",
                    "sku": "AUR-BT-001",
                    "category": "electronica_informatica",
                    "price": 79.99,
                    "weight_kg": 0.3,
                },
            },
            {
                "id": "oi-cosmetics-uuid",
                "order_id": "ord-mixed-uuid",
                "quantity": 1,
                "unit_price": 45.00,
                "product": {
                    "name": "Perfume Eau de Parfum 100ml",
                    "sku": "PER-EDP-100",
                    "category": "cosmetica_perfumeria",
                    "price": 45.00,
                    "weight_kg": 0.2,
                },
            },
        ],
    }


@pytest.fixture
def sample_items_to_return_mixed():
    """El cliente pide devolver AMBOS artículos del pedido mixto."""
    return [
        {
            "order_item_id": "oi-electronics-uuid",
            "quantity": 1,
            "condition": "defective",
        },
        {"order_item_id": "oi-cosmetics-uuid", "quantity": 1, "condition": "used"},
    ]


@pytest.fixture
def mock_policy_results_electronics():
    """Resultado RAG para electrónica: devolución elegible dentro de plazo."""
    return {
        "query": "devolución defective auriculares",
        "category": "electronica_informatica",
        "policy_info": {
            "id": "pol-electronica",
            "category": "electronica_informatica",
            "max_return_days": 30,
            "requires_original_packaging": True,
            "restocking_fee_percent": 0.0,
            "allowed_conditions": [
                "unopened",
                "opened_tested",
                "defective",
                "wrong_item",
                "damaged_in_transit",
            ],
            "active": True,
        },
    }


@pytest.fixture
def mock_policy_results_cosmetics():
    """Resultado RAG para cosmética: exclusión de higiene tras retirar el precinto."""
    return {
        "query": "devolución cambio de opinión perfume",
        "category": "cosmetica_perfumeria",
        "policy_info": {
            "id": "pol-cosmetica",
            "category": "cosmetica_perfumeria",
            "max_return_days": 21,
            "requires_original_packaging": True,
            "hygiene_seal_required": True,
            "restocking_fee_percent": 0.0,
            "allowed_conditions": ["unopened", "defective", "wrong_item"],
            "active": True,
        },
    }
