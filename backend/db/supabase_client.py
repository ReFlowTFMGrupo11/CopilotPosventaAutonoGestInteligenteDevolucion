"""
Supabase client connection setup.

Required environment variables:
- SUPABASE_URL: Your Supabase project URL (e.g., https://<project-id>.supabase.co)
- SUPABASE_SERVICE_KEY: Service role key (full access, used server-side only)
"""

from functools import lru_cache

from pydantic_settings import BaseSettings
from supabase import AsyncClient, create_async_client


class SupabaseSettings(BaseSettings):
    """Settings for Supabase connection loaded from environment variables."""

    supabase_url: str
    supabase_service_key: str

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> SupabaseSettings:
    """Return cached Supabase settings."""
    return SupabaseSettings()


async def get_supabase_client() -> AsyncClient:
    """Create and return an async Supabase client."""
    settings = get_settings()
    client = await create_async_client(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_key,
    )
    return client
