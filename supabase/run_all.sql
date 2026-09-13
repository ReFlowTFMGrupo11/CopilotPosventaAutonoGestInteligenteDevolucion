-- ==============================================================================
-- run_all.sql — Script de conveniencia: TODAS las migraciones en uno.
-- ==============================================================================
-- Generado concatenando, en orden, supabase/migrations/001_*.sql .. 015_*.sql.
-- La fuente de verdad de cada pieza es su fichero de origen en migrations/ —
-- este fichero es una copia derivada para poder pegar/ejecutar todo de una
-- vez en el SQL Editor de Supabase. Si se añade una migración nueva, hay que
-- regenerar este fichero (no editarlo a mano): concatenar de nuevo
-- migrations/*.sql en orden numérico.
--
-- Ya no incluye seed data: supabase/seed.sql (el seed pequeño de 3
-- clientes/5 productos) se eliminó porque duplicaba innecesariamente
-- supabase/seed_synthetic.sql y colisionaba con él en un order_number
-- (ORD-2026-00142). Para cargar datos de prueba tras ejecutar este fichero,
-- usa supabase/seed_synthetic.sql (ver data/README.md).
-- ==============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Customers table
CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT,
    address JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_customers_email ON customers(email);

-- Products table
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    weight_kg NUMERIC(6, 3),
    image_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_products_sku ON products(sku);
CREATE INDEX idx_products_category ON products(category);

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL REFERENCES customers(id),
    order_number TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'delivered',
    total_amount NUMERIC(10, 2) NOT NULL,
    shipping_address JSONB NOT NULL,
    ordered_at TIMESTAMPTZ NOT NULL,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_number ON orders(order_number);
CREATE INDEX idx_orders_status ON orders(status);

-- Order items table
CREATE TABLE IF NOT EXISTS order_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price NUMERIC(10, 2) NOT NULL,
    total_price NUMERIC(10, 2) NOT NULL
);

CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);

-- Return requests table
CREATE TABLE IF NOT EXISTS return_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES orders(id),
    customer_id UUID NOT NULL REFERENCES customers(id),
    status TEXT NOT NULL DEFAULT 'pending',
    reason TEXT NOT NULL,
    reason_category TEXT NOT NULL,
    resolution TEXT,
    refund_amount NUMERIC(10, 2),
    tracking_number TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

-- Allowed statuses: pending, approved, rejected, shipped, received, refunded, closed
CREATE INDEX idx_returns_order ON return_requests(order_id);
CREATE INDEX idx_returns_customer ON return_requests(customer_id);
CREATE INDEX idx_returns_status ON return_requests(status);

-- Return items (which products from the order are being returned)
CREATE TABLE IF NOT EXISTS return_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    return_request_id UUID NOT NULL REFERENCES return_requests(id) ON DELETE CASCADE,
    order_item_id UUID NOT NULL REFERENCES order_items(id),
    quantity INTEGER NOT NULL DEFAULT 1,
    condition TEXT NOT NULL DEFAULT 'unopened'
);

CREATE INDEX idx_return_items_request ON return_items(return_request_id);

-- Return policies table (used by agent to validate eligibility)
CREATE TABLE IF NOT EXISTS return_policies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category TEXT NOT NULL,
    max_return_days INTEGER NOT NULL DEFAULT 30,
    requires_original_packaging BOOLEAN DEFAULT FALSE,
    restocking_fee_percent NUMERIC(5, 2) DEFAULT 0,
    allowed_conditions TEXT[] DEFAULT ARRAY['unopened', 'defective', 'wrong_item'],
    policy_text TEXT NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_policies_category ON return_policies(category) WHERE active = TRUE;

-- Policy embeddings for RAG-based policy lookup
CREATE TABLE IF NOT EXISTS policy_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    policy_id UUID REFERENCES return_policies(id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    embedding VECTOR(1536) NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- IVFFlat index for fast cosine similarity search
CREATE INDEX idx_policy_embeddings_vector ON policy_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);

-- Chat sessions for conversation tracking
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID REFERENCES customers(id),
    status TEXT NOT NULL DEFAULT 'active',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'
);

-- Chat messages within a session
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chat_messages_session ON chat_messages(session_id);
CREATE INDEX idx_chat_sessions_customer ON chat_sessions(customer_id);

-- Function to search policy embeddings by similarity
CREATE OR REPLACE FUNCTION match_policy_embeddings(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    policy_id UUID,
    chunk_text TEXT,
    similarity FLOAT
)
LANGUAGE sql STABLE
AS $$
    SELECT
        pe.id,
        pe.policy_id,
        pe.chunk_text,
        1 - (pe.embedding <=> query_embedding) AS similarity
    FROM policy_embeddings pe
    WHERE 1 - (pe.embedding <=> query_embedding) > match_threshold
    ORDER BY pe.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- Triggers for updated_at
CREATE TRIGGER trg_customers_updated_at
    BEFORE UPDATE ON customers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_return_requests_updated_at
    BEFORE UPDATE ON return_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Añadir thread_id de LangGraph a return_requests para vincular el grafo con la BD.
ALTER TABLE return_requests ADD COLUMN IF NOT EXISTS thread_id TEXT;
CREATE INDEX IF NOT EXISTS idx_returns_thread ON return_requests(thread_id);

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

-- Registro de uso de LLM por petición: coste en tokens y latencia, para
-- monitorizar gasto por sesión/cliente/pedido en el panel admin (ver
-- backend/services/usage_service.py y frontend/pages/2_Costes.py).
--
-- customer_id/order_id son NULL en los turnos de triaje anteriores a
-- conocer el order_number del cliente (ver fetch_order_data en triage.py);
-- se rellenan a partir de que el pedido queda resuelto en el estado.
CREATE TABLE IF NOT EXISTS llm_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id TEXT NOT NULL,
    customer_id UUID REFERENCES customers(id),
    order_id UUID REFERENCES orders(id),
    node TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_thread ON llm_usage(thread_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_customer ON llm_usage(customer_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_order ON llm_usage(order_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at ON llm_usage(created_at DESC);

-- Elimina chat_sessions/chat_messages (creadas en 010_create_chat_sessions.sql).
--
-- Auditado (grep -rn "chat_sessions\|chat_messages" backend/ frontend/): ningún
-- nodo, router ni página del frontend lee o escribe estas tablas. Solo las
-- poblaba data/generate_dataset.py como muestra ilustrativa para el dataset
-- sintético de QA/seed -- nunca el chat en producción. El propósito original
-- ("dar contenido conversacional real con el que probar el futuro Agente de
-- Triaje", ver data/README.md histórico) ya está cubierto, y mejor, por
-- mecanismos que sí están en uso: el historial real de cada conversación vive
-- en el checkpointer de LangGraph (`checkpoints`/`checkpoint_writes`, ver
-- graph.py) y es trazable en Langfuse por `thread_id` = `langfuse_session_id`
-- (con tokens/coste/latencia que chat_messages nunca tuvo). Mantener una tabla
-- sin consumidor real solo añade superficie sin aportar nada -- ver
-- docs/defensaTFM/defenderAgentes.md §15.
--
-- No se elimina/edita 010_create_chat_sessions.sql (migraciones numeradas y
-- secuenciales: no se reescribe el historial, se añade una migración nueva
-- que deshace el efecto de la anterior).
DROP TABLE IF EXISTS chat_messages;
DROP TABLE IF EXISTS chat_sessions;

