import os
from datetime import date

import psycopg

DATABASE_URL = os.getenv(
    "MULEWATCH_DATABASE_URL",
    "postgresql://mulewatch:mulewatch_dev@localhost:5432/mulewatch",
)


def write_pipeline_run(
    run_date: date,
    rows_in: int,
    rows_quarantined: int,
    accounts_scored: int,
    alerts_raised: int,
    model_version: str,
    duration_seconds: float,
    database_url: str = DATABASE_URL,
) -> dict:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_runs (
                    run_date,
                    rows_in,
                    rows_quarantined,
                    accounts_scored,
                    alerts_raised,
                    duration_seconds,
                    model_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_date)
                DO UPDATE SET
                    rows_in = EXCLUDED.rows_in,
                    rows_quarantined = EXCLUDED.rows_quarantined,
                    accounts_scored = EXCLUDED.accounts_scored,
                    alerts_raised = EXCLUDED.alerts_raised,
                    duration_seconds = EXCLUDED.duration_seconds,
                    model_version = EXCLUDED.model_version,
                    updated_at = NOW()
                """,
                (
                    run_date,
                    rows_in,
                    rows_quarantined,
                    accounts_scored,
                    alerts_raised,
                    duration_seconds,
                    model_version,
                ),
            )

    return {
        "run_date": run_date.isoformat(),
        "rows_in": rows_in,
        "rows_quarantined": rows_quarantined,
        "accounts_scored": accounts_scored,
        "alerts_raised": alerts_raised,
        "duration_seconds": duration_seconds,
        "model_version": model_version,
    }
