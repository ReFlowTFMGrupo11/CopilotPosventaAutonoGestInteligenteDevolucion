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
