CREATE TABLE IF NOT EXISTS customers (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    address TEXT NOT NULL,
    occupation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    opened_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id BIGSERIAL PRIMARY KEY,
    sender_account_id TEXT NOT NULL REFERENCES accounts(id),
    receiver_account_id TEXT NOT NULL REFERENCES accounts(id),
    source_transaction_id TEXT UNIQUE,
    transaction_type TEXT NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    is_fraud BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS staging_transactions (
    source_transaction_id TEXT,
    run_date DATE NOT NULL,
    sender_account_id TEXT NOT NULL,
    receiver_account_id TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    is_fraud BOOLEAN NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_staging_transactions_run_date
    ON staging_transactions (run_date);


CREATE TABLE IF NOT EXISTS quarantine_transactions (
    id BIGSERIAL PRIMARY KEY,
    source_transaction_id TEXT,
    run_date DATE NOT NULL,
    sender_account_id TEXT,
    receiver_account_id TEXT,
    transaction_type TEXT,
    amount NUMERIC(18, 2),
    timestamp TIMESTAMPTZ,
    is_fraud BOOLEAN,
    failure_reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quarantine_transactions_run_date
    ON quarantine_transactions (run_date);

CREATE INDEX IF NOT EXISTS idx_transactions_sender_timestamp
    ON transactions (sender_account_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_transactions_receiver_timestamp
    ON transactions (receiver_account_id, timestamp);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    alert_date DATE NOT NULL,
    risk_score DOUBLE PRECISION NOT NULL,
    model_version TEXT NOT NULL,
    reasons JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'NEW',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_account_date
    ON alerts (account_id, alert_date);

CREATE TABLE IF NOT EXISTS cases (
    id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL REFERENCES alerts(id),
    status TEXT NOT NULL DEFAULT 'OPEN',
    summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    case_id BIGINT REFERENCES cases(id),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
