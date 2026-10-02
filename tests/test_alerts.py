from datetime import date

import psycopg
import pytest

from pipeline.alerts import (
    get_accounts_for_date,
    insert_alerts,
    select_alert_candidates,
)


@pytest.fixture
def alert_database():
    connection = psycopg.connect(
        "postgresql://mulewatch:mulewatch_dev@localhost:5432/mulewatch_test"
    )

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

        cursor.execute(
            """
            INSERT INTO customers (
                name,
                email,
                phone,
                address,
                occupation
            )
            VALUES (
                'Alice',
                'alice@example.com',
                '1111111111',
                'Test Address',
                'Analyst'
            )
            RETURNING id
            """
        )

        customer_id = cursor.fetchone()[0]

        cursor.executemany(
            """
            INSERT INTO accounts (
                id,
                customer_id,
                opened_at
            )
            VALUES (
                %s,
                %s,
                %s
            )
            """,
            [
                (
                    "ACC_A",
                    customer_id,
                    "2026-01-01 00:00:00+00",
                ),
                (
                    "ACC_B",
                    customer_id,
                    "2026-01-01 00:00:00+00",
                ),
                (
                    "ACC_C",
                    customer_id,
                    "2026-01-01 00:00:00+00",
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
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            [
                (
                    "ACC_A",
                    "ACC_B",
                    "TRANSFER",
                    100,
                    "2026-01-10 10:00:00+00",
                    False,
                ),
                (
                    "ACC_B",
                    "ACC_C",
                    "TRANSFER",
                    50,
                    "2026-01-10 11:00:00+00",
                    False,
                ),
            ],
        )

    connection.commit()

    yield connection

    connection.close()


def test_select_alert_candidates_respects_budget():
    scored_accounts = [
        {
            "account_id": "ACC_A",
            "risk_score": 0.91,
        },
        {
            "account_id": "ACC_B",
            "risk_score": 0.45,
        },
        {
            "account_id": "ACC_C",
            "risk_score": 0.82,
        },
        {
            "account_id": "ACC_D",
            "risk_score": 0.73,
        },
    ]

    selected = select_alert_candidates(
        scored_accounts,
        alert_budget=2,
    )

    assert len(selected) == 2

    assert [account["account_id"] for account in selected] == [
        "ACC_A",
        "ACC_C",
    ]


def test_select_alert_candidates_breaks_ties_deterministically():
    scored_accounts = [
        {
            "account_id": "ACC_B",
            "risk_score": 0.80,
        },
        {
            "account_id": "ACC_A",
            "risk_score": 0.80,
        },
        {
            "account_id": "ACC_C",
            "risk_score": 0.70,
        },
    ]

    selected = select_alert_candidates(
        scored_accounts,
        alert_budget=1,
    )

    assert selected[0]["account_id"] == "ACC_A"


def test_select_alert_candidates_rejects_invalid_budget():
    with pytest.raises(
        ValueError,
        match="alert_budget must be greater than zero",
    ):
        select_alert_candidates(
            [],
            alert_budget=0,
        )


def test_get_accounts_for_date(
    alert_database,
):
    accounts = get_accounts_for_date(
        connection=alert_database,
        alert_date=date(2026, 1, 10),
    )

    assert accounts == [
        "ACC_A",
        "ACC_B",
        "ACC_C",
    ]


def test_insert_alerts_persists_required_fields(
    alert_database,
):
    candidates = [
        {
            "account_id": "ACC_A",
            "risk_score": 0.91,
            "reasons": [
                {
                    "feature": "pass_through_ratio",
                    "value": 0.97,
                    "shap_value": 1.2,
                },
                {
                    "feature": "fan_in",
                    "value": 9.0,
                    "shap_value": 0.8,
                },
                {
                    "feature": "median_dwell_minutes",
                    "value": 40.0,
                    "shap_value": -0.5,
                },
            ],
        }
    ]

    inserted = insert_alerts(
        connection=alert_database,
        alert_date=date(2026, 1, 10),
        candidates=candidates,
        model_version="1",
    )

    assert inserted == 1

    with alert_database.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                account_id,
                alert_date,
                risk_score,
                model_version,
                reasons,
                status
            FROM alerts
            WHERE account_id = %s
              AND alert_date = %s
            """,
            (
                "ACC_A",
                date(2026, 1, 10),
            ),
        )

        alert = cursor.fetchone()

    assert alert[0] == "ACC_A"
    assert alert[1] == date(2026, 1, 10)
    assert alert[2] == pytest.approx(0.91)
    assert alert[3] == "1"
    assert len(alert[4]) == 3
    assert alert[5] == "NEW"


def test_insert_alerts_is_idempotent(
    alert_database,
):
    candidates = [
        {
            "account_id": "ACC_A",
            "risk_score": 0.91,
            "reasons": [
                {
                    "feature": "fan_in",
                    "value": 9.0,
                    "shap_value": 1.0,
                }
            ],
        }
    ]

    first_insert = insert_alerts(
        connection=alert_database,
        alert_date=date(2026, 1, 10),
        candidates=candidates,
        model_version="1",
    )

    second_insert = insert_alerts(
        connection=alert_database,
        alert_date=date(2026, 1, 10),
        candidates=candidates,
        model_version="1",
    )

    assert first_insert == 1
    assert second_insert == 0

    with alert_database.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM alerts
            WHERE account_id = %s
              AND alert_date = %s
            """,
            (
                "ACC_A",
                date(2026, 1, 10),
            ),
        )

        count = cursor.fetchone()[0]

    assert count == 1
