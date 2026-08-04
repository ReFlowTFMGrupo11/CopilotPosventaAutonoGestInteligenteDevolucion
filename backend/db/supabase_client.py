"""
Supabase client connection setup.

Required environment variables:
- SUPABASE_URL: Your Supabase project URL (e.g., https://<project-id>.supabase.co)
- SUPABASE_SERVICE_KEY: Service role key (full access, used server-side only)
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings
from supabase import AsyncClient, create_async_client


class SupabaseSettings(BaseSettings):
    """Settings for Supabase connection loaded from environment variables."""

    supabase_url: str
    supabase_service_key: str

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> SupabaseSettings:
    """Return cached Supabase settings."""
    return SupabaseSettings()


# Singleton perezoso: antes de la auditoria de ramas (ver doc/AUDITORIA_RAMAS.md),
# mcp_supabase.py y backend/services/supabase_service.py reimplementaban cada uno
# su propio cliente en vez de reusar esta funcion, y esta funcion ademas creaba
# una conexion nueva en cada llamada. Se centraliza aqui: un unico cliente por
# proceso, cacheado tras la primera llamada.
_client: Optional[AsyncClient] = None


async def get_supabase_client() -> AsyncClient:
    """Return the async Supabase client, creating it on first use."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = await create_async_client(
            supabase_url=settings.supabase_url,
            supabase_key=settings.supabase_service_key,
        )
    return _client
