from datetime import UTC, datetime

import psycopg
import pytest

import db.queries as queries


@pytest.fixture
def seeded_database(monkeypatch):
    write_url = "postgresql://mulewatch:mulewatch_dev@localhost:5432/mulewatch_test"

    read_url = (
        "postgresql://mulewatch_readonly:"
        "mulewatch_readonly_dev@localhost:5432/mulewatch_test"
    )

    with psycopg.connect(write_url) as connection:
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
                    id, name, email, phone, address, occupation
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        1,
                        "Alice Test",
                        "alice@example.com",
                        "1111111111",
                        "Test Address 1",
                        "Analyst",
                    ),
                    (
                        2,
                        "Bob Test",
                        "bob@example.com",
                        "2222222222",
                        "Test Address 2",
                        "Engineer",
                    ),
                    (
                        3,
                        "Charlie Test",
                        "charlie@example.com",
                        "3333333333",
                        "Test Address 3",
                        "Teacher",
                    ),
                ],
            )

            cursor.executemany(
                """
                INSERT INTO accounts (
                    id, customer_id, opened_at
                )
                VALUES (%s, %s, %s)
                """,
                [
                    (
                        "ACC_A",
                        1,
                        datetime(2025, 1, 1, tzinfo=UTC),
                    ),
                    (
                        "ACC_B",
                        2,
                        datetime(2025, 2, 1, tzinfo=UTC),
                    ),
                    (
                        "ACC_C",
                        3,
                        datetime(2025, 3, 1, tzinfo=UTC),
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
                        "ACC_A",
                        "ACC_B",
                        "TRANSFER",
                        100.00,
                        datetime(2026, 1, 10, 10, 0, tzinfo=UTC),
                        False,
                    ),
                    (
                        "ACC_B",
                        "ACC_A",
                        "TRANSFER",
                        40.00,
                        datetime(2026, 1, 11, 10, 0, tzinfo=UTC),
                        False,
                    ),
                    (
                        "ACC_A",
                        "ACC_C",
                        "TRANSFER",
                        25.00,
                        datetime(2026, 1, 12, 10, 0, tzinfo=UTC),
                        True,
                    ),
                ],
            )

    monkeypatch.setattr(queries, "DATABASE_URL", read_url)


def test_get_account_profile(seeded_database):
    profile = queries.get_account_profile("ACC_A")

    assert profile is not None
    assert profile["account_id"] == "ACC_A"
    assert profile["customer_id"] == 1
    assert profile["occupation"] == "Analyst"

    for key in ("name", "email", "phone", "address"):
        assert key not in profile


def test_get_transactions(seeded_database):
    transactions = queries.get_transactions("ACC_A", days=30)

    assert len(transactions) == 3

    transaction_ids = {transaction["id"] for transaction in transactions}

    assert len(transaction_ids) == 3

    for transaction in transactions:
        assert "is_fraud" not in transaction


def test_get_counterparties(seeded_database):
    counterparties = queries.get_counterparties("ACC_A")

    assert len(counterparties) == 2

    by_account = {row["counterparty_account_id"]: row for row in counterparties}

    assert by_account["ACC_B"]["transaction_count"] == 2
    assert by_account["ACC_B"]["total_amount"] == 140

    assert by_account["ACC_C"]["transaction_count"] == 1
    assert by_account["ACC_C"]["total_amount"] == 25


def test_get_transactions_rejects_invalid_days(seeded_database):
    with pytest.raises(
        ValueError,
        match="days must be greater than zero",
    ):
        queries.get_transactions("ACC_A", days=0)
