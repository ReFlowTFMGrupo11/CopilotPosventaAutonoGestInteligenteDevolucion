"""Fixtures compartidos para todos los tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_order_details():
    """Pedido de ejemplo con un artículo de electrónica."""
    return {
        "order": {
            "id": "ord-001-uuid",
            "status": "delivered",
            "delivered_at": "2026-07-25T10:00:00Z",
            "created_at": "2026-07-20T08:00:00Z",
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
        ] + [
            {"id": "ret-7", "status": "rejected", "refund_amount": 0.0}
        ],
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
def mock_supabase_client():
    """Cliente Supabase completamente mockeado."""
    return AsyncMock()


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
