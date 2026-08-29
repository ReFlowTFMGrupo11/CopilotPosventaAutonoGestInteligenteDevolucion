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
-- Seed data for development and demo purposes

-- Sample customers
INSERT INTO customers (id, email, full_name, phone, address) VALUES
    ('a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'maria.garcia@email.com', 'María García López', '+34612345678', '{"street": "Calle Gran Vía 42", "city": "Madrid", "postal_code": "28013", "country": "ES"}'),
    ('b2c3d4e5-f6a7-8901-bcde-f12345678901', 'carlos.martinez@email.com', 'Carlos Martínez Ruiz', '+34623456789', '{"street": "Avda. Diagonal 211", "city": "Barcelona", "postal_code": "08018", "country": "ES"}'),
    ('c3d4e5f6-a7b8-9012-cdef-123456789012', 'laura.fernandez@email.com', 'Laura Fernández Soto', '+34634567890', '{"street": "Calle Sierpes 15", "city": "Sevilla", "postal_code": "41004", "country": "ES"}');

-- Sample products
-- Categorías alineadas con la taxonomía en español de data/rag/policies/
-- (ver nota equivalente en supabase/seed.sql).
INSERT INTO products (id, sku, name, description, category, price, weight_kg) VALUES
    ('d4e5f6a7-b8c9-0123-defa-234567890123', 'ELEC-LAPTOP-001', 'Portátil ProBook 15"', 'Portátil de alto rendimiento con 16GB RAM y 512GB SSD', 'electronica_informatica', 899.99, 1.8),
    ('e5f6a7b8-c9d0-1234-efab-345678901234', 'ELEC-PHONE-001', 'Smartphone Galaxy X12', 'Smartphone 5G con cámara de 108MP', 'electronica_informatica', 649.99, 0.19),
    ('f6a7b8c9-d0e1-2345-fabc-456789012345', 'FASH-JACKET-001', 'Chaqueta de Cuero Premium', 'Chaqueta de cuero auténtico, talla M', 'moda_ropa', 199.99, 1.2),
    ('a7b8c9d0-e1f2-3456-abcd-567890123456', 'HOME-BLENDER-001', 'Batidora de Vaso 1200W', 'Batidora profesional con 6 velocidades', 'electrodomesticos', 79.99, 2.5),
    ('b8c9d0e1-f2a3-4567-bcde-678901234567', 'BOOK-PROG-001', 'Clean Code (Edición Español)', 'Libro sobre buenas prácticas de programación', 'libros_papeleria', 34.99, 0.6);

-- Sample orders
INSERT INTO orders (id, customer_id, order_number, status, total_amount, shipping_address, ordered_at, delivered_at) VALUES
    ('c9d0e1f2-a3b4-5678-cdef-789012345678', 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'ORD-2026-00142', 'delivered', 899.99, '{"street": "Calle Gran Vía 42", "city": "Madrid", "postal_code": "28013", "country": "ES"}', '2026-07-10 14:30:00+02', '2026-07-14 11:00:00+02'),
    ('d0e1f2a3-b4c5-6789-defa-890123456789', 'b2c3d4e5-f6a7-8901-bcde-f12345678901', 'ORD-2026-00158', 'delivered', 849.98, '{"street": "Avda. Diagonal 211", "city": "Barcelona", "postal_code": "08018", "country": "ES"}', '2026-07-05 09:15:00+02', '2026-07-09 16:45:00+02'),
    ('e1f2a3b4-c5d6-7890-efab-901234567890', 'c3d4e5f6-a7b8-9012-cdef-123456789012', 'ORD-2026-00163', 'delivered', 114.98, '{"street": "Calle Sierpes 15", "city": "Sevilla", "postal_code": "41004", "country": "ES"}', '2026-06-20 18:00:00+02', '2026-06-25 10:30:00+02');

-- Sample order items
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, total_price) VALUES
    ('f2a3b4c5-d6e7-8901-fabc-012345678901', 'c9d0e1f2-a3b4-5678-cdef-789012345678', 'd4e5f6a7-b8c9-0123-defa-234567890123', 1, 899.99, 899.99),
    ('a3b4c5d6-e7f8-9012-abcd-123456789012', 'd0e1f2a3-b4c5-6789-defa-890123456789', 'e5f6a7b8-c9d0-1234-efab-345678901234', 1, 649.99, 649.99),
    ('b4c5d6e7-f8a9-0123-bcde-234567890123', 'd0e1f2a3-b4c5-6789-defa-890123456789', 'f6a7b8c9-d0e1-2345-fabc-456789012345', 1, 199.99, 199.99),
    ('c5d6e7f8-a9b0-1234-cdef-345678901234', 'e1f2a3b4-c5d6-7890-efab-901234567890', 'a7b8c9d0-e1f2-3456-abcd-567890123456', 1, 79.99, 79.99),
    ('d6e7f8a9-b0c1-2345-defa-456789012345', 'e1f2a3b4-c5d6-7890-efab-901234567890', 'b8c9d0e1-f2a3-4567-bcde-678901234567', 1, 34.99, 34.99);

-- Sample return policies
-- Mismas categorías que products + ON CONFLICT DO NOTHING (ver nota
-- equivalente en supabase/seed.sql).
INSERT INTO return_policies (id, category, max_return_days, requires_original_packaging, restocking_fee_percent, allowed_conditions, policy_text) VALUES
    ('e7f8a9b0-c1d2-3456-efab-567890123456', 'electronica_informatica', 15, TRUE, 10.00, ARRAY['unopened', 'defective', 'wrong_item'], 'Los productos electrónicos pueden devolverse en un plazo de 15 días desde la entrega. Deben incluir el embalaje original y todos los accesorios. Se aplica una tarifa de reposición del 10% para productos abiertos no defectuosos. Los productos defectuosos se reembolsan íntegramente.'),
    ('f8a9b0c1-d2e3-4567-fabc-678901234567', 'moda_ropa', 30, FALSE, 0.00, ARRAY['unopened', 'wrong_size', 'wrong_item', 'not_as_described'], 'Las prendas de moda tienen un plazo de devolución de 30 días. No es necesario el embalaje original pero las prendas deben estar sin usar y con las etiquetas puestas. No se cobra tarifa de reposición. Cambios de talla disponibles según stock.'),
    ('a9b0c1d2-e3f4-5678-abcd-789012345678', 'electrodomesticos', 30, TRUE, 5.00, ARRAY['unopened', 'defective', 'wrong_item'], 'Los electrodomésticos pueden devolverse en 30 días. Requieren embalaje original. Tarifa de reposición del 5% para productos abiertos funcionales. Garantía de 2 años para defectos de fabricación.'),
    ('b0c1d2e3-f4a5-6789-bcde-890123456789', 'libros_papeleria', 14, FALSE, 0.00, ARRAY['wrong_item', 'defective'], 'Los libros solo pueden devolverse en 14 días si se recibió un artículo incorrecto o el producto está defectuoso (páginas faltantes, daño de impresión). No se aceptan devoluciones por cambio de opinión.')
ON CONFLICT (category) WHERE active DO NOTHING;
