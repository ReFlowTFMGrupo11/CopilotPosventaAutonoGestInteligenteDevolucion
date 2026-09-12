"""
Supabase client connection setup.

Required environment variables (from .env):
- SUPABASE_URL: Project URL (e.g., https://<project-id>.supabase.co)
- SUPABASE_SERVICE_KEY: Service role key (full access, server-side only)
- SUPABASE_DB_URL: PostgreSQL pooler URL (used by LangGraph checkpointer)

Estas tres viven en el ``Settings`` centralizado de ``backend/config.py``
junto con el resto de env vars del backend. Son opcionales ahí (para no
acoplar la validación de Supabase a módulos no relacionados que también
usan ``Settings``, p. ej. ``llm_factory.py``); la validación de que
realmente estén configuradas ("falla rápido si faltan") vive aquí, en el
único sitio que de verdad las necesita: la creación del cliente.
"""

from typing import Optional

from supabase import AsyncClient, create_async_client

from backend.config import get_settings

# Singleton perezoso: antes de la auditoria de ramas (ver doc/AUDITORIA_RAMAS.md),
# mcp_supabase.py y la capa de servicios (hoy backend/services/orders_service.py,
# returns_service.py, policy_service.py) reimplementaban cada uno su propio
# cliente en vez de reusar esta funcion, y esta funcion ademas creaba
# una conexion nueva en cada llamada. Se centraliza aqui: un unico cliente por
# proceso, cacheado tras la primera llamada.
_client: Optional[AsyncClient] = None


async def get_supabase_client() -> AsyncClient:
    """Return the async Supabase client, creating it on first use."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_service_key:
            raise RuntimeError(
                "Supabase no configurado: faltan SUPABASE_URL y/o "
                "SUPABASE_SERVICE_KEY en el entorno/.env."
            )
        _client = await create_async_client(
            supabase_url=settings.supabase_url,
            supabase_key=settings.supabase_service_key.get_secret_value(),
        )
    return _client
