ALTER TABLE cases
    ADD COLUMN IF NOT EXISTS thread_id TEXT,
    ADD COLUMN IF NOT EXISTS agent_action TEXT,
    ADD COLUMN IF NOT EXISTS final_action TEXT,
    ADD COLUMN IF NOT EXISTS review_decision TEXT,
    ADD COLUMN IF NOT EXISTS reviewer_id TEXT,
    ADD COLUMN IF NOT EXISTS reviewer_comment TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS agreement BOOLEAN;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cases_thread_id
    ON cases (thread_id)
    WHERE thread_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cases_review_status
    ON cases (status, created_at DESC);
