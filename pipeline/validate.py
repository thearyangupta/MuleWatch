from datetime import date

import pandas as pd
import pandera.pandas as pa
import psycopg

ALLOWED_TRANSACTION_TYPES = {
    "CASH_IN",
    "CASH_OUT",
    "DEBIT",
    "PAYMENT",
    "TRANSFER",
}

QUARANTINE_THRESHOLD = 0.05

DATABASE_URL = "postgresql://mulewatch:mulewatch_dev@localhost:5432/mulewatch"


transaction_schema = pa.DataFrameSchema(
    {
        "source_transaction_id": pa.Column(
            str,
            nullable=False,
        ),
        "run_date": pa.Column(
            pa.Date,
            nullable=False,
        ),
        "sender_account_id": pa.Column(
            str,
            nullable=False,
        ),
        "receiver_account_id": pa.Column(
            str,
            nullable=False,
        ),
        "transaction_type": pa.Column(
            str,
            pa.Check.isin(ALLOWED_TRANSACTION_TYPES),
            nullable=False,
        ),
        "amount": pa.Column(
            float,
            pa.Check.ge(0),
            coerce=True,
            nullable=False,
        ),
        "timestamp": pa.Column(
            "datetime64[ns, UTC]",
            coerce=True,
            nullable=False,
        ),
        "is_fraud": pa.Column(
            bool,
            coerce=True,
            nullable=False,
        ),
    },
    strict=True,
    coerce=True,
)


def add_failure_reason(
    reasons: pd.Series,
    mask: pd.Series,
    reason: str,
) -> pd.Series:
    reasons = reasons.copy()

    reasons.loc[mask] = reasons.loc[mask].apply(
        lambda existing: f"{existing}; {reason}" if existing else reason
    )

    return reasons


def validate_transactions(
    transactions: pd.DataFrame,
    run_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = transactions.copy()

    data["timestamp"] = pd.to_datetime(
        data["timestamp"],
        utc=True,
        errors="coerce",
    )

    reasons = pd.Series(
        "",
        index=data.index,
        dtype="object",
    )
    missing_id = data["source_transaction_id"].isna() | data[
        "source_transaction_id"
    ].astype("string").str.strip().eq("")

    reasons = add_failure_reason(
        reasons,
        missing_id,
        "source_transaction_id is required",
    )
    negative_amount = data["amount"].isna() | (data["amount"] < 0)

    reasons = add_failure_reason(
        reasons,
        negative_amount,
        "amount must be non-negative",
    )
    unknown_type = ~data["transaction_type"].isin(ALLOWED_TRANSACTION_TYPES)

    reasons = add_failure_reason(
        reasons,
        unknown_type,
        "unknown transaction_type",
    )
    same_account = data["sender_account_id"] == data["receiver_account_id"]

    reasons = add_failure_reason(
        reasons,
        same_account,
        "sender and receiver must differ",
    )
    duplicate_id = data["source_transaction_id"].notna() & data[
        "source_transaction_id"
    ].duplicated(keep=False)

    reasons = add_failure_reason(
        reasons,
        duplicate_id,
        "duplicate source_transaction_id",
    )
    wrong_date = data["timestamp"].isna() | data["timestamp"].dt.date.ne(run_date)

    reasons = add_failure_reason(
        reasons,
        wrong_date,
        "timestamp must belong to run_date",
    )

    invalid_mask = reasons.ne("")

    clean = data.loc[~invalid_mask].copy()
    quarantined = data.loc[invalid_mask].copy()

    quarantined["failure_reason"] = reasons.loc[invalid_mask]
    if not clean.empty:
        clean = transaction_schema.validate(clean)

    return clean, quarantined


def load_staged_transactions(
    connection: psycopg.Connection,
    run_date: date,
) -> pd.DataFrame:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                source_transaction_id,
                run_date,
                sender_account_id,
                receiver_account_id,
                transaction_type,
                amount,
                timestamp,
                is_fraud
            FROM staging_transactions
            WHERE run_date = %s
            ORDER BY source_transaction_id
            """,
            (run_date,),
        )

        rows = cursor.fetchall()

        columns = [column.name for column in cursor.description]

    return pd.DataFrame(
        rows,
        columns=columns,
    )


def write_quarantined_rows(
    connection: psycopg.Connection,
    run_date: date,
    quarantined: pd.DataFrame,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM quarantine_transactions
            WHERE run_date = %s
            """,
            (run_date,),
        )

        if quarantined.empty:
            return

        rows = [
            (
                row.source_transaction_id,
                row.run_date,
                row.sender_account_id,
                row.receiver_account_id,
                row.transaction_type,
                row.amount,
                row.timestamp,
                row.is_fraud,
                row.failure_reason,
            )
            for row in quarantined.itertuples(index=False)
        ]

        cursor.executemany(
            """
            INSERT INTO quarantine_transactions (
                source_transaction_id,
                run_date,
                sender_account_id,
                receiver_account_id,
                transaction_type,
                amount,
                timestamp,
                is_fraud,
                failure_reason
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            rows,
        )


def upsert_clean_transactions(
    connection: psycopg.Connection,
    clean: pd.DataFrame,
) -> None:
    if clean.empty:
        return

    rows = [
        (
            row.source_transaction_id,
            row.sender_account_id,
            row.receiver_account_id,
            row.transaction_type,
            row.amount,
            row.timestamp,
            row.is_fraud,
        )
        for row in clean.itertuples(index=False)
    ]

    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO transactions (
                source_transaction_id,
                sender_account_id,
                receiver_account_id,
                transaction_type,
                amount,
                timestamp,
                is_fraud
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            ON CONFLICT (source_transaction_id)
            DO UPDATE SET
                sender_account_id =
                    EXCLUDED.sender_account_id,
                receiver_account_id =
                    EXCLUDED.receiver_account_id,
                transaction_type =
                    EXCLUDED.transaction_type,
                amount =
                    EXCLUDED.amount,
                timestamp =
                    EXCLUDED.timestamp,
                is_fraud =
                    EXCLUDED.is_fraud
            """,
            rows,
        )


def validate_staged_transactions(
    run_date: date,
    database_url: str = DATABASE_URL,
) -> tuple[int, int]:
    with psycopg.connect(database_url) as connection:
        staged = load_staged_transactions(
            connection,
            run_date,
        )

        if staged.empty:
            raise ValueError(f"No staged transactions found for {run_date}")

        clean, quarantined = validate_transactions(
            staged,
            run_date,
        )

        total_rows = len(staged)
        quarantined_rows = len(quarantined)

        quarantine_rate = quarantined_rows / total_rows

        write_quarantined_rows(
            connection,
            run_date,
            quarantined,
        )

        if quarantine_rate > QUARANTINE_THRESHOLD:
            raise ValueError(
                "Quarantine rate "
                f"{quarantine_rate:.2%} "
                "exceeds "
                f"{QUARANTINE_THRESHOLD:.2%} "
                "threshold"
            )

        upsert_clean_transactions(
            connection,
            clean,
        )

    return (
        len(clean),
        quarantined_rows,
    )
