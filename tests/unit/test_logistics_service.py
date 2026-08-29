"""Tests unitarios para backend.services.logistics_service."""

import json
import pytest
from pathlib import Path

from backend.services.logistics_service import (
    generate_shipping_label,
    send_customer_notification,
    LABELS_DIR,
)


class TestGenerateShippingLabel:
    """Tests para generación de etiquetas PDF."""

    @pytest.mark.asyncio
    async def test_generates_pdf_file(self, tmp_path, monkeypatch):
        """Verifica que se crea un PDF en disco."""
        monkeypatch.setattr("backend.services.logistics_service.LABELS_DIR", tmp_path)

        result = await generate_shipping_label(
            order_id="ord-001-uuid",
            items=[{"name": "Auriculares", "quantity": 1}],
            customer_name="Ana García",
        )

        assert result["tracking_number"].startswith("RF-")
        assert result["items_count"] == 1
        assert result["order_id"] == "ord-001-uuid"

        # Verificar que el archivo PDF existe
        label_path = Path(result["label_path"])
        assert label_path.exists()
        assert label_path.suffix == ".pdf"

    @pytest.mark.asyncio
    async def test_tracking_number_is_unique(self, tmp_path, monkeypatch):
        """Dos llamadas generan tracking numbers diferentes."""
        monkeypatch.setattr("backend.services.logistics_service.LABELS_DIR", tmp_path)

        result1 = await generate_shipping_label(
            order_id="ord-001", items=[{"name": "Item", "quantity": 1}]
        )
        result2 = await generate_shipping_label(
            order_id="ord-001", items=[{"name": "Item", "quantity": 1}]
        )

        assert result1["tracking_number"] != result2["tracking_number"]

    @pytest.mark.asyncio
    async def test_handles_empty_items(self, tmp_path, monkeypatch):
        """Funciona con lista vacía de items."""
        monkeypatch.setattr("backend.services.logistics_service.LABELS_DIR", tmp_path)

        result = await generate_shipping_label(order_id="ord-001", items=[])

        assert result["items_count"] == 0
        assert Path(result["label_path"]).exists()

    @pytest.mark.asyncio
    async def test_truncates_long_address(self, tmp_path, monkeypatch):
        """No falla con direcciones largas."""
        monkeypatch.setattr("backend.services.logistics_service.LABELS_DIR", tmp_path)

        long_address = "A" * 200
        result = await generate_shipping_label(
            order_id="ord-001",
            items=[{"name": "Item", "quantity": 1}],
            customer_address=long_address,
        )

        assert result["tracking_number"].startswith("RF-")


class TestSendCustomerNotification:
    """Tests para envío simulado de notificaciones."""

    @pytest.mark.asyncio
    async def test_returns_simulated_status(self, tmp_path, monkeypatch):
        """Verifica que devuelve status sent_simulated."""
        monkeypatch.setattr("backend.services.logistics_service.LABELS_DIR", tmp_path)

        result = await send_customer_notification(
            email="test@example.com",
            message="Tu devolución ha sido aprobada.",
            subject="Devolución aprobada",
        )

        assert result["status"] == "sent_simulated"
        assert result["to"] == "test@example.com"
        assert "notification_id" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_writes_to_log_file(self, tmp_path, monkeypatch):
        """Verifica que se escribe en el log JSONL."""
        monkeypatch.setattr("backend.services.logistics_service.LABELS_DIR", tmp_path)

        await send_customer_notification(
            email="log@example.com",
            message="Test message",
        )

        log_file = tmp_path / "notifications_log.jsonl"
        assert log_file.exists()

        with open(log_file) as f:
            entry = json.loads(f.readline())

        assert entry["to"] == "log@example.com"
        assert entry["status"] == "sent_simulated"

    @pytest.mark.asyncio
    async def test_appends_multiple_entries(self, tmp_path, monkeypatch):
        """Múltiples envíos se acumulan en el log."""
        monkeypatch.setattr("backend.services.logistics_service.LABELS_DIR", tmp_path)

        await send_customer_notification(email="a@b.com", message="msg1")
        await send_customer_notification(email="c@d.com", message="msg2")

        log_file = tmp_path / "notifications_log.jsonl"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2
