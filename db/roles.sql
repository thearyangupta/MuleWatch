DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'mulewatch_readonly'
    ) THEN
        CREATE ROLE mulewatch_readonly
            LOGIN
            PASSWORD 'mulewatch_readonly_dev';
    END IF;
END
$$;

GRANT CONNECT
ON DATABASE mulewatch
TO mulewatch_readonly;

GRANT USAGE
ON SCHEMA public
TO mulewatch_readonly;

GRANT SELECT
ON ALL TABLES IN SCHEMA public
TO mulewatch_readonly;

ALTER DEFAULT PRIVILEGES
IN SCHEMA public
GRANT SELECT
ON TABLES
TO mulewatch_readonly;