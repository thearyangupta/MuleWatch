from unittest.mock import patch

from agent.fallback import insufficient_evidence, manual_review
from agent.graph import assess, verify


def test_insufficient_evidence_status():
    result = insufficient_evidence()

    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.open_questions


def test_manual_review_status():
    result = manual_review()

    assert result.status == "NEEDS_MANUAL_REVIEW"
    assert result.open_questions


def test_custom_reason_preserved():
    result = manual_review("Gemini endpoint unavailable.")

    assert result.reason == "Gemini endpoint unavailable."


def test_fallback_does_not_claim_low_risk():
    result = manual_review()

    assert result.status != "LOW"


def make_state():
    return {
        "alert_id": 1,
        "alert": {"id": 1},
        "evidence": [],
        "messages": [],
        "steps_taken": 0,
        "limit_hit": False,
        "typology_checked": True,
        "report": None,
        "status": "VERIFYING",
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
    }


def test_assess_handles_model_failure():
    state = make_state()

    with patch(
        "agent.graph.generate_report",
        side_effect=RuntimeError("LLM unavailable"),
    ):
        result = assess(state, model=object())

    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert result["report"] is None


def test_assess_abstains_without_typology():
    state = make_state()
    state["typology_checked"] = False

    result = assess(state, model=object())

    assert result["status"] == "INSUFFICIENT_EVIDENCE"


def test_verify_preserves_manual_review():
    state = make_state()
    state["status"] = "NEEDS_MANUAL_REVIEW"

    result = verify(state, model=object())

    assert result == {}


def test_verify_rejects_policy_violation():
    state = make_state()

    state["report"] = {
        "summary": "Suspicious activity requires investigation.",
        "risk_rating": "HIGH",
        "recommended_action": "CLOSE_NO_ACTION",
        "findings": [
            {
                "claim": "Transfers require further investigation.",
                "evidence_ids": ["E1"],
            }
        ],
        "typology_matches": [],
        "open_questions": [],
        "confidence": 0.8,
    }

    state["evidence"] = [
        {
            "evidence_id": "E1",
            "source": "get_account_activity",
            "data": {"ok": True},
        }
    ]

    with patch(
        "agent.graph.generate_report",
        side_effect=RuntimeError("Retry unavailable"),
    ):
        result = verify(state, model=object())

    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert result["report"] is None
