import os
from datetime import timedelta

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv(
    "MULEWATCH_DATABASE_URL",
    ("postgresql://mulewatch_readonly:mulewatch_readonly_dev@localhost:5432/mulewatch"),
)


def get_account_profile(account_id: str) -> dict | None:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    a.id AS account_id,
                    a.opened_at,
                    c.id AS customer_id,
                    c.occupation
                FROM accounts AS a
                JOIN customers AS c
                    ON a.customer_id = c.id
                WHERE a.id = %s
                """,
                (account_id,),
            )
            return cursor.fetchone()


def get_transactions(
    account_id: str,
    days: int,
) -> list[dict]:
    if days <= 0:
        raise ValueError("days must be greater than zero")

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT MAX(timestamp) AS latest_timestamp
                FROM transactions
                """
            )

            latest_row = cursor.fetchone()

            if latest_row is None or latest_row["latest_timestamp"] is None:
                return []

            end_time = latest_row["latest_timestamp"]
            start_time = end_time - timedelta(days=days)

            cursor.execute(
                """
                SELECT
                    id,
                    sender_account_id,
                    receiver_account_id,
                    transaction_type,
                    amount,
                    timestamp
                FROM transactions
                WHERE (
                    sender_account_id = %s
                    OR receiver_account_id = %s
                )
                AND timestamp >= %s
                AND timestamp <= %s
                ORDER BY timestamp DESC
                """,
                (
                    account_id,
                    account_id,
                    start_time,
                    end_time,
                ),
            )

            return cursor.fetchall()


def get_counterparties(account_id: str) -> list[dict]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    CASE
                        WHEN sender_account_id = %s
                            THEN receiver_account_id
                        ELSE sender_account_id
                    END AS counterparty_account_id,
                    COUNT(*) AS transaction_count,
                    SUM(amount) AS total_amount
                FROM transactions
                WHERE
                    sender_account_id = %s
                    OR receiver_account_id = %s
                GROUP BY counterparty_account_id
                ORDER BY transaction_count DESC
                """,
                (
                    account_id,
                    account_id,
                    account_id,
                ),
            )

            return cursor.fetchall()
