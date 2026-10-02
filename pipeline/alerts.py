import json
from datetime import date

import pandas as pd
import psycopg

from pipeline.features import build_daily_feature_row
from scoring.api import load_registered_model
from scoring.train import FEATURE_COLUMNS, get_shap_reasons


def select_alert_candidates(
    scored_accounts: list[dict],
    alert_budget: int = 50,
) -> list[dict]:
    if alert_budget <= 0:
        raise ValueError("alert_budget must be greater than zero")

    ranked_accounts = sorted(
        scored_accounts,
        key=lambda account: (
            -account["risk_score"],
            account["account_id"],
        ),
    )

    return ranked_accounts[:alert_budget]


def get_accounts_for_date(
    connection: psycopg.Connection,
    alert_date: date,
) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT account_id
            FROM (
                SELECT sender_account_id AS account_id
                FROM transactions
                WHERE timestamp::date = %s

                UNION

                SELECT receiver_account_id AS account_id
                FROM transactions
                WHERE timestamp::date = %s
            ) AS daily_accounts
            ORDER BY account_id
            """,
            (
                alert_date,
                alert_date,
            ),
        )
        rows = cursor.fetchall()

    return [row[0] for row in rows]


def score_accounts_for_date(
    connection: psycopg.Connection,
    alert_date: date,
    model,
) -> list[dict]:
    account_ids = get_accounts_for_date(
        connection=connection,
        alert_date=alert_date,
    )

    scored_accounts = []

    for account_id in account_ids:
        feature_row = build_daily_feature_row(
            connection=connection,
            account_id=account_id,
            feature_date=alert_date,
        )

        features = pd.DataFrame(
            [{column: feature_row[column] for column in FEATURE_COLUMNS}],
            columns=FEATURE_COLUMNS,
        )

        risk_score = float(model.predict_proba(features)[0, 1])

        reasons = get_shap_reasons(
            model=model,
            feature_row=feature_row,
            top_n=3,
        )

        scored_accounts.append(
            {
                "account_id": account_id,
                "risk_score": risk_score,
                "reasons": reasons,
            }
        )

    return scored_accounts


def insert_alerts(
    connection: psycopg.Connection,
    alert_date: date,
    candidates: list[dict],
    model_version: str,
) -> int:
    inserted_count = 0

    with connection.cursor() as cursor:
        for candidate in candidates:
            cursor.execute(
                """
                INSERT INTO alerts (
                    account_id,
                    alert_date,
                    risk_score,
                    model_version,
                    reasons,
                    status
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'NEW'
                )
                ON CONFLICT (
                    account_id,
                    alert_date
                )
                DO NOTHING
                RETURNING id
                """,
                (
                    candidate["account_id"],
                    alert_date,
                    candidate["risk_score"],
                    model_version,
                    json.dumps(candidate["reasons"]),
                ),
            )

            if cursor.fetchone() is not None:
                inserted_count += 1

    connection.commit()

    return inserted_count


def generate_daily_alerts(
    connection: psycopg.Connection,
    alert_date: date,
    alert_budget: int = 50,
    model_version: str = "1",
) -> dict:
    model = load_registered_model()

    scored_accounts = score_accounts_for_date(
        connection=connection,
        alert_date=alert_date,
        model=model,
    )

    candidates = select_alert_candidates(
        scored_accounts=scored_accounts,
        alert_budget=alert_budget,
    )

    inserted_count = insert_alerts(
        connection=connection,
        alert_date=alert_date,
        candidates=candidates,
        model_version=model_version,
    )

    threshold = candidates[-1]["risk_score"] if candidates else None

    return {
        "alert_date": alert_date,
        "accounts_scored": len(scored_accounts),
        "alert_budget": alert_budget,
        "threshold": threshold,
        "alerts_selected": len(candidates),
        "alerts_inserted": inserted_count,
    }
