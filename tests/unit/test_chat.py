"""Tests unitarios de backend/api/routers/chat.py.

Corresponde 1:1 con frontend/Chat.py (ver docs/defensaTFM/defenderFastAPI.md).
Usan dependency_overrides para inyectar un mock del grafo, de modo que NO
se necesita OpenAI, Supabase ni servidores MCP.
"""

import pytest
import time
from unittest.mock import MagicMock

import jwt as pyjwt
from pydantic import SecretStr

# ── Autenticación (JWT de Supabase Auth) ───────────────────────────────────
#
# Los tests parchean backend.api.dependencies._settings para que no
# dependan de si el .env local tiene (o no) SUPABASE_JWT_SECRET — mismo
# criterio de determinismo que _no_real_langfuse en conftest.py.

# ≥32 bytes: PyJWT >= 2.13 emite InsecureKeyLengthWarning con claves HMAC
# más cortas (RFC 7518 §3.2) y el ruido no aporta nada a estos tests.
_JWT_SECRET = "test-jwt-secret-0123456789abcdef"


def _auth_settings(monkeypatch, secret=None, environment="development"):
    """Fija un Settings bajo control del test en dependencies._settings."""
    settings = MagicMock()
    settings.supabase_jwt_secret = secret
    settings.environment = environment
    monkeypatch.setattr("backend.api.dependencies._settings", settings)
    return settings


def _make_token(
    secret=_JWT_SECRET,
    sub="cust-001-uuid",
    email="ana.garcia@example.com",
    exp_offset_seconds=3600,
    **extra_claims,
):
    """Firma un JWT HS256 como lo haría Supabase Auth tras el login."""
    now = int(time.time())
    payload = {"sub": sub, "email": email, "iat": now, "exp": now + exp_offset_seconds}
    payload.update(extra_claims)
    return pyjwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture(autouse=True)
def _auth_disabled_by_default(monkeypatch):
    """Fuerza "auth desactivada" en TODOS los tests de este módulo.

    Sin esto, el resultado de los tests clásicos de chat (test_send_message,
    test_create_chat...) dependería de si el .env local tiene o no
    SUPABASE_JWT_SECRET — un .env con el secreto los tumbaría con 401.
    Los tests de autenticación de más abajo vuelven a parchear _settings
    con sus propios valores vía _auth_settings().
    """
    _auth_settings(monkeypatch, secret=None, environment="development")


@pytest.mark.asyncio
async def test_send_message_auth_disabled_in_development(
    async_client, mock_graph, monkeypatch
):
    """Sin SUPABASE_JWT_SECRET en development, la auth queda desactivada."""
    _auth_settings(monkeypatch, secret=None, environment="development")

    async with async_client as client:
        resp = await client.post(
            "/api/chat",
            json={"thread_id": "test-thread-123", "message": "Hola"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_send_message_production_without_secret_rejects_everything(
    async_client, monkeypatch
):
    """En production sin secreto: error de configuración del servidor (500)."""
    _auth_settings(monkeypatch, secret=None, environment="production")

    async with async_client as client:
        resp = await client.post(
            "/api/chat",
            json={"thread_id": "test-thread-123", "message": "Hola"},
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_send_message_missing_token(async_client, monkeypatch):
    """Con el secreto configurado, una petición sin token recibe 401."""
    _auth_settings(monkeypatch, secret=SecretStr(_JWT_SECRET))

    async with async_client as client:
        resp = await client.post(
            "/api/chat",
            json={"thread_id": "test-thread-123", "message": "Hola"},
        )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_send_message_valid_token(async_client, mock_graph, monkeypatch):
    """Un JWT válido firmado con el secreto correcto da acceso al endpoint."""
    _auth_settings(monkeypatch, secret=SecretStr(_JWT_SECRET))

    async with async_client as client:
        resp = await client.post(
            "/api/chat",
            json={"thread_id": "test-thread-123", "message": "Hola"},
            headers={"Authorization": f"Bearer {_make_token()}"},
        )

    assert resp.status_code == 200
    mock_graph.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_message_expired_token(async_client, monkeypatch):
    """Un JWT expirado recibe 401, sin llegar a invocar el grafo."""
    _auth_settings(monkeypatch, secret=SecretStr(_JWT_SECRET))

    async with async_client as client:
        resp = await client.post(
            "/api/chat",
            json={"thread_id": "test-thread-123", "message": "Hola"},
            headers={"Authorization": f"Bearer {_make_token(exp_offset_seconds=-60)}"},
        )

    assert resp.status_code == 401
    assert "expirado" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_send_message_wrong_signature(async_client, monkeypatch):
    """Un JWT firmado con otro secreto recibe 401."""
    _auth_settings(monkeypatch, secret=SecretStr(_JWT_SECRET))

    async with async_client as client:
        resp = await client.post(
            "/api/chat",
            json={"thread_id": "test-thread-123", "message": "Hola"},
            headers={
                "Authorization": f"Bearer {_make_token(secret='otro-secreto-muy-distinto-y-largo')}"
            },
        )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_send_message_token_without_sub(async_client, monkeypatch):
    """Un JWT válido pero sin 'sub' no identifica al usuario: 401."""
    _auth_settings(monkeypatch, secret=SecretStr(_JWT_SECRET))

    async with async_client as client:
        resp = await client.post(
            "/api/chat",
            json={"thread_id": "test-thread-123", "message": "Hola"},
            headers={"Authorization": f"Bearer {_make_token(sub=None)}"},
        )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_chat_also_requires_token(async_client, monkeypatch):
    """La dependencia es del router: /new también queda protegida."""
    _auth_settings(monkeypatch, secret=SecretStr(_JWT_SECRET))

    async with async_client as client:
        resp = await client.post("/api/chat/new")

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_chat(async_client):
    """Verifica que crear un chat nuevo devuelve un thread_id con formato UUID."""
    async with async_client as client:
        resp = await client.post("/api/chat/new")

    assert resp.status_code == 200
    data = resp.json()
    assert "thread_id" in data
    assert len(data["thread_id"]) == 36  # UUID


@pytest.mark.asyncio
async def test_send_message(async_client, mock_graph):
    """Verifica que enviar un mensaje invoca al grafo y devuelve su respuesta."""
    async with async_client as client:
        resp = await client.post(
            "/api/chat",
            json={
                "thread_id": "test-thread-123",
                "message": "Quiero devolver mi pedido ORD-001",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["thread_id"] == "test-thread-123"
    assert data["response"] == "Devolución procesada correctamente."
    assert data["current_agent"] == "resolution"
    assert data["order_id"] == "ORD-001"
    assert data["is_eligible"] is True

    # Verificar que se llamó al grafo con los argumentos correctos
    mock_graph.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_message_graph_error(async_client, mock_graph):
    """Verifica que un error del grafo se propaga como 500 con el detalle del error."""
    mock_graph.ainvoke.side_effect = Exception("OpenAI timeout")

    async with async_client as client:
        resp = await client.post(
            "/api/chat",
            json={
                "thread_id": "test-thread-123",
                "message": "Hola",
            },
        )

    assert resp.status_code == 500
    assert "OpenAI timeout" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_send_message_missing_fields(async_client, mock_graph):
    """Verifica que falta el campo thread_id produce un 422 de validación."""
    async with async_client as client:
        resp = await client.post("/api/chat", json={"message": "Hola"})

    assert resp.status_code == 422  # Validation error (falta thread_id)


@pytest.mark.asyncio
async def test_get_chat_state(async_client, mock_graph):
    """Verifica que se puede consultar el estado actual de un thread del grafo."""
    state = MagicMock()
    state.values = {
        "current_agent": "triage",
        "order_id": "ORD-001",
        "customer_name": "Ana García",
        "is_eligible": None,
        "resolution": None,
        "refund_amount": None,
    }
    mock_graph.aget_state.return_value = state

    async with async_client as client:
        resp = await client.get("/api/chat/test-thread-123/state")

    assert resp.status_code == 200
    data = resp.json()
    assert data["thread_id"] == "test-thread-123"
    assert data["current_agent"] == "triage"
    assert data["order_id"] == "ORD-001"
