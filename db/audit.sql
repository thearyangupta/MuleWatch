BEGIN;

ALTER TABLE audit_log
    ADD COLUMN IF NOT EXISTS previous_hash TEXT,
    ADD COLUMN IF NOT EXISTS event_hash TEXT;

ALTER TABLE audit_log
    ALTER COLUMN details SET NOT NULL,
    ALTER COLUMN previous_hash SET NOT NULL,
    ALTER COLUMN event_hash SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS
    idx_audit_log_event_hash
    ON audit_log (event_hash);

CREATE INDEX IF NOT EXISTS
    idx_audit_log_case
    ON audit_log (case_id, id);


CREATE OR REPLACE FUNCTION audit_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'audit_log is append-only';
END;
$$;

DROP TRIGGER IF EXISTS audit_no_update_delete
    ON audit_log;

CREATE TRIGGER audit_no_update_delete
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW
EXECUTE FUNCTION audit_reject_mutation();

DROP TRIGGER IF EXISTS audit_no_truncate
    ON audit_log;

CREATE TRIGGER audit_no_truncate
BEFORE TRUNCATE ON audit_log
FOR EACH STATEMENT
EXECUTE FUNCTION audit_reject_mutation();

REVOKE UPDATE, DELETE, TRUNCATE
ON audit_log FROM mulewatch;

GRANT SELECT, INSERT
ON audit_log TO mulewatch;

COMMIT;
