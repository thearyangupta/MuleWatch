import os
import secrets
import uuid
from datetime import datetime

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException
from langgraph.types import Command
from psycopg.rows import dict_row
from pydantic import BaseModel

from agent.graph import CASE_DATABASE_URL, MODEL_NAME, PROMPT_PATH, initial_state
from agent.review_runtime import review_graph, thread_config
from agent.state_machine import InvalidTransition, ReviewDecision
from agent.tracing import (
    configured_trace_seed,
    investigation_trace,
    prompt_version_id,
)

router = APIRouter(prefix="/cases", tags=["Case Review"])


def traced_config(config: dict, handler) -> dict:
    """Attach tracing without modifying the original config."""
    if handler is None:
        return config

    return {
        **config,
        "callbacks": [handler],
    }


def require_reviewer(
    x_review_api_key: str | None = Header(default=None),
) -> None:
    expected = os.getenv("MULEWATCH_REVIEW_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Review authentication is not configured",
        )

    if not x_review_api_key or not secrets.compare_digest(x_review_api_key, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid review API key",
        )


def get_case_row(case_id: int) -> dict:
    with psycopg.connect(CASE_DATABASE_URL, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, alert_id, status, summary, report,
                       thread_id, agent_action, final_action,
                       review_decision, reviewer_id,
                       reviewer_comment, reviewed_at, agreement
                FROM cases
                WHERE id = %s
                """,
                (case_id,),
            )
            row = cursor.fetchone()

    if row is None:
        raise HTTPException(404, "Case not found")

    return row


class CaseListItem(BaseModel):
    id: int
    alert_id: int
    status: str
    summary: str | None
    agent_action: str | None
    final_action: str | None
    reviewer_id: str | None
    reviewed_at: datetime | None
    agreement: bool | None


@router.get(
    "",
    response_model=list[CaseListItem],
    dependencies=[Depends(require_reviewer)],
)
def list_cases(status: str | None = None):
    if status is not None and status not in {
        "AWAITING_REVIEW",
        "CLOSED",
        "ESCALATED",
        "NEEDS_MANUAL_REVIEW",
        "INSUFFICIENT_EVIDENCE",
        "COMPLETE",
    }:
        raise HTTPException(422, "Unsupported case status")

    with psycopg.connect(CASE_DATABASE_URL, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, alert_id, status, summary,
                       agent_action, final_action,
                       reviewer_id, reviewed_at, agreement
                FROM cases
                WHERE (%s::text IS NULL OR status = %s)
                ORDER BY created_at DESC, id DESC
                LIMIT 100
                """,
                (status, status),
            )
            return cursor.fetchall()


@router.get(
    "/{case_id}",
    dependencies=[Depends(require_reviewer)],
)
def get_case(case_id: int):
    return get_case_row(case_id)


@router.post(
    "/{case_id}/decision",
    dependencies=[Depends(require_reviewer)],
)
def decide_case(case_id: int, decision: ReviewDecision):
    with psycopg.connect(CASE_DATABASE_URL) as lock_connection:
        with lock_connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s)",
                (case_id,),
            )
            locked = cursor.fetchone()[0]

        if not locked:
            raise HTTPException(409, "Another review is in progress")

        try:
            case = get_case_row(case_id)

            if case["status"] != "AWAITING_REVIEW":
                raise HTTPException(
                    409,
                    "Case is not awaiting review",
                )

            if not case["thread_id"] or not case["report"]:
                raise HTTPException(
                    409,
                    "Review checkpoint or report missing",
                )

            from agent.report import CaseReport

            agent_action = CaseReport.model_validate(case["report"]).recommended_action

            try:
                decision.resolved_action(agent_action)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

            config = thread_config(case["thread_id"])

            with review_graph() as graph:
                snapshot = graph.get_state(config)

                if not snapshot.next or ("review" not in snapshot.next):
                    raise HTTPException(
                        409,
                        "Graph is not paused for review",
                    )

                with investigation_trace(
                    source="api_review_resume",
                    model=MODEL_NAME,
                    prompt_version=prompt_version_id(PROMPT_PATH),
                    git_sha=os.getenv("MULEWATCH_GIT_SHA", "unknown"),
                    correlation_seed=configured_trace_seed(case["thread_id"]),
                ) as handler:
                    result = graph.invoke(
                        Command(resume=decision.model_dump(mode="json")),
                        config=traced_config(config, handler),
                    )

                    if handler is not None:
                        handler.record_metrics(result)

            if result.get("__interrupt__"):
                raise HTTPException(409, "Review was not finalized")

            return get_case_row(case_id)

        except InvalidTransition as exc:
            raise HTTPException(409, str(exc)) from exc

        finally:
            with lock_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_unlock(%s)",
                    (case_id,),
                )


class StartInvestigationResponse(BaseModel):
    case_id: int
    status: str
    report: dict | None


def start_review_investigation(
    alert_id: int,
) -> StartInvestigationResponse:
    if alert_id < 1:
        raise HTTPException(422, "alert_id must be positive")

    thread_id = str(uuid.uuid4())
    config = thread_config(thread_id)

    try:
        with investigation_trace(
            source="api_investigation",
            model=MODEL_NAME,
            prompt_version=prompt_version_id(PROMPT_PATH),
            git_sha=os.getenv("MULEWATCH_GIT_SHA", "unknown"),
            correlation_seed=configured_trace_seed(thread_id),
        ) as handler:
            with review_graph() as graph:
                result = graph.invoke(
                    initial_state(
                        alert_id,
                        thread_id=thread_id,
                        human_review=True,
                    ),
                    config=traced_config(config, handler),
                )

                snapshot = graph.get_state(config)
                state = snapshot.values or result

                if handler is not None:
                    handler.record_metrics(state)

    except ValueError as exc:
        if str(exc) == f"Alert {alert_id} not found":
            raise HTTPException(404, "Alert not found") from exc
        raise

    if state.get("status") == "AWAITING_REVIEW":
        if "review" not in snapshot.next:
            raise HTTPException(
                500,
                "Expected persisted review interruption",
            )

    return StartInvestigationResponse(
        case_id=state["case_id"],
        status=state["status"],
        report=state.get("report"),
    )
