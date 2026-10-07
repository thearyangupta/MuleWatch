import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, Field

from agent.evidence import EvidenceItem, create_evidence
from db.queries import (
    get_account_profile,
    get_counterparties,
    get_transactions,
)
from pipeline.features import (
    calculate_median_dwell_time,
    calculate_pass_through_ratio,
)
from rag.search import hybrid_search

SCORE_API_URL = os.getenv(
    "MULEWATCH_SCORE_API_URL",
    "http://localhost:8000",
)


class AccountActivityInput(BaseModel):
    account_id: str = Field(min_length=1)
    days: int = Field(default=30, ge=1, le=365)


class ScoreAccountInput(BaseModel):
    account_id: str = Field(min_length=1)


class SearchTypologiesInput(BaseModel):
    query: str = Field(min_length=1)


def _serialise(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _serialise(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_serialise(item) for item in value]

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    return value


def _error_evidence(
    *,
    source: str,
    error_type: str,
    message: str,
) -> EvidenceItem:
    return create_evidence(
        source=source,
        summary=f"{source} failed",
        data={
            "ok": False,
            "error": {
                "type": error_type,
                "message": message,
            },
        },
    )


def get_account_activity(
    account_id: str,
    days: int = 30,
) -> EvidenceItem:
    """Return a compact read-only activity profile for an account."""

    try:
        arguments = AccountActivityInput(
            account_id=account_id,
            days=days,
        )

        profile = get_account_profile(arguments.account_id)

        if profile is None:
            return _error_evidence(
                source="get_account_activity",
                error_type="account_not_found",
                message=f"Account {arguments.account_id} was not found",
            )

        transactions = get_transactions(
            arguments.account_id,
            arguments.days,
        )

        counterparties = get_counterparties(
            arguments.account_id,
        )

        incoming = [
            transaction
            for transaction in transactions
            if transaction["receiver_account_id"] == arguments.account_id
        ]

        outgoing = [
            transaction
            for transaction in transactions
            if transaction["sender_account_id"] == arguments.account_id
        ]

        total_incoming = sum(float(transaction["amount"]) for transaction in incoming)

        total_outgoing = sum(float(transaction["amount"]) for transaction in outgoing)

        pass_through_ratio = calculate_pass_through_ratio(
            incoming_amount=total_incoming,
            outgoing_amount=total_outgoing,
        )

        median_dwell_minutes = calculate_median_dwell_time(
            inbound_times=sorted(transaction["timestamp"] for transaction in incoming),
            outbound_times=sorted(transaction["timestamp"] for transaction in outgoing),
        )

        largest_transactions = sorted(
            transactions,
            key=lambda transaction: float(transaction["amount"]),
            reverse=True,
        )[:10]

        data = {
            "ok": True,
            "account": _serialise(profile),
            "window_days": arguments.days,
            "total_incoming": total_incoming,
            "total_outgoing": total_outgoing,
            "pass_through_ratio": pass_through_ratio,
            "median_dwell_minutes": median_dwell_minutes,
            "top_counterparties": [
                _serialise(counterparty) for counterparty in counterparties[:10]
            ],
            "largest_transactions": [
                _serialise(transaction) for transaction in largest_transactions
            ],
        }

        return create_evidence(
            source="get_account_activity",
            summary=(
                f"{arguments.days}-day activity profile "
                f"for account {arguments.account_id}"
            ),
            data=data,
        )

    except Exception as exc:
        return _error_evidence(
            source="get_account_activity",
            error_type=type(exc).__name__,
            message=str(exc),
        )


def score_account(
    account_id: str,
) -> EvidenceItem:
    """Score an account using MuleWatch's existing scoring API."""

    try:
        arguments = ScoreAccountInput(
            account_id=account_id,
        )

        response = httpx.post(
            f"{SCORE_API_URL}/score",
            json={
                "account_id": arguments.account_id,
            },
            timeout=10.0,
        )

        response.raise_for_status()

        result = response.json()

        data = {
            "ok": True,
            "account_id": arguments.account_id,
            "risk_score": result["risk_score"],
            "model_version": result["model_version"],
            "reasons": result["reasons"],
        }

        return create_evidence(
            source="score_account",
            summary=(
                f"Model score for account "
                f"{arguments.account_id}: "
                f"{result['risk_score']:.4f}"
            ),
            data=data,
        )

    except httpx.HTTPStatusError as exc:
        return _error_evidence(
            source="score_account",
            error_type="http_error",
            message=(f"Scoring API returned HTTP {exc.response.status_code}"),
        )

    except Exception as exc:
        return _error_evidence(
            source="score_account",
            error_type=type(exc).__name__,
            message=str(exc),
        )


def search_typologies(
    query: str,
) -> EvidenceItem:
    """Search the typology knowledge base for relevant guidance."""

    try:
        arguments = SearchTypologiesInput(
            query=query,
        )

        results = hybrid_search(
            arguments.query,
            limit=5,
        )

        chunks = [
            {
                "chunk_id": result["chunk_id"],
                "content": result["content"],
                "source": result["source"],
                "title": result["title"],
                "section": result["section"],
                "url": result["url"],
                "source_date": _serialise(result["source_date"]),
                "rrf_score": result["rrf_score"],
            }
            for result in results
        ]

        return create_evidence(
            source="search_typologies",
            summary=(
                f"Retrieved {len(chunks)} typology chunks for query: {arguments.query}"
            ),
            data={
                "ok": True,
                "query": arguments.query,
                "chunks": chunks,
            },
        )

    except Exception as exc:
        return _error_evidence(
            source="search_typologies",
            error_type=type(exc).__name__,
            message=str(exc),
        )
