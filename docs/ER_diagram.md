```mermaid
erDiagram
    customers {
        UUID id PK
        TEXT email UK
        TEXT full_name
        TEXT phone
        JSONB address
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    products {
        UUID id PK
        TEXT sku UK
        TEXT name
        TEXT description
        TEXT category
        NUMERIC price
        NUMERIC weight_kg
        TEXT image_url
        TIMESTAMPTZ created_at
    }

    orders {
        UUID id PK
        UUID customer_id FK
        TEXT order_number UK
        TEXT status
        NUMERIC total_amount
        JSONB shipping_address
        TIMESTAMPTZ ordered_at
        TIMESTAMPTZ delivered_at
        TIMESTAMPTZ created_at
    }

    order_items {
        UUID id PK
        UUID order_id FK
        UUID product_id FK
        INTEGER quantity
        NUMERIC unit_price
        NUMERIC total_price
    }

    return_requests {
        UUID id PK
        UUID order_id FK
        UUID customer_id FK
        TEXT status
        TEXT reason
        TEXT reason_category
        TEXT resolution
        NUMERIC refund_amount
        TEXT tracking_number
        TEXT notes
        TEXT thread_id
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        TIMESTAMPTZ resolved_at
    }

    return_items {
        UUID id PK
        UUID return_request_id FK
        UUID order_item_id FK
        INTEGER quantity
        TEXT condition
    }

    return_policies {
        UUID id PK
        TEXT category UK
        INTEGER max_return_days
        BOOLEAN requires_original_packaging
        NUMERIC restocking_fee_percent
        TEXT_ARRAY allowed_conditions
        TEXT policy_text
        BOOLEAN active
        TIMESTAMPTZ created_at
    }

    policy_embeddings {
        UUID id PK
        UUID policy_id FK
        TEXT chunk_text
        VECTOR_1536 embedding
        JSONB metadata
        TIMESTAMPTZ created_at
    }

    llm_usage {
        UUID id PK
        TEXT thread_id
        UUID customer_id FK
        UUID order_id FK
        TEXT node
        TEXT model
        INTEGER input_tokens
        INTEGER output_tokens
        INTEGER total_tokens
        INTEGER latency_ms
        NUMERIC cost_eur
        TIMESTAMPTZ created_at
    }

    mcp_tool_calls {
        UUID id PK
        TEXT thread_id
        TEXT tool_name
        JSONB input_args
        JSONB output_result
        INTEGER latency_ms
        TEXT status
        TIMESTAMPTZ created_at
    }

    customers ||--o{ orders : "places"
    customers ||--o{ return_requests : "submits"
    customers ||--o{ llm_usage : "generates (opcional)"

    orders ||--o{ order_items : "contains"
    orders ||--o{ return_requests : "generates"
    orders ||--o{ llm_usage : "asociado a (opcional)"

    products ||--o{ order_items : "appears in"
    products }o--o{ return_policies : "category match"

    order_items ||--o{ return_items : "returned as"

    return_requests ||--o{ return_items : "includes"
    return_requests ||--o{ mcp_tool_calls : "linked via thread_id"

    return_policies ||--o{ policy_embeddings : "chunked into"
```

## Notas sobre tablas que no reflejan el uso real

- **El estado real de cada conversación no vive en ninguna tabla de este
  diagrama**: vive en las tablas propias del checkpointer de LangGraph
  (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`,
  `checkpoint_migrations`), creadas dinámicamente por
  `AsyncPostgresSaver.setup()` (ver `backend/agents/graph.py`) la primera vez
  que arranca el backend — **no** por ningún fichero de
  `supabase/migrations/`, así que no aparecen en este diagrama. `thread_id`
  (columna TEXT en `return_requests`, `llm_usage`, y `mcp_tool_calls`,
  migraciones 012/014/017) es el identificador que conecta ambos mundos.
  (Existió una tabla `chat_sessions`/`chat_messages` — migración `010` —
  pensada para esto mismo, pero nunca la consultó ni la escribió ningún código
  de `backend/`; se eliminó en la migración `015_drop_chat_sessions.sql`. Ver
  `docs/defensaTFM/defenderAgentes.md` §15.)
- **`llm_usage`**: `customer_id`/`order_id` son `NULL` en los turnos de
  triaje anteriores a conocer el `order_number` del cliente (ver
  `fetch_order_data` en `triage.py`) — de ahí "(opcional)" en las relaciones.
  El campo `cost_eur` (migración 016) congela el coste económico en el
  momento de la llamada LLM, permitiendo auditoría y análisis de ROI sin
  recálculo posterior.
- **`mcp_tool_calls`** (migración 017): Registro de auditoría de todas las
  invocaciones de MCP (tools de Supabase y Logistics) para debugging,
  análisis de rendimiento y trazabilidad de decisiones del agente.
  Vinculado por `thread_id` a `return_requests` para rastreo end-to-end
  de una devolución.
