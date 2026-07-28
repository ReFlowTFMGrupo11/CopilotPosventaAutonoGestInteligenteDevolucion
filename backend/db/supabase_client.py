"""
Supabase client connection setup.

Required environment variables:
- SUPABASE_URL: Your Supabase project URL (e.g., https://<project-id>.supabase.co)
- SUPABASE_SERVICE_KEY: Service role key (full access, used server-side only)
"""

# functools.lru_cache: decorador que memoriza el resultado de una función sin
# argumentos, para no recrear el objeto de configuración en cada llamada.
from functools import lru_cache

# BaseSettings: clase base de pydantic-settings que lee y valida variables de
# entorno (o un fichero .env) y las expone como atributos tipados.
from pydantic_settings import BaseSettings
# AsyncClient: tipo del cliente asíncrono de Supabase.
# create_async_client: función fábrica que instancia y autentica ese cliente.
from supabase import AsyncClient, create_async_client


class SupabaseSettings(BaseSettings):
    """Settings for Supabase connection loaded from environment variables."""

    # Campo obligatorio: se rellena desde la env var SUPABASE_URL
    # (pydantic-settings compara nombres de forma insensible a mayúsculas).
    supabase_url: str
    # Campo obligatorio: se rellena desde la env var SUPABASE_SERVICE_KEY.
    supabase_service_key: str

    # Indica a pydantic-settings que, además del entorno del proceso, lea
    # también el fichero .env (codificado en utf-8) si existe. extra="ignore"
    # es necesario porque el .env es compartido con otras partes del
    # proyecto (OPENAI_API_KEY, LABELS_OUTPUT_DIR) que no son campos de
    # este modelo; sin esto, pydantic-settings rechaza esas claves "extra".
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# lru_cache sin argumentos (maxsize por defecto) => actúa como un singleton:
# la primera llamada construye SupabaseSettings() (leyendo el entorno) y las
# siguientes devuelven el mismo objeto ya cacheado.
@lru_cache
def get_settings() -> SupabaseSettings:
    """Return cached Supabase settings."""
    return SupabaseSettings()


async def get_supabase_client() -> AsyncClient:
    """Create and return an async Supabase client."""
    # Recupera (o crea, la primera vez) la configuración cacheada.
    settings = get_settings()
    # Crea el cliente asíncrono de Supabase autenticado con la service_role
    # key, que da acceso total a la base de datos (uso exclusivo servidor).
    client = await create_async_client(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_key,
    )
    return client
