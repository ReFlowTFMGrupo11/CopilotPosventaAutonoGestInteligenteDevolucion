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
