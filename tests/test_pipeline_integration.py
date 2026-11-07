import os
from datetime import date
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from pipeline.validate import validate_staged_transactions


def test_quarantine_survives_quality_gate_failure():
    url = os.getenv("MULEWATCH_INTEGRATION_DATABASE_URL", "")
    if not url:
        pytest.skip("Dedicated integration database not configured")

    database_name = urlsplit(url).path.lstrip("/")
    if database_name not in ("mulewatch_test", "mulewatch_e2e"):
        pytest.fail("Refusing to run outside approved test database")

    schema = "mw_it_" + uuid4().hex[:16]
    run_date = date(2026, 1, 1)

    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    try:
        with psycopg.connect(url) as setup:
            setup.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
            )
            setup.execute("""
                CREATE TABLE staging_transactions (
                    source_transaction_id TEXT,
                    run_date DATE NOT NULL,
                    sender_account_id TEXT NOT NULL,
                    receiver_account_id TEXT NOT NULL,
                    transaction_type TEXT NOT NULL,
                    amount NUMERIC(18,2),
                    timestamp TIMESTAMPTZ NOT NULL,
                    is_fraud BOOLEAN NOT NULL
                )
            """)
            setup.execute("""
                CREATE TABLE quarantine_transactions (
                    source_transaction_id TEXT,
                    run_date DATE,
                    sender_account_id TEXT,
                    receiver_account_id TEXT,
                    transaction_type TEXT,
                    amount NUMERIC(18,2),
                    timestamp TIMESTAMPTZ,
                    is_fraud BOOLEAN,
                    failure_reason TEXT
                )
            """)
            setup.execute("""
                CREATE TABLE transactions (
                    source_transaction_id TEXT UNIQUE,
                    sender_account_id TEXT,
                    receiver_account_id TEXT,
                    transaction_type TEXT,
                    amount NUMERIC(18,2),
                    timestamp TIMESTAMPTZ,
                    is_fraud BOOLEAN
                )
            """)
            setup.execute(
                """
                INSERT INTO staging_transactions VALUES
                ('valid-1', %s, 'A', 'B', 'TRANSFER',
                 100, '2026-01-01T10:00:00Z', FALSE),
                ('invalid-1', %s, 'A', 'A', 'TRANSFER',
                 100, '2026-01-01T11:00:00Z', FALSE)
            """,
                (run_date, run_date),
            )

        # psycopg accepts a connection options parameter in its DSN.
        # Use an explicit search_path for this disposable schema.
        with psycopg.connect(url) as probe:
            probe.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
            )
            probe.commit()

        # Set search_path for the function's own connection.
        from unittest.mock import patch

        import pipeline.validate as validation

        original_connect = psycopg.connect

        def isolated_connect(*args, **kwargs):
            conn = original_connect(*args, **kwargs)
            conn.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
            )
            return conn

        with patch.object(validation.psycopg, "connect", isolated_connect):
            with pytest.raises(ValueError, match="Quarantine rate"):
                validate_staged_transactions(run_date, database_url=url)

        with psycopg.connect(url) as check:
            check.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
            )
            quarantined = check.execute(
                "SELECT failure_reason FROM quarantine_transactions"
            ).fetchall()
            clean_count = check.execute("SELECT COUNT(*) FROM transactions").fetchone()[
                0
            ]

        assert len(quarantined) == 1
        assert "sender and receiver" in quarantined[0][0]
        assert clean_count == 0

    finally:
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
