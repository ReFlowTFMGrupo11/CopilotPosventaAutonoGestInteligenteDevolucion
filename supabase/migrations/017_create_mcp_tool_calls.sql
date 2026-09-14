-- Registro de éxito/fallo por llamada a una tool MCP.
--
-- Hasta ahora, si create_return_record/generate_shipping_label/etc.
-- fallaba, la excepción subía y en el mejor caso marcaba el TURNO completo
-- como "exception" (ver backend/services/observability.py::score_error) --
-- no quedaba ningún registro de QUÉ TOOL falló. "¿Qué tools fallan más?"
-- no tenía respuesta, ni en Langfuse ni en ningún otro sitio (hueco
-- identificado explícitamente en docs/defensaTFM/defenderLangfuse.md).
--
-- Instrumentado en el único punto de paso de las 10 tools MCP:
-- backend/agents/infra/mcp_client.py::call_tool() (ver
-- backend/services/tool_call_service.py, que lee/escribe esta tabla).
--
-- thread_id es NULLABLE a propósito: varios wrappers de mcp_client.py
-- (get_order_details, get_policy_info, update_return_status,
-- generate_shipping_label, send_customer_notification...) no reciben
-- thread_id en su firma hoy -- se extrae de forma oportunista de
-- args["thread_id"] cuando está presente (search_return_policy,
-- create_return_record), sin forzar a añadirlo en todos los wrappers solo
-- para esto. Sin thread_id, la fila sigue siendo útil para la agregación
-- por tool (error_rate/latencia), solo pierde la trazabilidad a la sesión.
CREATE TABLE IF NOT EXISTS mcp_tool_calls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id TEXT,
    tool_name TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_calls_tool_name ON mcp_tool_calls(tool_name);
CREATE INDEX IF NOT EXISTS idx_mcp_tool_calls_success ON mcp_tool_calls(success);
CREATE INDEX IF NOT EXISTS idx_mcp_tool_calls_created_at ON mcp_tool_calls(created_at DESC);
