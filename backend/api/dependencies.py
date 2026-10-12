"""Dependencias compartidas para los routers de FastAPI.

`get_graph()` usa `Request.app.state` para cachear el grafo, lo que permite
sustituirlo en tests con `app.dependency_overrides`.

`ThreadLockRegistry`/`GRAPH_RECURSION_LIMIT`/`GRAPH_TURN_TIMEOUT_SECONDS`/
`with_graph_limits()` vivían antes duplicados en `routers/chat.py` Y
`routers/admin.py` (no son endpoints, son infraestructura de concurrencia y
límites de ejecución del grafo que ambos routers necesitan) — movidos aquí
siguiendo la convención de FastAPI de que un `router.py` solo contiene
`APIRouter()` + *path operations*, no dependencias compartidas entre routers.
"""

import asyncio
import logging
import time

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.agents.graph import get_return_graph
from backend.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

# ── Autenticación (JWT de Supabase Auth) ─────────────────────────────────
#
# El cliente se autentica ante esta API presentando el JWT que Supabase
# Auth le emitió tras el login, en la cabecera "Authorization: Bearer <jwt>".
# Verificar aquí la firma (HS256 con SUPABASE_JWT_SECRET) es todo lo que
# hace falta — no hay que llamar a Supabase en cada petición, la firma se
# valida localmente con el secreto compartido.
#
# Sin SUPABASE_JWT_SECRET configurado, el comportamiento sigue el criterio
# "fail-open solo si es seguro" de graph.py (checkpointer): en development
# se degrada a autenticación desactivada con un warning (arranque local y
# tests siguen funcionando); en production se rechaza todo con 503 — una API
# desprotegida en producción es un error de configuración, no un modo válido.

_bearer_scheme = HTTPBearer(auto_error=False)

# Aviso único al arrancar (no por petición): sin esto, montar la API sin
# SUPABASE_JWT_SECRET parece "todo funciona" cuando en realidad cualquier
# cliente puede llamar a los endpoints protegidos.
if _settings.supabase_jwt_secret is None and _settings.environment != "production":
    logger.warning(
        "SUPABASE_JWT_SECRET no configurada: autenticación desactivada "
        "(solo aceptable en development)."
    )


class AuthenticatedCustomer:
    """Identidad del cliente extraída del JWT verificado.

    Attributes:
        user_id: ``sub`` del token (UUID del usuario en Supabase Auth).
        email: Email del usuario, si el token lo incluye.
    """

    def __init__(self, user_id: str, email: str | None = None):
        self.user_id = user_id
        self.email = email


async def require_authenticated_customer(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedCustomer | None:
    """Verifica el JWT de Supabase Auth antes de ejecutar el endpoint.

    Raises:
        HTTPException: 401 si falta la cabecera o el token es inválido o
            expirado; 503 en production sin ``SUPABASE_JWT_SECRET``.
    """
    jwt_secret = _settings.supabase_jwt_secret

    if jwt_secret is None:
        if _settings.environment == "production":
            # SUPABASE_JWT_SECRET no configurada en production es un error de
            # configuración del servidor, no una indisponibilidad temporal.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Autenticación no configurada (SUPABASE_JWT_SECRET ausente).",
            )
        return None  # development: autenticación desactivada

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta la cabecera Authorization: Bearer <token>.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            jwt_secret.get_secret_value(),
            algorithms=["HS256"],  # fijo: nunca aceptar "none" ni RS256 aquí
            options={"leeway": 10},  # 10 s de tolerancia a desfase de reloj
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sin 'sub' (identidad del usuario).",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AuthenticatedCustomer(user_id=sub, email=payload.get("email"))


# Explícito en vez de depender del default implícito de LangGraph (25).
# Fuente única en Settings (backend/config.py) — antes se definía por
# duplicado en chat.py Y admin.py con el mismo valor cada una, lo que
# permitía cambiar una sin la otra y desincronizarlas sin ningún aviso.
GRAPH_RECURSION_LIMIT = _settings.graph_recursion_limit

# Tiempo máximo para que el grafo complete un turno completo (todas las
# llamadas a LLM/MCP/BD que ese turno dispare). Si se agota, se cancela la
# tarea y se informa al cliente en vez de dejar la petición colgada. Sin
# esto, un `ainvoke`/`astream` colgado (LLM/MCP/BD sin responder) dejaba la
# petición esperando para siempre, sin ninguna excepción capturable.
GRAPH_TURN_TIMEOUT_SECONDS = _settings.graph_turn_timeout_seconds


async def get_graph(request: Request):
    """Devuelve el grafo compilado (singleton cacheado en app.state)."""
    if getattr(request.app.state, "graph", None) is None:
        request.app.state.graph = await get_return_graph()
    return request.app.state.graph


def with_graph_limits(config: dict) -> dict:
    """Añade el `recursion_limit` explícito a un config de LangGraph."""
    merged = dict(config)
    merged["recursion_limit"] = GRAPH_RECURSION_LIMIT
    return merged


# ── Lock por thread_id ──────────────────────────────────────────────────
#
# Si dos peticiones para el MISMO hilo llegan solapadas (doble clic, doble
# envío del frontend, reintento de red...), la segunda espera a que la
# primera termine en vez de invocar el grafo dos veces en paralelo sobre el
# mismo checkpoint. Sin esto, la segunda podía toparse con un estado a
# medias y devolver el mensaje genérico de "sigue pendiente de revisión"
# sin haber creado ningún registro en BD.
#
# ThreadLockRegistry en vez de un defaultdict(asyncio.Lock) plano: un dict
# así crece con cada thread_id nuevo y nunca se libera solo (una fuga de
# memoria lenta en un proceso de larga duración). El registro expulsa
# entradas inactivas (no locked() y sin uso reciente) cada vez que se pide
# un lock nuevo.
_THREAD_LOCK_TTL_SECONDS = 3600.0  # 1 hora sin actividad


class ThreadLockRegistry:
    """Registro de ``asyncio.Lock`` por ``thread_id`` con expulsión de
    entradas inactivas, para no crecer sin límite en un proceso de larga
    duración."""

    def __init__(self, ttl_seconds: float = _THREAD_LOCK_TTL_SECONDS) -> None:
        """Inicializa el registro vacío.

        Args:
            ttl_seconds: Tiempo de inactividad tras el cual una entrada
                (lock no adquirido) se considera obsoleta y se expulsa.
        """
        self._ttl = ttl_seconds
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_used: dict[str, float] = {}

    def get(self, thread_id: str) -> asyncio.Lock:
        """Devuelve el lock de ``thread_id``, creándolo si es la primera vez.

        De paso, expulsa entradas obsoletas del registro (ver `_evict_stale`).
        """
        self._evict_stale()
        self._last_used[thread_id] = time.monotonic()
        if thread_id not in self._locks:
            self._locks[thread_id] = asyncio.Lock()
        return self._locks[thread_id]

    def _evict_stale(self) -> None:
        """Elimina del registro los locks sin actividad reciente y no adquiridos."""
        now = time.monotonic()
        stale = [
            tid
            for tid, last_used in self._last_used.items()
            if now - last_used > self._ttl and not self._locks[tid].locked()
        ]
        for tid in stale:
            del self._locks[tid]
            del self._last_used[tid]


thread_locks = ThreadLockRegistry()
