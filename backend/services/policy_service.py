"""
Servicio de políticas de devolución: consulta estructurada (`return_policies`)
y búsqueda semántica RAG (`policy_embeddings` vía pgvector). Contiene la
lógica que antes vivía dentro de las funciones `@mcp.tool()` de
backend/mcp/mcp_supabase.py.

Porqué esta capa existe (ver doc/AUDITORIA_RAMAS.md, punto 6): antes, la lógica de
negocio (qué tablas de Supabase consultar) estaba mezclada con el código de
transporte MCP. Con esta capa, mcp_supabase.py pasa a ser un wrapper fino que
solo traduce `@mcp.tool()` -> llamada a estas funciones; cualquier otro
consumidor (FastAPI, un script, un test) puede importar directamente desde
aquí sin tocar MCP.

Extraído de supabase_service.py (ver docs/REMAINING_TASKS.md #3): ese fichero
mezclaba pedidos, devoluciones y políticas/RAG bajo un nombre de tecnología,
no de dominio de negocio.
"""

from backend.config import get_settings
from backend.db.supabase_client import get_supabase_client

# ---------------------------------------------------------------------------
# Política estructurada (sin búsqueda vectorial)
# ---------------------------------------------------------------------------


async def get_policy_info(category: str) -> dict | None:
    """Consulta la fila estructurada de ``return_policies`` para una categoría.

    A diferencia de ``search_return_policy()``, NO genera ningún embedding ni
    ejecuta la búsqueda vectorial (`match_policy_embeddings`) — es una
    consulta directa a una tabla por su índice de categoría, sin llamada a la
    API de OpenAI. Existe para que el veto legal/determinista
    (``policy_rules.py::deterministic_check``, que solo necesita
    ``max_return_days``/``allowed_conditions``/``restocking_fee_percent``)
    pueda evaluarse SIN pagar el coste de la búsqueda RAG narrativa cuando el
    resultado ya está decidido de todos modos (ver
    docs/defensaTFM/defenderRAG.md §4.2 — evaluator_agent la usa como
    pre-check antes de decidir si hace falta la búsqueda narrativa + LLM).
    """
    if not category:
        return None
    client = await get_supabase_client()
    policy_resp = (
        await client.table("return_policies")
        .select("*")
        .eq("category", category)
        .eq("active", True)
        .single()
        .execute()
    )
    return policy_resp.data


# ---------------------------------------------------------------------------
# Búsqueda RAG de políticas
# ---------------------------------------------------------------------------


async def search_return_policy(
    query: str, category: str = "", thread_id: str = ""
) -> dict:
    """Realiza una búsqueda semántica RAG usando pgvector sobre la normativa de la tienda.

    Args:
        query: Texto de consulta para buscar en las políticas.
        category: Categoría opcional para filtrar políticas (e.g., "electronics").
        thread_id: id de conversación, solo para trazabilidad en LangFuse (no
            afecta a la búsqueda). Este servicio corre en el proceso del MCP
            server (mcp_supabase.py), no en el de la API, así que se registra
            el cliente LangFuse aquí explícitamente antes de usar
            langfuse.openai — si no, no habría ningún cliente autenticado en
            este proceso y la traza no se enviaría (ver
            get_langfuse_callback() en observability.py, mismo problema).
    """
    # Import local para no cargar los SDKs si esta función no se invoca.
    from backend.services.observability import get_langfuse

    lf = get_langfuse()
    # langfuse.openai es un drop-in de `openai` que traza la llamada
    # (tokens + coste) como una GENERATION en LangFuse; si no está
    # configurado, se usa el SDK de OpenAI normal y punto.
    if lf is not None:
        import langfuse.openai as openai
    else:
        import openai

    client = await get_supabase_client()

    api_key = get_settings().openai_api_key
    openai_client = openai.OpenAI(
        api_key=api_key.get_secret_value() if api_key else None
    )
    # Debe ser el mismo modelo de embedding usado al indexar las políticas.
    # `session_id` como kwarg rompe esta llamada (Embeddings.create() no lo
    # acepta y langfuse.openai no lo filtra para el recurso "embedding",
    # comprobado en real); por eso el thread_id va en `metadata`, que sí
    # está soportado -- la traza queda suelta (no anidada en el trace de la
    # conversación), pero es buscable/filtrable por thread_id igualmente.
    embedding_resp = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=query,
        name="rag_embedding",
        metadata={"thread_id": thread_id, "category": category},
    )
    query_embedding = embedding_resp.data[0].embedding

    rpc_params = {
        "query_embedding": query_embedding,
        "match_threshold": get_settings().rag_match_threshold,
        "match_count": 5,
        # Pass category as filter so the vector search only returns chunks from
        # the relevant policy document (+ marco general). Without this, a query
        # for "alimentacion" could return high-similarity chunks from "mascotas"
        # or "drogueria_salud" (all hygiene-sensitive categories share similar text).
        # NULL = search all chunks (backwards-compatible default in the SQL function).
        "filter_category": category if category else None,
    }
    results = await client.rpc("match_policy_embeddings", rpc_params).execute()

    policy_info = await get_policy_info(category)

    return {
        "query": query,
        "category": category,
        "semantic_results": results.data,
        "policy_info": policy_info,
    }
