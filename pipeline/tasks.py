import json
import os
from datetime import date

import httpx
import psycopg
from psycopg.rows import dict_row

from pipeline.alerts import insert_alerts, select_alert_candidates
from pipeline.features import build_daily_feature_row

DATABASE_URL = os.getenv(
    "MULEWATCH_DATABASE_URL",
    "postgresql://mulewatch:mulewatch_dev@localhost:5432/mulewatch",
)

SCORING_API_URL = os.getenv(
    "MULEWATCH_SCORING_API_URL",
    "http://127.0.0.1:8000",
)

SCORE_BATCH_SIZE = 500


def get_active_account_ids(
    connection: psycopg.Connection,
    feature_date: date,
) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT account_id
            FROM (
                SELECT sender_account_id AS account_id
                FROM transactions
                WHERE timestamp >= %s::date
                  AND timestamp < %s::date + INTERVAL '1 day'

                UNION

                SELECT receiver_account_id AS account_id
                FROM transactions
                WHERE timestamp >= %s::date
                  AND timestamp < %s::date + INTERVAL '1 day'
            ) AS active_accounts
            ORDER BY account_id
            """,
            (
                feature_date,
                feature_date,
                feature_date,
                feature_date,
            ),
        )

        return [row["account_id"] for row in cursor.fetchall()]


def upsert_feature_row(
    connection: psycopg.Connection,
    feature_row: dict,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO account_features (
                account_id,
                feature_date,
                pass_through_ratio,
                median_dwell_minutes,
                fan_in,
                fan_out,
                transfer_cashout_chains,
                account_age_days,
                velocity_ratio
            )
            VALUES (
                %(account_id)s,
                %(feature_date)s,
                %(pass_through_ratio)s,
                %(median_dwell_minutes)s,
                %(fan_in)s,
                %(fan_out)s,
                %(transfer_cashout_chains)s,
                %(account_age_days)s,
                %(velocity_ratio)s
            )
            ON CONFLICT (account_id, feature_date)
            DO UPDATE SET
                pass_through_ratio =
                    EXCLUDED.pass_through_ratio,
                median_dwell_minutes =
                    EXCLUDED.median_dwell_minutes,
                fan_in =
                    EXCLUDED.fan_in,
                fan_out =
                    EXCLUDED.fan_out,
                transfer_cashout_chains =
                    EXCLUDED.transfer_cashout_chains,
                account_age_days =
                    EXCLUDED.account_age_days,
                velocity_ratio =
                    EXCLUDED.velocity_ratio,
                updated_at = NOW()
            """,
            feature_row,
        )


def build_features_for_date(
    feature_date: date,
    database_url: str = DATABASE_URL,
) -> dict:
    with psycopg.connect(
        database_url,
        row_factory=dict_row,
    ) as connection:
        account_ids = get_active_account_ids(
            connection,
            feature_date,
        )

        for account_id in account_ids:
            feature_row = build_daily_feature_row(
                connection=connection,
                account_id=account_id,
                feature_date=feature_date,
            )

            upsert_feature_row(
                connection,
                feature_row,
            )

    return {
        "feature_date": feature_date.isoformat(),
        "account_count": len(account_ids),
    }


def get_feature_account_ids(
    connection: psycopg.Connection,
    feature_date: date,
) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT account_id
            FROM account_features
            WHERE feature_date = %s
            ORDER BY account_id
            """,
            (feature_date,),
        )

        return [row["account_id"] for row in cursor.fetchall()]


def chunk_account_ids(
    account_ids: list[str],
    chunk_size: int = SCORE_BATCH_SIZE,
):
    for start in range(
        0,
        len(account_ids),
        chunk_size,
    ):
        yield account_ids[start : start + chunk_size]


def upsert_scores(
    connection: psycopg.Connection,
    score_date: date,
    scores: list[dict],
) -> None:
    if not scores:
        return

    rows = [
        (
            score["account_id"],
            score_date,
            score["risk_score"],
            score["model_version"],
            json.dumps(score["reasons"]),
        )
        for score in scores
    ]

    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO account_scores (
                account_id,
                score_date,
                risk_score,
                model_version,
                reasons
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s
            )
            ON CONFLICT (
                account_id,
                score_date
            )
            DO UPDATE SET
                risk_score = EXCLUDED.risk_score,
                model_version = EXCLUDED.model_version,
                reasons = EXCLUDED.reasons,
                updated_at = NOW()
            """,
            rows,
        )


def score_features_for_date(
    feature_date: date,
    database_url: str = DATABASE_URL,
    scoring_api_url: str = SCORING_API_URL,
) -> dict:
    with psycopg.connect(
        database_url,
        row_factory=dict_row,
    ) as connection:
        account_ids = get_feature_account_ids(
            connection,
            feature_date,
        )

    scored_count = 0
    model_versions = set()

    with httpx.Client(timeout=60.0) as client:
        with psycopg.connect(database_url) as connection:
            for account_chunk in chunk_account_ids(account_ids):
                response = client.post(
                    f"{scoring_api_url}/score/batch",
                    json={
                        "account_ids": account_chunk,
                        "feature_date": (feature_date.isoformat()),
                    },
                )

                response.raise_for_status()

                scores = response.json()["scores"]

                for score in scores:
                    model_versions.add(score["model_version"])

                upsert_scores(
                    connection=connection,
                    score_date=feature_date,
                    scores=scores,
                )

                scored_count += len(scores)

    if len(model_versions) > 1:
        raise ValueError(
            f"Multiple model versions returned for one scoring run: {model_versions}"
        )

    model_version = next(iter(model_versions)) if model_versions else "unknown"

    return {
        "feature_date": feature_date.isoformat(),
        "scored_count": scored_count,
        "model_version": model_version,
    }


def create_alerts_for_date(
    alert_date: date,
    database_url: str = DATABASE_URL,
    alert_budget: int = 50,
) -> dict:
    with psycopg.connect(
        database_url,
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    account_id,
                    risk_score,
                    model_version,
                    reasons
                FROM account_scores
                WHERE score_date = %s
                ORDER BY risk_score DESC, account_id
                """,
                (alert_date,),
            )

            scored_accounts = cursor.fetchall()

        if not scored_accounts:
            raise ValueError(f"No scores found for {alert_date}")

        model_versions = {account["model_version"] for account in scored_accounts}

        if len(model_versions) != 1:
            raise ValueError(
                "Expected exactly one model version "
                f"for {alert_date}, got {model_versions}"
            )

        candidates = select_alert_candidates(
            scored_accounts=scored_accounts,
            alert_budget=alert_budget,
        )

        threshold = candidates[-1]["risk_score"] if candidates else None

        model_version = next(iter(model_versions))

        inserted_count = insert_alerts(
            connection=connection,
            alert_date=alert_date,
            candidates=candidates,
            model_version=model_version,
            threshold=threshold,
        )

    return {
        "alert_date": alert_date.isoformat(),
        "accounts_scored": len(scored_accounts),
        "alerts_selected": len(candidates),
        "alerts_inserted": inserted_count,
        "model_version": model_version,
        "threshold": threshold,
    }
