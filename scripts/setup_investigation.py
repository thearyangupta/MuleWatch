from pathlib import Path

import psycopg

from agent.graph import CASE_DATABASE_URL
from agent.review_runtime import initialize_checkpointer


def apply_migrations() -> None:
    root = Path(__file__).resolve().parents[1]

    review_sql = (root / "db" / "review.sql").read_text(encoding="utf-8")
    audit_sql = (root / "db" / "audit.sql").read_text(encoding="utf-8")

    with psycopg.connect(CASE_DATABASE_URL) as connection:
        # Reject legacy unhashed records rather than fabricate history.
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.audit_log')")
            if cursor.fetchone()[0] is None:
                raise RuntimeError("audit_log missing: apply db/schema.sql first")

            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'audit_log'
                  AND column_name IN (
                      'previous_hash', 'event_hash', 'details'
                  )
            """)
            columns = {row[0] for row in cursor.fetchall()}

            if {"previous_hash", "event_hash"} <= columns:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM audit_log
                        WHERE previous_hash IS NULL
                           OR event_hash IS NULL
                           OR details IS NULL
                    )
                """)
            else:
                cursor.execute("SELECT EXISTS (SELECT 1 FROM audit_log)")

            if cursor.fetchone()[0]:
                raise RuntimeError(
                    "Legacy unhashed audit records detected. "
                    "Migration requires a separately reviewed backfill."
                )

        connection.execute(review_sql)
        print("Applied migration: review.sql")

    # audit.sql manages its own BEGIN/COMMIT transaction.
    with psycopg.connect(CASE_DATABASE_URL, autocommit=True) as connection:
        connection.execute(audit_sql)
        print("Applied migration: audit.sql")


def main() -> None:
    apply_migrations()
    initialize_checkpointer()
    print("Case review, audit, and checkpoint setup complete.")


if __name__ == "__main__":
    main()
