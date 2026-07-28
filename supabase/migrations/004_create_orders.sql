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
