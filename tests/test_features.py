from datetime import UTC, date, datetime

import psycopg
import pytest

from pipeline.features import (
    build_all_daily_feature_rows,
    build_daily_feature_row,
    calculate_account_age_days,
    calculate_median_dwell_time,
    calculate_pass_through_ratio,
    calculate_velocity_ratio,
    count_transfer_cashout_chains,
    get_daily_transaction_summary,
    get_daily_transactions,
)


@pytest.fixture
def feature_database():
    database_url = "postgresql://mulewatch:mulewatch_dev@localhost:5432/mulewatch_test"

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                TRUNCATE TABLE
                    audit_log,
                    cases,
                    alerts,
                    transactions,
                    accounts,
                    customers
                RESTART IDENTITY CASCADE
                """
            )

            cursor.executemany(
                """
                INSERT INTO customers (
                    id,
                    name,
                    email,
                    phone,
                    address,
                    occupation
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        1,
                        "Account Owner",
                        "owner@example.com",
                        "1111111111",
                        "Test Address",
                        "Tester",
                    ),
                    (
                        2,
                        "Sender One",
                        "sender@example.com",
                        "2222222222",
                        "Test Address",
                        "Tester",
                    ),
                    (
                        3,
                        "Receiver One",
                        "receiver@example.com",
                        "3333333333",
                        "Test Address",
                        "Tester",
                    ),
                    (
                        4,
                        "Sender Two",
                        "sender2@example.com",
                        "4444444444",
                        "Test Address",
                        "Tester",
                    ),
                ],
            )

            cursor.executemany(
                """
                INSERT INTO accounts (
                    id,
                    customer_id,
                    opened_at
                )
                VALUES (%s, %s, %s)
                """,
                [
                    (
                        "ACC_TARGET",
                        1,
                        datetime(2025, 1, 1, tzinfo=UTC),
                    ),
                    (
                        "ACC_SENDER",
                        2,
                        datetime(2025, 1, 1, tzinfo=UTC),
                    ),
                    (
                        "ACC_RECEIVER",
                        3,
                        datetime(2025, 1, 1, tzinfo=UTC),
                    ),
                    (
                        "ACC_SENDER_2",
                        4,
                        datetime(2025, 1, 1, tzinfo=UTC),
                    ),
                ],
            )

            cursor.executemany(
                """
                INSERT INTO transactions (
                    sender_account_id,
                    receiver_account_id,
                    transaction_type,
                    amount,
                    timestamp,
                    is_fraud
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        "ACC_SENDER",
                        "ACC_TARGET",
                        "TRANSFER",
                        600.00,
                        datetime(2026, 1, 10, 9, 0, tzinfo=UTC),
                        False,
                    ),
                    (
                        "ACC_SENDER",
                        "ACC_TARGET",
                        "TRANSFER",
                        400.00,
                        datetime(2026, 1, 10, 10, 0, tzinfo=UTC),
                        False,
                    ),
                    (
                        "ACC_SENDER_2",
                        "ACC_TARGET",
                        "TRANSFER",
                        200.00,
                        datetime(2026, 1, 10, 10, 30, tzinfo=UTC),
                        False,
                    ),
                    (
                        "ACC_TARGET",
                        "ACC_RECEIVER",
                        "TRANSFER",
                        900.00,
                        datetime(2026, 1, 10, 11, 0, tzinfo=UTC),
                        False,
                    ),
                ],
            )

        yield connection


def test_pass_through_ratio():
    result = calculate_pass_through_ratio(
        incoming_amount=1000,
        outgoing_amount=900,
    )

    assert result == pytest.approx(0.9)


def test_get_daily_transaction_summary(feature_database):
    summary = get_daily_transaction_summary(
        connection=feature_database,
        account_id="ACC_TARGET",
        feature_date=date(2026, 1, 10),
    )

    assert summary["incoming_amount"] == 1200
    assert summary["outgoing_amount"] == 900
    assert summary["fan_in"] == 2
    assert summary["fan_out"] == 1


def test_daily_pass_through_ratio(feature_database):
    summary = get_daily_transaction_summary(
        connection=feature_database,
        account_id="ACC_TARGET",
        feature_date=date(2026, 1, 10),
    )

    result = calculate_pass_through_ratio(
        incoming_amount=summary["incoming_amount"],
        outgoing_amount=summary["outgoing_amount"],
    )

    assert result == pytest.approx(0.75)


def test_median_dwell_time():
    inbound_times = [
        datetime(2026, 1, 10, 9, 0, tzinfo=UTC),
        datetime(2026, 1, 10, 9, 10, tzinfo=UTC),
        datetime(2026, 1, 10, 11, 0, tzinfo=UTC),
    ]

    outbound_times = [
        datetime(2026, 1, 10, 9, 40, tzinfo=UTC),
        datetime(2026, 1, 10, 11, 15, tzinfo=UTC),
    ]

    result = calculate_median_dwell_time(
        inbound_times,
        outbound_times,
    )

    assert result == pytest.approx(30.0)


def test_median_dwell_time_with_no_outbound():
    inbound_times = [
        datetime(2026, 1, 10, 9, 0, tzinfo=UTC),
    ]

    result = calculate_median_dwell_time(
        inbound_times,
        [],
    )

    assert result == 0.0


def test_transfer_cashout_chains():
    transactions = [
        {
            "sender_account_id": "ACC_A",
            "receiver_account_id": "ACC_TARGET",
            "transaction_type": "TRANSFER",
        },
        {
            "sender_account_id": "ACC_TARGET",
            "receiver_account_id": "ACC_X",
            "transaction_type": "CASH_OUT",
        },
        {
            "sender_account_id": "ACC_B",
            "receiver_account_id": "ACC_TARGET",
            "transaction_type": "TRANSFER",
        },
        {
            "sender_account_id": "ACC_TARGET",
            "receiver_account_id": "ACC_Y",
            "transaction_type": "CASH_OUT",
        },
    ]

    result = count_transfer_cashout_chains(
        transactions=transactions,
        account_id="ACC_TARGET",
    )

    assert result == 2


def test_account_age_days():
    opened_at = datetime(
        2026,
        1,
        1,
        tzinfo=UTC,
    )

    result = calculate_account_age_days(
        opened_at=opened_at,
        feature_date=date(2026, 1, 21),
    )

    assert result == 20


def test_velocity_ratio():
    result = calculate_velocity_ratio(
        current_transaction_count=10,
        historical_daily_average=2.0,
    )

    assert result == pytest.approx(5.0)


def test_velocity_ratio_with_no_history():
    result = calculate_velocity_ratio(
        current_transaction_count=10,
        historical_daily_average=0.0,
    )

    assert result == 0.0


def test_get_daily_transactions(feature_database):
    transactions = get_daily_transactions(
        connection=feature_database,
        account_id="ACC_TARGET",
        feature_date=date(2026, 1, 10),
    )

    assert len(transactions) == 4

    assert transactions[0]["timestamp"] == datetime(
        2026,
        1,
        10,
        9,
        0,
        tzinfo=UTC,
    )

    assert transactions[-1]["timestamp"] == datetime(
        2026,
        1,
        10,
        11,
        0,
        tzinfo=UTC,
    )


def test_build_daily_feature_row(feature_database):
    row = build_daily_feature_row(
        connection=feature_database,
        account_id="ACC_TARGET",
        feature_date=date(2026, 1, 10),
    )

    assert row["account_id"] == "ACC_TARGET"
    assert row["feature_date"] == date(2026, 1, 10)
    assert row["pass_through_ratio"] == pytest.approx(0.75)
    assert row["median_dwell_minutes"] == pytest.approx(60.0)
    assert row["fan_in"] == 2
    assert row["fan_out"] == 1
    assert row["transfer_cashout_chains"] == 0
    assert row["account_age_days"] == 374
    assert row["velocity_ratio"] == 0.0


def test_build_all_daily_feature_rows(feature_database):
    rows = build_all_daily_feature_rows(
        connection=feature_database,
    )

    account_days = {
        (
            row["account_id"],
            row["feature_date"],
        )
        for row in rows
    }

    assert account_days == {
        ("ACC_SENDER", date(2026, 1, 10)),
        ("ACC_SENDER_2", date(2026, 1, 10)),
        ("ACC_TARGET", date(2026, 1, 10)),
        ("ACC_RECEIVER", date(2026, 1, 10)),
    }
