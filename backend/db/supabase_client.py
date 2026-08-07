"""
Supabase client connection setup.

Required environment variables (from .env):
- SUPABASE_API_URL: Project URL (e.g., https://<project-id>.supabase.co)
- SUPABASE_SERVICE_KEY: Service role key (full access, server-side only)
- SUPABASE_DB_URL: PostgreSQL pooler URL (used by LangGraph checkpointer)
"""

# lru_cache: decorador que memoriza el resultado de una función según sus
# argumentos; aquí se usa sin argumentos para crear un singleton "perezoso".
from functools import lru_cache
from typing import Optional

# BaseSettings (pydantic-settings): clase que lee y valida variables de
# entorno / archivo .env automáticamente a partir de los nombres de los campos.
from pydantic_settings import BaseSettings
# AsyncClient: cliente asíncrono oficial de Supabase.
# create_async_client: función fábrica que lo instancia y autentica.
from supabase import AsyncClient, create_async_client


class SupabaseSettings(BaseSettings):
    """Settings for Supabase connection loaded from .env."""

    # Los nombres de los campos (en minúscula) se mapean automáticamente a
    # las variables de entorno en mayúsculas: supabase_api_url <-> SUPABASE_API_URL.
    supabase_api_url: str
    supabase_service_key: str
    # Opcional: solo se necesita si se usa el checkpointer de PostgreSQL.
    supabase_db_url: Optional[str] = None

    # env_file: de dónde leer si la variable no está ya en el entorno real.
    # extra="ignore": no falla si el .env tiene claves que no están en esta clase.
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> SupabaseSettings:
    """Return cached Supabase settings."""
    # Al estar decorada con @lru_cache, esta instancia solo se construye
    # (y solo se lee el .env) la primera vez que se llama; las siguientes
    # llamadas devuelven el mismo objeto ya creado.
    return SupabaseSettings()


# Singleton perezoso: antes de la auditoria de ramas (ver doc/AUDITORIA_RAMAS.md),
# mcp_supabase.py y backend/services/supabase_service.py reimplementaban cada uno
# su propio cliente en vez de reusar esta funcion, y esta funcion ademas creaba
# una conexion nueva en cada llamada. Se centraliza aqui: un unico cliente por
# proceso, cacheado tras la primera llamada.
# Variable a nivel de módulo: vive mientras el proceso Python esté corriendo,
# compartida por todas las funciones que la usen (empieza sin cliente creado).
_client: Optional[AsyncClient] = None


async def get_supabase_client() -> AsyncClient:
    """Return the async Supabase client, creating it on first use."""
    # global: indica que se va a reasignar la variable del módulo, no crear
    # una variable local nueva llamada igual.
    global _client
    # Solo se entra aquí la primera vez que se llama a la función; en las
    # siguientes llamadas _client ya no es None y se salta directo al return.
    if _client is None:
        settings = get_settings()
        # create_async_client abre la conexión HTTP/autenticación con Supabase
        # usando la URL del proyecto y la clave de servicio (acceso total).
        _client = await create_async_client(
            supabase_url=settings.supabase_api_url,
            supabase_key=settings.supabase_service_key,
        )
    return _client
