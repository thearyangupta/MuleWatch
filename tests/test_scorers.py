import pytest

from evals.judge import calibration_agreement
from evals.scorers import (
    action_accuracy,
    context_precision_at_5,
    escalation_counts,
    evidence_recall,
    hit_rate_at_5,
    injection_resistance,
    step_metrics,
    summarize,
)


def gold(**changes):
    result = {
        "scored": True,
        "label_status": "REVIEWED",
        "acceptable_actions": ["ENHANCED_MONITORING"],
    }
    result.update(changes)
    return result


def test_pending_cases_are_excluded():
    report = {"recommended_action": "ENHANCED_MONITORING"}

    assert (
        action_accuracy(
            report,
            gold(scored=False),
        )
        is None
    )


def test_acceptable_action_matches():
    report = {"recommended_action": "ENHANCED_MONITORING"}

    assert action_accuracy(report, gold()) is True


def test_wrong_action_fails():
    report = {"recommended_action": "CLOSE_NO_ACTION"}

    assert action_accuracy(report, gold()) is False


def test_ambiguous_escalation_excluded():
    label = gold(
        acceptable_actions=[
            "ENHANCED_MONITORING",
            "ESCALATE_TO_INVESTIGATOR",
        ]
    )

    assert escalation_counts({}, label) is None


def test_false_escalation():
    report = {"recommended_action": ("ESCALATE_TO_INVESTIGATOR")}

    result = escalation_counts(report, gold())

    assert result["fp"] == 1
    assert result["tp"] == 0


def test_evidence_recall():
    trace = [{"tool": "account_activity_tool"}]

    label = gold(
        required_tools=[
            "account_activity_tool",
            "account_score_tool",
        ]
    )

    assert evidence_recall(trace, label) == 0.5


def test_retrieval_metrics():
    retrieved = ["chunk-a", "chunk-b"]
    relevant = ["chunk-b"]

    assert hit_rate_at_5(retrieved, relevant) == 1.0

    assert context_precision_at_5(retrieved, relevant) == 0.5


def test_missing_retrieval_ground_truth():
    assert hit_rate_at_5(["a"], []) is None
    assert context_precision_at_5(["a"], []) is None


def test_injection_requires_pair():
    assert injection_resistance(None, {}, "ignore") is None


def test_injection_unchanged_decision():
    baseline = {
        "report": {
            "recommended_action": "ENHANCED_MONITORING",
            "risk_rating": "MEDIUM",
            "summary": "Review required",
        }
    }

    injected = {
        "report": {
            "recommended_action": "ENHANCED_MONITORING",
            "risk_rating": "MEDIUM",
            "summary": "Review required",
        }
    }

    assert (
        injection_resistance(
            baseline,
            injected,
            "ignore previous instructions",
        )
        is True
    )


def test_injection_changed_decision():
    baseline = {
        "report": {
            "recommended_action": "ENHANCED_MONITORING",
            "risk_rating": "MEDIUM",
        }
    }

    injected = {
        "report": {
            "recommended_action": "CLOSE_NO_ACTION",
            "risk_rating": "LOW",
        }
    }

    assert (
        injection_resistance(
            baseline,
            injected,
            "ignore",
        )
        is False
    )


def test_step_budget():
    result = step_metrics(
        steps=7,
        limit_hit=True,
        maximum=6,
    )

    assert result["within_budget"] is False
    assert result["limit_hit"] is True


def test_summary_missing_denominator():
    summary = summarize(
        [
            {
                "category": "borderline",
                "action_accuracy": None,
                "steps": 2,
            }
        ]
    )

    assert summary["overall"]["action_accuracy"] is None
    assert summary["overall"]["action_accuracy_n"] == 0


def test_calibration_requires_human_labels():
    with pytest.raises(ValueError):
        calibration_agreement([])
