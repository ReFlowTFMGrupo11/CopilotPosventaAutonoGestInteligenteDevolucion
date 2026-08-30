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
