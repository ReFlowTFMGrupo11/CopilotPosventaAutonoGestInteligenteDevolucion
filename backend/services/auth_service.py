"""Servicio de autenticación JWT.

Capa de lógica pura: no depende de FastAPI, MCP ni Supabase.
Su único trabajo es crear y verificar tokens JWT usando PyJWT.

Los consumidores son:
- ``backend/api/routers/auth.py``   → llama a ``create_token`` al hacer login.
- ``backend/api/dependencies.py``   → llama a ``verify_token`` en cada request
  protegido para extraer el ``customer_id`` / rol del token.

Estructura del payload de un token emitido:
    {
        "sub":  "CLI-001",       # customer_id (cliente) o "admin" (administrador)
        "role": "customer",      # "customer" | "admin"
        "iat":  1700000000,      # issued-at  (Unix timestamp, añadido por PyJWT)
        "exp":  1700028800,      # expiry     (Unix timestamp, añadido por PyJWT)
    }
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from backend.config import get_settings


class AuthError(Exception):
    """Excepción lanzada cuando un token JWT no es válido.

    Incluye un ``detail`` legible para que el consumidor (``dependencies.py``)
    pueda convertirla en una respuesta HTTP 401 con mensaje claro, sin
    mezclar lógica de HTTP aquí.

    Args:
        detail: Descripción del motivo del fallo (token expirado, firma
            inválida, secret no configurado, etc.).
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def create_token(subject: str, role: str) -> str:
    """Genera un token JWT firmado con ``JWT_SECRET``.

    Args:
        subject: Identificador del portador del token. Para clientes,
            el ``customer_id`` (p. ej. ``"CLI-001"``); para el admin,
            la cadena ``"admin"``.
        role: Rol del portador. ``"customer"`` o ``"admin"``. El rol
            queda grabado en el payload y se verifica en cada request
            protegido por ``require_authenticated_customer`` /
            ``require_admin`` (``backend/api/dependencies.py``).

    Returns:
        Token JWT como string (``"eyJhbGci..."``) listo para devolver
        al cliente en el response del login.

    Raises:
        AuthError: Si ``JWT_SECRET`` no está configurado en el entorno
            (campo ``jwt_secret`` de ``Settings`` es ``None``).
    """
    settings = get_settings()

    if settings.jwt_secret is None:
        raise AuthError(
            "JWT_SECRET no está configurado. "
            "Genera un valor con 'openssl rand -hex 32' y ponlo en .env."
        )

    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expiry_hours),
    }

    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def verify_token(token: str) -> dict:
    """Decodifica y valida un token JWT.

    Verifica la firma contra ``JWT_SECRET`` y comprueba que el token
    no ha expirado. PyJWT hace ambas comprobaciones en una sola llamada.

    Args:
        token: El token JWT en crudo, tal como llega en el header
            ``Authorization: Bearer <token>``.

    Returns:
        Payload decodificado como dict, con al menos las claves
        ``"sub"`` (identificador del portador) y ``"role"``.

    Raises:
        AuthError: Si el token está expirado, tiene firma inválida,
            está malformado, o ``JWT_SECRET`` no está configurado.
    """
    settings = get_settings()

    if settings.jwt_secret is None:
        raise AuthError(
            "JWT_SECRET no está configurado. "
            "Genera un valor con 'openssl rand -hex 32' y ponlo en .env."
        )

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise AuthError("El token ha expirado. Vuelve a iniciar sesión.")
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"Token inválido: {exc}")

    return payload
