import math
import os
import re
import uuid
from datetime import date, datetime
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from langgraph.types import Command
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from agent.graph import CASE_DATABASE_URL, MODEL_NAME, PROMPT_PATH, initial_state
from agent.report import RecommendedAction
from agent.review_runtime import review_graph, thread_config
from agent.state_machine import InvalidTransition, ReviewDecision
from agent.tracing import (
    configured_trace_seed,
    investigation_trace,
    prompt_version_id,
)
from api.auth import AuthenticatedUser, current_user

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
    user: AuthenticatedUser = Depends(current_user),
) -> AuthenticatedUser:
    """Allow authenticated analysts and leads to review cases."""
    return user


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
    id: int | None
    alert_id: int
    alert_date: date
    account_id: str
    risk_score: float
    risk: Literal["LOW", "MEDIUM", "HIGH"]
    status: str
    summary: str | None
    agent_action: str | None
    final_action: str | None
    reviewer_id: str | None
    reviewed_at: datetime | None
    agreement: bool | None
    created_at: datetime


class PaginatedCases(BaseModel):
    items: list[CaseListItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class AlertInvestigationStatus(BaseModel):
    alert_id: int
    case_id: int | None
    status: str


RISK_SQL = """CASE WHEN a.risk_score >= 0.70 THEN 'HIGH'
                    WHEN a.risk_score >= 0.40 THEN 'MEDIUM'
                    ELSE 'LOW' END"""


@router.get("", response_model=PaginatedCases, dependencies=[Depends(require_reviewer)])
def list_cases(
    status: str | None = None,
    risk: Literal["LOW", "MEDIUM", "HIGH"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: Literal["newest", "oldest"] = "newest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedCases:
    allowed_statuses = {
        "NEW",
        "OPEN",
        "INVESTIGATING",
        "AWAITING_REVIEW",
        "CLOSED",
        "ESCALATED",
        "NEEDS_MANUAL_REVIEW",
        "INSUFFICIENT_EVIDENCE",
        "COMPLETE",
    }
    if status is not None and status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Unsupported case status")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not exceed date_to")

    joins = """FROM alerts a
        LEFT JOIN LATERAL (
            SELECT id, status, summary, agent_action, final_action,
                   reviewer_id, reviewed_at, agreement
            FROM cases
            WHERE alert_id = a.id
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        ) c ON TRUE"""
    where = f"""WHERE (%s::text IS NULL OR COALESCE(c.status, a.status) = %s)
        AND (%s::text IS NULL OR ({RISK_SQL}) = %s)
        AND (%s::date IS NULL OR a.alert_date >= %s::date)
        AND (%s::date IS NULL OR a.alert_date <= %s::date)"""
    params = (status, status, risk, risk, date_from, date_from, date_to, date_to)
    direction = "DESC" if sort == "newest" else "ASC"
    with psycopg.connect(CASE_DATABASE_URL, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total {joins} {where}", params)
            count_row = cursor.fetchone()
            total = int(count_row["total"]) if count_row else 0
            cursor.execute(
                f"""SELECT c.id, a.id AS alert_id, a.alert_date, a.account_id,
                           a.risk_score, {RISK_SQL} AS risk,
                           COALESCE(c.status, a.status) AS status,
                           c.summary, c.agent_action, c.final_action,
                           c.reviewer_id, c.reviewed_at, c.agreement, a.created_at
                    {joins} {where}
                    ORDER BY a.created_at {direction}, a.id {direction}
                    LIMIT %s OFFSET %s""",
                (*params, page_size, (page - 1) * page_size),
            )
            rows = cursor.fetchall()
    return PaginatedCases(
        items=[CaseListItem(**row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get(
    "/alerts/{alert_id}/status",
    response_model=AlertInvestigationStatus,
    dependencies=[Depends(require_reviewer)],
)
def get_alert_investigation_status(alert_id: int) -> AlertInvestigationStatus:
    with psycopg.connect(CASE_DATABASE_URL, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT a.id AS alert_id, c.id AS case_id,
                          COALESCE(c.status, a.status) AS status
                   FROM alerts a
                   LEFT JOIN LATERAL (
                       SELECT id, status FROM cases
                       WHERE alert_id = a.id
                       ORDER BY created_at DESC, id DESC LIMIT 1
                   ) c ON TRUE
                   WHERE a.id = %s""",
                (alert_id,),
            )
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertInvestigationStatus(**row)


@router.get(
    "/{case_id}",
    dependencies=[Depends(require_reviewer)],
)
def get_case(case_id: int):
    return get_case_row(case_id)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "override", "escalate"]
    comment: str = Field(min_length=1, max_length=2000)
    final_action: RecommendedAction | None = None


@router.post("/{case_id}/decision")
def decide_case(
    case_id: int,
    request: DecisionRequest,
    user: AuthenticatedUser = Depends(current_user),
):
    decision = ReviewDecision.model_validate(
        {
            **request.model_dump(mode="json"),
            "reviewer_id": user.username,
        }
    )
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


class CaseEvidenceDetail(BaseModel):
    """Case view projection: masked identity, report, trace and linked evidence."""

    case_id: int
    alert_id: int
    account_token: str
    status: str
    risk_score: float
    model_version: str
    prompt_version: str | None
    report: dict | None
    evidence: list[dict]
    model_reasons: object
    tool_trace: object
    warnings: list[str]


def _safe_citation_id(value: object) -> bool:
    """Only opaque, bounded citation identifiers may reach the browser."""
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value) is not None
    )


def _safe_case_report(report: dict | None) -> dict | None:
    """Preserve structured decisions and references, not unreviewed prose."""
    if report is None:
        return None

    safe = {
        "summary": "Narrative withheld pending privacy review.",
        "findings": [],
        "typology_matches": [],
        "open_questions": [],
    }

    if report.get("risk_rating") in ("LOW", "MEDIUM", "HIGH"):
        safe["risk_rating"] = report["risk_rating"]

    if report.get("recommended_action") in (
        "CLOSE_NO_ACTION",
        "ENHANCED_MONITORING",
        "ESCALATE_TO_INVESTIGATOR",
    ):
        safe["recommended_action"] = report["recommended_action"]

    confidence = report.get("confidence")
    if (
        isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
        and math.isfinite(confidence)
        and 0 <= confidence <= 1
    ):
        safe["confidence"] = confidence

    for finding in report.get("findings", []):
        if not isinstance(finding, dict):
            continue
        ids = finding.get("evidence_ids", [])
        if not isinstance(ids, list):
            continue
        refs = [item for item in ids if _safe_citation_id(item)]
        if refs:
            safe["findings"].append(
                {
                    "claim": "Finding narrative withheld pending privacy review.",
                    "evidence_ids": refs,
                }
            )

    for match in report.get("typology_matches", []):
        if not isinstance(match, dict):
            continue
        ref = match.get("evidence_id")
        if not _safe_citation_id(ref):
            continue
        chunks = match.get("chunk_ids", [])
        if not isinstance(chunks, list):
            chunks = []
        safe["typology_matches"].append(
            {
                "typology": "Typology narrative withheld",
                "explanation": "Explanation withheld pending privacy review.",
                "evidence_id": ref,
                "chunk_ids": [item for item in chunks if _safe_citation_id(item)],
            }
        )

    return safe


def _safe_model_reasons(value: object) -> list[dict]:
    """Only trained feature names and finite numeric values are exposed."""
    from scoring.train import FEATURE_COLUMNS

    allowed = set(FEATURE_COLUMNS)
    if not isinstance(value, list):
        return []

    safe = []
    for item in value:
        if not isinstance(item, dict):
            continue
        feature = item.get("feature")
        if not isinstance(feature, str) or feature not in allowed:
            continue

        projected = {"feature": feature}
        for key in ("value", "shap_value"):
            number = item.get(key)
            if (
                isinstance(number, (int, float))
                and not isinstance(number, bool)
                and math.isfinite(number)
            ):
                projected[key] = number

        if "shap_value" in projected:
            safe.append(projected)

    return safe


def _safe_evidence_data(value: object) -> dict:
    """Expose only numeric measurements; raw text may contain customer PII."""
    if not isinstance(value, dict):
        return {}
    safe = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key) is None
            or any(
                term in key
                for term in (
                    "account",
                    "customer",
                    "phone",
                    "email",
                    "address",
                    "name",
                    "iban",
                    "pan",
                    "aadhaar",
                    "identifier",
                    "reference",
                    "token",
                    "secret",
                )
            )
        ):
            continue
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            safe[key] = item
        elif isinstance(item, dict):
            nested = _safe_evidence_data(item)
            if nested:
                safe[key] = nested
    return safe


def _evidence_from_trace(value: object) -> list[dict]:
    """Find evidence-shaped objects without inventing evidence or citations."""
    found: dict[str, dict] = {}

    def walk(node: object, depth: int = 0) -> None:
        if depth > 12:
            return
        if isinstance(node, dict):
            identifier = node.get("evidence_id")
            if _safe_citation_id(identifier):
                found.setdefault(
                    identifier,
                    {
                        "evidence_id": identifier,
                        "source": "Stored investigation evidence",
                        "summary": "Evidence record (sensitive text withheld)",
                        "data": _safe_evidence_data(node.get("data")),
                    },
                )
            for child in node.values():
                walk(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                walk(child, depth + 1)

    walk(value)
    return list(found.values())


@router.get(
    "/{case_id}/evidence",
    response_model=CaseEvidenceDetail,
    dependencies=[Depends(require_reviewer)],
)
def get_case_evidence(case_id: int) -> CaseEvidenceDetail:
    with psycopg.connect(CASE_DATABASE_URL, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT c.id AS case_id, c.alert_id, c.status, c.report,
                          c.tool_trace, a.account_id, a.risk_score,
                          a.model_version, a.reasons
                   FROM cases c JOIN alerts a ON a.id = c.alert_id
                   WHERE c.id = %s""",
                (case_id,),
            )
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")

    report = row["report"] if isinstance(row["report"], dict) else None
    trace = row["tool_trace"]
    evidence = _evidence_from_trace(trace)
    cited = set()
    if report:
        for finding in report.get("findings", []):
            if isinstance(finding, dict):
                cited.update(
                    x for x in finding.get("evidence_ids", []) if _safe_citation_id(x)
                )
        for match in report.get("typology_matches", []):
            if isinstance(match, dict) and _safe_citation_id(match.get("evidence_id")):
                cited.add(match["evidence_id"])
    available = {item["evidence_id"] for item in evidence}
    warnings = []
    if report is None:
        warnings.append("No structured report is available for this case.")
    if cited - available:
        warnings.append(
            "Some cited evidence is not available in the stored tool trace."
        )
    if not evidence:
        warnings.append("No evidence items were found in the stored tool trace.")
    if isinstance(trace, (dict, list)):
        trace_text = str(trace).lower()
        if "possible_injection" in trace_text or "prompt_injection" in trace_text:
            warnings.append("Possible prompt injection: review the source evidence.")
    account_id = str(row["account_id"])
    return CaseEvidenceDetail(
        case_id=row["case_id"],
        alert_id=row["alert_id"],
        account_token="****" + account_id[-4:],
        status=row["status"],
        risk_score=row["risk_score"],
        model_version=row["model_version"],
        prompt_version=prompt_version_id(PROMPT_PATH),
        report=_safe_case_report(report),
        evidence=evidence,
        model_reasons=_safe_model_reasons(row["reasons"]),
        tool_trace={},  # Never expose raw trace: it can contain PII/untrusted text.
        warnings=warnings,
    )
