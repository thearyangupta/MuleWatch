from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pandas as pd
import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LANDING_DIR = PROJECT_ROOT / "data" / "landing"
DATABASE_URL = "postgresql://mulewatch:mulewatch_dev@localhost:5432/mulewatch"


def make_source_transaction_id(run_date: date, row_number: int) -> str:
    source_key = f"mulewatch:{run_date.isoformat()}:{row_number}"
    return str(uuid5(NAMESPACE_URL, source_key))


def prepare_staging_rows(
    transactions: pd.DataFrame,
    run_date: date,
) -> list[tuple]:
    rows = []

    for row_number, row in enumerate(transactions.itertuples(index=False)):
        timestamp = datetime.combine(
            run_date,
            datetime.min.time(),
            tzinfo=UTC,
        ) + timedelta(hours=(int(row.step) - 1) % 24)

        rows.append(
            (
                make_source_transaction_id(run_date, row_number),
                run_date,
                row.nameOrig,
                row.nameDest,
                row.type,
                float(row.amount),
                timestamp,
                bool(row.isFraud),
            )
        )

    return rows


def ingest_landing_file(
    run_date: date,
    database_url: str = DATABASE_URL,
) -> int:
    landing_path = LANDING_DIR / f"{run_date.isoformat()}.csv"

    if not landing_path.exists():
        raise FileNotFoundError(f"Landing file not found: {landing_path}")

    transactions = pd.read_csv(landing_path)
    rows = prepare_staging_rows(transactions, run_date)

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM staging_transactions
                WHERE run_date = %s
                """,
                (run_date,),
            )

            cursor.executemany(
                """
                INSERT INTO staging_transactions (
                    source_transaction_id,
                    run_date,
                    sender_account_id,
                    receiver_account_id,
                    transaction_type,
                    amount,
                    timestamp,
                    is_fraud
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )

    return len(rows)
