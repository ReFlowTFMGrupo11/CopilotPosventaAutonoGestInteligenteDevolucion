"""Router de autenticación: emisión de tokens JWT.

Dos endpoints:
- POST /api/auth/login         → cliente se autentica con su email.
- POST /api/auth/admin/login   → admin se autentica con contraseña.

La lógica de firma/verificación de tokens vive en
``backend/services/auth_service.py`` (capa pura, sin dependencias de FastAPI).
Este router es la capa HTTP fina: recibe credenciales, delega en auth_service,
devuelve el token o el error HTTP correspondiente.

Flujo del cliente:
    1. POST /api/auth/login  { "email": "ana.garcia@email.com" }
    2. FastAPI busca el email en la tabla ``customers`` de Supabase.
    3. Si existe → create_token(customer_id, "customer") → { "token": "eyJ..." }
    4. Streamlit guarda el token en st.session_state["token"].
    5. Todas las llamadas siguientes llevan Authorization: Bearer <token>.

Flujo del admin:
    1. POST /api/auth/admin/login  { "password": "..." }
    2. FastAPI compara con ADMIN_PASSWORD del entorno.
    3. Si coincide → create_token("admin", "admin") → { "token": "eyJ..." }
"""

from fastapi import APIRouter, HTTPException

from backend.api.schemas import AdminLoginRequest, CustomerLoginRequest, TokenResponse
from backend.config import get_settings
from backend.db.supabase_client import get_supabase_client
from backend.services.auth_service import AuthError, create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def customer_login(request: CustomerLoginRequest):
    """Autentica a un cliente por email y devuelve un token JWT.

    No requiere contraseña: el email actúa como identificador único
    (columna ``email UNIQUE`` en la tabla ``customers``). En un sistema
    de producción real se sustituiría por Supabase Auth o similar.

    Args:
        request: Body con el campo ``email``.

    Returns:
        ``TokenResponse`` con el token JWT y el ``customer_id`` del cliente.

    Raises:
        HTTPException 401: Si el email no existe en la tabla ``customers``.
        HTTPException 500: Si ``JWT_SECRET`` no está configurado en el entorno.
    """
    client = await get_supabase_client()
    result = (
        await client.table("customers")
        .select("id, full_name")
        .eq("email", request.email)
        .execute()
    )

    if not result.data:
        # Mismo mensaje tanto para "email no existe" como para cualquier otro
        # fallo de búsqueda: no revelar qué emails están registrados.
        raise HTTPException(
            status_code=401,
            detail="Email no encontrado. Comprueba que es el email con el que realizaste tu compra.",
        )

    customer = result.data[0]

    try:
        token = create_token(subject=customer["id"], role="customer")
    except AuthError as exc:
        raise HTTPException(status_code=500, detail=exc.detail)

    return TokenResponse(token=token, customer_id=customer["id"])


@router.post("/admin/login", response_model=TokenResponse)
async def admin_login(request: AdminLoginRequest):
    """Autentica al administrador por contraseña y devuelve un token JWT.

    La contraseña se compara con ``ADMIN_PASSWORD`` del entorno (ver .env.example).
    No hay tabla de usuarios admin: hay un único administrador para el TFM.

    Args:
        request: Body con el campo ``password``.

    Returns:
        ``TokenResponse`` con el token JWT de admin (``customer_id`` es None).

    Raises:
        HTTPException 401: Si la contraseña no coincide con ``ADMIN_PASSWORD``.
        HTTPException 500: Si ``ADMIN_PASSWORD`` o ``JWT_SECRET`` no están configurados.
    """
    settings = get_settings()

    if settings.admin_password is None:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_PASSWORD no está configurada. Añádela al .env.",
        )

    if request.password != settings.admin_password.get_secret_value():
        raise HTTPException(status_code=401, detail="Contraseña incorrecta.")

    try:
        token = create_token(subject="admin", role="admin")
    except AuthError as exc:
        raise HTTPException(status_code=500, detail=exc.detail)

    return TokenResponse(token=token, customer_id=None)
