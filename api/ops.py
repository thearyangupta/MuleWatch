"""Lead-only operational and quality metrics."""

import json
from datetime import date
from pathlib import Path

import psycopg
from fastapi import APIRouter, Depends
from psycopg.rows import dict_row
from pydantic import BaseModel

from agent.graph import CASE_DATABASE_URL
from api.auth import require_lead

router = APIRouter(
    prefix="/ops",
    tags=["Operations"],
    dependencies=[Depends(require_lead)],
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_SUMMARY_PATH = PROJECT_ROOT / "evals" / "results" / "summary.json"


class PipelineDay(BaseModel):
    run_date: date
    rows_in: int
    rows_quarantined: int
    accounts_scored: int
    alerts_raised: int


class AlertDay(BaseModel):
    alert_date: date
    alert_count: int


class ReviewQuality(BaseModel):
    reviewed_cases: int
    compared_cases: int
    agreed_cases: int
    agreement_rate: float | None


class OpsSummary(BaseModel):
    pipeline: list[PipelineDay]
    alerts_by_day: list[AlertDay]
    review_quality: ReviewQuality
    evaluation: dict | None
    evaluation_status: str
    average_cost_usd: float | None
    cost_status: str


def load_evaluation_summary() -> tuple[dict | None, str]:
    if not EVAL_SUMMARY_PATH.is_file():
        return None, "NOT MEASURED: evaluation summary unavailable"

    try:
        data = json.loads(EVAL_SUMMARY_PATH.read_text(encoding="utf-8-sig"))
    except OSError, ValueError:
        return None, "UNAVAILABLE: evaluation summary cannot be read"

    if not isinstance(data, dict):
        return None, "UNAVAILABLE: invalid evaluation summary"

    allowed = (
        "action_accuracy",
        "citation_validity",
        "policy_pass",
        "escalation_recall",
        "false_escalation_rate",
        "injection_resistance",
        "graph_execution",
        "limitations",
    )
    return {key: data[key] for key in allowed if key in data}, "AVAILABLE"


@router.get("/summary", response_model=OpsSummary)
def get_ops_summary(days: int = 30) -> OpsSummary:
    if not 1 <= days <= 90:
        from fastapi import HTTPException

        raise HTTPException(422, "days must be between 1 and 90")

    with psycopg.connect(
        CASE_DATABASE_URL,
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT run_date, rows_in, rows_quarantined,
                       accounts_scored, alerts_raised
                FROM pipeline_runs
                WHERE run_date >= CURRENT_DATE - (%s - 1)
                ORDER BY run_date
                """,
                (days,),
            )
            pipeline = cursor.fetchall()

            cursor.execute(
                """
                SELECT alert_date, COUNT(*)::int AS alert_count
                FROM alerts
                WHERE alert_date >= CURRENT_DATE - (%s - 1)
                GROUP BY alert_date
                ORDER BY alert_date
                """,
                (days,),
            )
            alerts = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE reviewed_at IS NOT NULL
                    )::int AS reviewed_cases,
                    COUNT(*) FILTER (
                        WHERE reviewed_at IS NOT NULL
                          AND agreement IS NOT NULL
                    )::int AS compared_cases,
                    COUNT(*) FILTER (
                        WHERE reviewed_at IS NOT NULL
                          AND agreement IS TRUE
                    )::int AS agreed_cases
                FROM cases
                WHERE reviewed_at >= CURRENT_DATE - (%s - 1)
                """,
                (days,),
            )
            quality = cursor.fetchone()

    reviewed = quality["reviewed_cases"]
    compared = quality["compared_cases"]
    agreed = quality["agreed_cases"]

    evaluation, evaluation_status = load_evaluation_summary()

    return OpsSummary(
        pipeline=[PipelineDay(**row) for row in pipeline],
        alerts_by_day=[AlertDay(**row) for row in alerts],
        review_quality=ReviewQuality(
            reviewed_cases=reviewed,
            compared_cases=compared,
            agreed_cases=agreed,
            agreement_rate=agreed / compared if compared else None,
        ),
        evaluation=evaluation,
        evaluation_status=evaluation_status,
        average_cost_usd=None,
        cost_status=(
            "NOT MEASURED: per-case cost is not yet "
            "persisted in the operational database"
        ),
    )
