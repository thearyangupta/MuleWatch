from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from agent.tools import (
    get_account_activity,
    score_account,
    search_typologies,
)


@patch("agent.tools.get_counterparties")
@patch("agent.tools.get_transactions")
@patch("agent.tools.get_account_profile")
def test_get_account_activity_returns_evidence(
    mock_profile,
    mock_transactions,
    mock_counterparties,
):
    mock_profile.return_value = {
        "account_id": "ACC_TARGET",
        "opened_at": datetime(
            2025,
            1,
            1,
            tzinfo=UTC,
        ),
        "customer_id": 1,
        "name": "Alice Test",
        "email": "alice@example.com",
        "phone": "1111111111",
        "address": "Test Address",
        "occupation": "Analyst",
    }

    mock_transactions.return_value = [
        {
            "id": 1,
            "sender_account_id": "ACC_SENDER",
            "receiver_account_id": "ACC_TARGET",
            "transaction_type": "TRANSFER",
            "amount": Decimal("1000.00"),
            "timestamp": datetime(
                2026,
                1,
                10,
                10,
                0,
                tzinfo=UTC,
            ),
            "is_fraud": False,
        },
        {
            "id": 2,
            "sender_account_id": "ACC_TARGET",
            "receiver_account_id": "ACC_RECEIVER",
            "transaction_type": "TRANSFER",
            "amount": Decimal("900.00"),
            "timestamp": datetime(
                2026,
                1,
                10,
                11,
                0,
                tzinfo=UTC,
            ),
            "is_fraud": False,
        },
    ]

    mock_counterparties.return_value = [
        {
            "counterparty_account_id": "ACC_SENDER",
            "transaction_count": 1,
            "total_amount": Decimal("1000.00"),
        }
    ]

    evidence = get_account_activity(
        account_id="ACC_TARGET",
        days=30,
    )

    assert evidence.source == "get_account_activity"
    assert evidence.evidence_id.startswith("evidence-")

    assert evidence.data["ok"] is True
    assert evidence.data["total_incoming"] == 1000.0
    assert evidence.data["total_outgoing"] == 900.0
    assert evidence.data["pass_through_ratio"] == 0.9
    assert evidence.data["median_dwell_minutes"] == 60.0

    assert len(evidence.data["largest_transactions"]) == 2


@patch("agent.tools.get_account_profile")
def test_get_account_activity_unknown_account(
    mock_profile,
):
    mock_profile.return_value = None

    evidence = get_account_activity(
        account_id="UNKNOWN",
        days=30,
    )

    assert evidence.data["ok"] is False
    assert evidence.data["error"]["type"] == "account_not_found"


@patch("agent.tools.httpx.post")
def test_score_account_returns_evidence(
    mock_post,
):
    response = MagicMock()

    response.json.return_value = {
        "risk_score": 0.91,
        "model_version": "1",
        "reasons": [
            {
                "feature": "pass_through_ratio",
                "value": 0.97,
                "shap_value": 1.42,
            },
            {
                "feature": "fan_in",
                "value": 9.0,
                "shap_value": 0.81,
            },
        ],
    }

    response.raise_for_status.return_value = None

    mock_post.return_value = response

    evidence = score_account("ACC_TARGET")

    assert evidence.source == "score_account"
    assert evidence.evidence_id.startswith("evidence-")

    assert evidence.data["ok"] is True
    assert evidence.data["account_id"] == "ACC_TARGET"
    assert evidence.data["risk_score"] == 0.91
    assert evidence.data["model_version"] == "1"
    assert len(evidence.data["reasons"]) == 2

    mock_post.assert_called_once_with(
        "http://localhost:8000/score",
        json={
            "account_id": "ACC_TARGET",
        },
        timeout=10.0,
    )


@patch("agent.tools.hybrid_search")
def test_search_typologies_returns_citations(
    mock_search,
):
    mock_search.return_value = [
        {
            "chunk_id": "nca:money-mules:1",
            "content": "Funds may rapidly pass through mule accounts.",
            "source": "NCA",
            "title": "Money Mules",
            "section": "Indicators",
            "url": "https://example.com/money-mules",
            "source_date": "2026-01-01",
            "rrf_score": 0.032,
        }
    ]

    evidence = search_typologies(
        "rapid pass-through of funds",
    )

    assert evidence.source == "search_typologies"
    assert evidence.evidence_id.startswith("evidence-")

    assert evidence.data["ok"] is True
    assert evidence.data["query"] == "rapid pass-through of funds"

    chunks = evidence.data["chunks"]

    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == "nca:money-mules:1"
    assert chunks[0]["source"] == "NCA"
    assert chunks[0]["section"] == "Indicators"
    assert chunks[0]["url"] == "https://example.com/money-mules"

    mock_search.assert_called_once_with(
        "rapid pass-through of funds",
        limit=5,
    )
