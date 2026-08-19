-- =============================================================================
-- Migration 013: add optional filter_category parameter to match_policy_embeddings
-- =============================================================================
-- Problem: the original function searched ALL chunks across ALL categories.
-- If two categories have similar policy text, a query for "alimentacion" could
-- return a high-similarity chunk from "mascotas" or "drogueria_salud".
--
-- Fix: add a nullable filter_category parameter.
--   - NULL (default) → original behaviour, searches all chunks (e.g. marco general)
--   - "alimentacion"  → restricts to chunks where metadata->>'category' matches,
--     so the agent only retrieves chunks from the relevant policy document.
--
-- The filter uses metadata->>'category' (stored by ingest_policy_embeddings.py)
-- rather than a JOIN through policy_id → return_policies, so it stays
-- self-contained and works even for the marco general (policy_id IS NULL).
-- =============================================================================

CREATE OR REPLACE FUNCTION match_policy_embeddings(
    query_embedding  VECTOR(1536),
    match_threshold  FLOAT   DEFAULT 0.7,
    match_count      INT     DEFAULT 5,
    filter_category  TEXT    DEFAULT NULL
)
RETURNS TABLE (
    id          UUID,
    policy_id   UUID,
    chunk_text  TEXT,
    similarity  FLOAT
)
LANGUAGE sql STABLE
AS $$
    SELECT
        pe.id,
        pe.policy_id,
        pe.chunk_text,
        1 - (pe.embedding <=> query_embedding) AS similarity
    FROM policy_embeddings pe
    WHERE
        1 - (pe.embedding <=> query_embedding) > match_threshold
        AND (
            filter_category IS NULL
            OR pe.metadata->>'category' = filter_category
            -- Always include marco general chunks (category = 'general')
            -- regardless of the requested category: they contain the legal
            -- baseline (14-day right of withdrawal, HITL threshold, Art. 103)
            -- that applies to all categories.
            OR pe.metadata->>'category' = 'general'
        )
    ORDER BY pe.embedding <=> query_embedding
    LIMIT match_count;
$$;
