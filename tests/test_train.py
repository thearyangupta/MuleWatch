from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import psycopg
import pytest

from scoring.train import (
    FEATURE_COLUMNS,
    add_mule_labels,
    evaluate_pr_auc,
    get_mule_account_ids,
    get_shap_reasons,
    register_model,
    rows_to_xy,
    time_based_split,
    train_gradient_boosting,
)


@pytest.fixture
def training_database():
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
                    (1, "Alice", "a@example.com", "111", "A", "Tester"),
                    (2, "Bob", "b@example.com", "222", "B", "Tester"),
                    (3, "Charlie", "c@example.com", "333", "C", "Tester"),
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
                    ("ACC_A", 1, datetime(2025, 1, 1, tzinfo=UTC)),
                    ("ACC_B", 2, datetime(2025, 1, 1, tzinfo=UTC)),
                    ("ACC_C", 3, datetime(2025, 1, 1, tzinfo=UTC)),
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
                        500.00,
                        datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
                        True,
                    ),
                    (
                        "ACC_C",
                        "ACC_A",
                        "TRANSFER",
                        100.00,
                        datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
                        False,
                    ),
                ],
            )

        yield connection


def test_get_mule_account_ids(training_database):
    mule_accounts = get_mule_account_ids(
        connection=training_database,
    )

    assert mule_accounts == {
        "ACC_A",
        "ACC_B",
    }


def test_feature_columns():
    assert FEATURE_COLUMNS == [
        "pass_through_ratio",
        "median_dwell_minutes",
        "fan_in",
        "fan_out",
        "transfer_cashout_chains",
        "account_age_days",
        "velocity_ratio",
    ]


def test_add_mule_labels():
    feature_rows = [
        {
            "account_id": "ACC_A",
            "feature_date": "2026-01-01",
            "pass_through_ratio": 0.9,
        },
        {
            "account_id": "ACC_C",
            "feature_date": "2026-01-01",
            "pass_through_ratio": 0.2,
        },
    ]

    labelled_rows = add_mule_labels(
        feature_rows=feature_rows,
        mule_account_ids={"ACC_A", "ACC_B"},
    )

    assert labelled_rows[0]["mule_label"] == 1
    assert labelled_rows[1]["mule_label"] == 0


def test_time_based_split():
    rows = [
        {"feature_date": date(2026, 1, 5)},
        {"feature_date": date(2026, 1, 2)},
        {"feature_date": date(2026, 1, 1)},
        {"feature_date": date(2026, 1, 4)},
        {"feature_date": date(2026, 1, 3)},
    ]

    train_rows, test_rows = time_based_split(
        rows,
        train_fraction=0.6,
    )

    assert {row["feature_date"] for row in train_rows} == {
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 3),
    }

    assert {row["feature_date"] for row in test_rows} == {
        date(2026, 1, 4),
        date(2026, 1, 5),
    }


def test_rows_to_xy():
    rows = [
        {
            "account_id": "ACC_A",
            "feature_date": date(2026, 1, 1),
            "pass_through_ratio": 0.9,
            "median_dwell_minutes": 20.0,
            "fan_in": 5,
            "fan_out": 2,
            "transfer_cashout_chains": 1,
            "account_age_days": 30,
            "velocity_ratio": 3.0,
            "mule_label": 1,
        }
    ]

    features, labels = rows_to_xy(rows)

    assert list(features.columns) == FEATURE_COLUMNS
    assert labels.tolist() == [1]


def test_gradient_boosting_and_pr_auc():
    rows = []

    for index in range(20):
        mule_label = int(index >= 10)

        rows.append(
            {
                "account_id": f"ACC_{index}",
                "feature_date": date(2026, 1, 1),
                "pass_through_ratio": float(mule_label),
                "median_dwell_minutes": 10.0 + index,
                "fan_in": 1 + mule_label * 5,
                "fan_out": 1,
                "transfer_cashout_chains": mule_label,
                "account_age_days": 100 - index,
                "velocity_ratio": 1.0 + mule_label * 2,
                "mule_label": mule_label,
            }
        )

    model = train_gradient_boosting(rows)

    pr_auc = evaluate_pr_auc(
        model=model,
        test_rows=rows,
    )

    assert 0.0 <= pr_auc <= 1.0


@patch("scoring.train.mlflow.xgboost.log_model")
@patch("scoring.train.mlflow.log_metric")
@patch("scoring.train.mlflow.log_params")
@patch("scoring.train.mlflow.start_run")
@patch("scoring.train.mlflow.set_experiment")
def test_register_model(
    mock_set_experiment,
    mock_start_run,
    mock_log_params,
    mock_log_metric,
    mock_log_model,
):
    model = MagicMock()

    model_info = MagicMock()
    model_info.registered_model_version = 1
    mock_log_model.return_value = model_info

    version = register_model(
        model=model,
        pr_auc=0.25,
    )

    assert version == "1"

    mock_set_experiment.assert_called_once_with("mulewatch-account-scoring")

    mock_log_metric.assert_called_once_with(
        "pr_auc",
        0.25,
    )

    mock_log_model.assert_called_once()


def test_get_shap_reasons():
    rows = []

    for index in range(20):
        mule_label = int(index >= 10)

        rows.append(
            {
                "account_id": f"ACC_{index}",
                "feature_date": date(2026, 1, 1),
                "pass_through_ratio": float(mule_label),
                "median_dwell_minutes": 10.0 + index,
                "fan_in": 1 + mule_label * 5,
                "fan_out": 1,
                "transfer_cashout_chains": mule_label,
                "account_age_days": 100 - index,
                "velocity_ratio": 1.0 + mule_label * 2,
                "mule_label": mule_label,
            }
        )

    model = train_gradient_boosting(rows)

    reasons = get_shap_reasons(
        model=model,
        feature_row=rows[-1],
    )

    assert len(reasons) == 3

    for reason in reasons:
        assert set(reason) == {
            "feature",
            "value",
            "shap_value",
        }

    assert abs(reasons[0]["shap_value"]) >= abs(reasons[1]["shap_value"])
    assert abs(reasons[1]["shap_value"]) >= abs(reasons[2]["shap_value"])
