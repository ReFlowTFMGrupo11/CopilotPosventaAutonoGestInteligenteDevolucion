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
