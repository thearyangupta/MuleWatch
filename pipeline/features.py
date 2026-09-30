from datetime import date
from statistics import median

import psycopg
from psycopg.rows import dict_row


def get_daily_transactions(
    connection: psycopg.Connection,
    account_id: str,
    feature_date: date,
) -> list[dict]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
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
            AND timestamp >= %s::date
            AND timestamp < %s::date + INTERVAL '1 day'
            ORDER BY timestamp
            """,
            (
                account_id,
                account_id,
                feature_date,
                feature_date,
            ),
        )

        return cursor.fetchall()


def get_daily_transaction_summary(
    connection: psycopg.Connection,
    account_id: str,
    feature_date: date,
) -> dict:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
                COALESCE(
                    SUM(amount) FILTER (
                        WHERE receiver_account_id = %s
                    ),
                    0
                ) AS incoming_amount,
                COALESCE(
                    SUM(amount) FILTER (
                        WHERE sender_account_id = %s
                    ),
                    0
                ) AS outgoing_amount,
                COUNT(
                    DISTINCT sender_account_id
                ) FILTER (
                    WHERE receiver_account_id = %s
                ) AS fan_in,
                COUNT(
                    DISTINCT receiver_account_id
                ) FILTER (
                    WHERE sender_account_id = %s
                ) AS fan_out
            FROM transactions
            WHERE (
                sender_account_id = %s
                OR receiver_account_id = %s
            )
            AND timestamp >= %s::date
            AND timestamp < %s::date + INTERVAL '1 day'
            """,
            (
                account_id,
                account_id,
                account_id,
                account_id,
                account_id,
                account_id,
                feature_date,
                feature_date,
            ),
        )

        return cursor.fetchone()


def calculate_pass_through_ratio(
    incoming_amount,
    outgoing_amount,
) -> float:
    incoming = float(incoming_amount)
    outgoing = float(outgoing_amount)

    if incoming <= 0:
        return 0.0

    return outgoing / incoming


def calculate_median_dwell_time(
    inbound_times: list,
    outbound_times: list,
) -> float:
    dwell_times = []

    for inbound_time in inbound_times:
        next_outbound = next(
            (
                outbound_time
                for outbound_time in outbound_times
                if outbound_time > inbound_time
            ),
            None,
        )

        if next_outbound is not None:
            dwell_minutes = (next_outbound - inbound_time).total_seconds() / 60

            dwell_times.append(dwell_minutes)

    if not dwell_times:
        return 0.0

    return float(median(dwell_times))


def count_transfer_cashout_chains(
    transactions: list[dict],
    account_id: str,
) -> int:
    transfer_seen = False
    chain_count = 0

    for transaction in transactions:
        if (
            transaction["receiver_account_id"] == account_id
            and transaction["transaction_type"] == "TRANSFER"
        ):
            transfer_seen = True

        elif (
            transfer_seen
            and transaction["sender_account_id"] == account_id
            and transaction["transaction_type"] == "CASH_OUT"
        ):
            chain_count += 1

    return chain_count


def calculate_account_age_days(
    opened_at,
    feature_date: date,
) -> int:
    opened_date = opened_at.date()

    return (feature_date - opened_date).days


def calculate_velocity_ratio(
    current_transaction_count: int,
    historical_daily_average: float,
) -> float:
    if historical_daily_average <= 0:
        return 0.0

    return current_transaction_count / historical_daily_average


def build_daily_feature_row(
    connection: psycopg.Connection,
    account_id: str,
    feature_date: date,
) -> dict:
    summary = get_daily_transaction_summary(
        connection=connection,
        account_id=account_id,
        feature_date=feature_date,
    )

    transactions = get_daily_transactions(
        connection=connection,
        account_id=account_id,
        feature_date=feature_date,
    )

    inbound_times = [
        transaction["timestamp"]
        for transaction in transactions
        if transaction["receiver_account_id"] == account_id
    ]

    outbound_times = [
        transaction["timestamp"]
        for transaction in transactions
        if transaction["sender_account_id"] == account_id
    ]

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT opened_at
            FROM accounts
            WHERE id = %s
            """,
            (account_id,),
        )
        account = cursor.fetchone()

        cursor.execute(
            """
            SELECT
                COUNT(*)::float
                / NULLIF(
                    COUNT(DISTINCT timestamp::date),
                    0
                ) AS historical_daily_average
            FROM transactions
            WHERE (
                sender_account_id = %s
                OR receiver_account_id = %s
            )
            AND timestamp < %s::date
            """,
            (
                account_id,
                account_id,
                feature_date,
            ),
        )
        history = cursor.fetchone()

    historical_daily_average = history["historical_daily_average"] or 0.0

    return {
        "account_id": account_id,
        "feature_date": feature_date,
        "pass_through_ratio": calculate_pass_through_ratio(
            incoming_amount=summary["incoming_amount"],
            outgoing_amount=summary["outgoing_amount"],
        ),
        "median_dwell_minutes": calculate_median_dwell_time(
            inbound_times=inbound_times,
            outbound_times=outbound_times,
        ),
        "fan_in": summary["fan_in"],
        "fan_out": summary["fan_out"],
        "transfer_cashout_chains": count_transfer_cashout_chains(
            transactions=transactions,
            account_id=account_id,
        ),
        "account_age_days": calculate_account_age_days(
            opened_at=account["opened_at"],
            feature_date=feature_date,
        ),
        "velocity_ratio": calculate_velocity_ratio(
            current_transaction_count=len(transactions),
            historical_daily_average=historical_daily_average,
        ),
    }


def build_all_daily_feature_rows(
    connection: psycopg.Connection,
) -> list[dict]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT DISTINCT
                account_id,
                feature_date
            FROM (
                SELECT
                    sender_account_id AS account_id,
                    timestamp::date AS feature_date
                FROM transactions

                UNION

                SELECT
                    receiver_account_id AS account_id,
                    timestamp::date AS feature_date
                FROM transactions
            ) AS account_days
            ORDER BY feature_date, account_id
            """
        )

        account_days = cursor.fetchall()

    return [
        build_daily_feature_row(
            connection=connection,
            account_id=row["account_id"],
            feature_date=row["feature_date"],
        )
        for row in account_days
    ]
