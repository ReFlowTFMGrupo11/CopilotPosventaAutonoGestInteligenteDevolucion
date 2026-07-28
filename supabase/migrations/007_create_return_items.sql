-- Return items (which products from the order are being returned)
CREATE TABLE IF NOT EXISTS return_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    return_request_id UUID NOT NULL REFERENCES return_requests(id) ON DELETE CASCADE,
    order_item_id UUID NOT NULL REFERENCES order_items(id),
    quantity INTEGER NOT NULL DEFAULT 1,
    condition TEXT NOT NULL DEFAULT 'unopened'
);

CREATE INDEX idx_return_items_request ON return_items(return_request_id);
