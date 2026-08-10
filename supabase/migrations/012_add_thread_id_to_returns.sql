-- Añadir thread_id de LangGraph a return_requests para vincular el grafo con la BD.
ALTER TABLE return_requests ADD COLUMN IF NOT EXISTS thread_id TEXT;
CREATE INDEX IF NOT EXISTS idx_returns_thread ON return_requests(thread_id);
