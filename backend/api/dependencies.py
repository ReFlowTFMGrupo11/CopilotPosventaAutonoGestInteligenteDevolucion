"""Dependencias compartidas para los routers de FastAPI.

`get_graph()` usa `Request.app.state` para cachear el grafo, lo que permite
sustituirlo en tests con `app.dependency_overrides`.

`ThreadLockRegistry`/`GRAPH_RECURSION_LIMIT`/`GRAPH_TURN_TIMEOUT_SECONDS`/
`with_graph_limits()` vivían antes duplicados en `routers/chat.py` Y
`routers/admin.py` (no son endpoints, son infraestructura de concurrencia y
límites de ejecución del grafo que ambos routers necesitan) — movidos aquí
siguiendo la convención de FastAPI de que un `router.py` solo contiene
`APIRouter()` + *path operations*, no dependencias compartidas entre routers.

`require_authenticated_customer` / `require_admin` extraen y validan el token
JWT del header ``Authorization: Bearer <token>`` en cada request protegido.
La lógica de firma/verificación vive en ``backend/services/auth_service.py``;
estas funciones solo traducen ``AuthError`` → ``HTTPException`` para FastAPI.
En tests se sustituyen vía ``app.dependency_overrides`` (ver conftest.py).
"""

import asyncio
import time

from fastapi import Depends, HTTPException
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.agents.graph import get_return_graph
from backend.config import get_settings
from backend.services.auth_service import AuthError, verify_token

_settings = get_settings()

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


# ── Autenticación JWT ────────────────────────────────────────────────────
#
# HTTPBearer extrae automáticamente el token del header:
#   Authorization: Bearer eyJhbGci...
# y devuelve un objeto HTTPAuthorizationCredentials con `.credentials`
# conteniendo el token en crudo. Si el header falta o tiene formato incorrecto,
# FastAPI devuelve 403 antes de llegar a la función (auto_error=True por defecto).
#
# En tests, estas dependencias se sustituyen vía app.dependency_overrides:
#   app.dependency_overrides[require_authenticated_customer] = lambda: "customer-test-id"
#   app.dependency_overrides[require_admin] = lambda: True
# lo que evita tener que generar tokens reales en cada test.

_bearer = HTTPBearer()


async def require_authenticated_customer(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    """Valida el token JWT de un cliente y devuelve su ``customer_id``.

    Se usa con ``Depends(require_authenticated_customer)`` en los endpoints
    de ``routers/chat.py``. El valor devuelto (el ``customer_id``) queda
    disponible en el endpoint como parámetro inyectado por FastAPI.

    Args:
        credentials: Token Bearer extraído del header ``Authorization``
            por ``HTTPBearer``. FastAPI rechaza la petición con 403 antes
            de llegar aquí si el header no está presente.

    Returns:
        ``customer_id`` (campo ``sub`` del payload JWT).

    Raises:
        HTTPException 401: Si el token está expirado, tiene firma inválida,
            o su rol no es ``"customer"``.
    """
    try:
        payload = verify_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=exc.detail)

    if payload.get("role") != "customer":
        raise HTTPException(
            status_code=401,
            detail="Token inválido para este endpoint: se requiere rol 'customer'.",
        )

    return payload["sub"]  # customer_id


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> bool:
    """Valida el token JWT de administrador.

    Se usa con ``Depends(require_admin)`` en los endpoints de
    ``routers/admin.py``. Devuelve ``True`` si el token es válido y tiene
    rol ``"admin"``; el valor en sí no se suele usar, la dependencia
    actúa como guard.

    Args:
        credentials: Token Bearer extraído del header ``Authorization``
            por ``HTTPBearer``.

    Returns:
        ``True`` si el token de admin es válido.

    Raises:
        HTTPException 401: Si el token está expirado, tiene firma inválida,
            o su rol no es ``"admin"``.
    """
    try:
        payload = verify_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=exc.detail)

    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=401,
            detail="Token inválido para este endpoint: se requiere rol 'admin'.",
        )

    return True
