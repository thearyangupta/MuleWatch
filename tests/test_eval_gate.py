from copy import deepcopy

from evals.gate import evaluate


def complete_document():
    rows = {}
    case_ids = []

    for i in range(35):
        case_id = f"TEST-{i:03d}"
        case_ids.append(case_id)

        is_positive = i < 18
        rows[case_id] = {
            "case_id": case_id,
            "category": "injection" if i >= 30 else "clear",
            "scored": True,
            "label_status": "REVIEWED",
            "graph_executed": True,
            "status": "AWAITING_REVIEW",
            "error": None,
            "action_accuracy": True,
            "escalation_counts": (
                {"tp": 1, "fn": 0, "fp": 0, "tn": 0}
                if is_positive
                else {"tp": 0, "fn": 0, "fp": 0, "tn": 1}
            ),
            "citation_validity": True,
            "policy_pass": True,
            "injection_resistance": True if i >= 30 else None,
            "cost_usd": 0.01,
        }

    return {
        "signature": {
            "git_sha": "synthetic-test",
            "configurations": ["baseline"],
            "case_ids": case_ids,
        },
        "results": rows,
    }


def test_complete_reviewed_results_pass():
    passed, summary = evaluate(complete_document())
    assert passed, summary


def test_unreviewed_labels_block():
    doc = complete_document()
    doc["results"]["TEST-000"]["scored"] = False
    doc["results"]["TEST-000"]["label_status"] = "PENDING_HUMAN_REVIEW"

    passed, summary = evaluate(doc)
    assert not passed
    assert "Independent label review incomplete" in summary


def test_missing_injection_score_blocks():
    doc = complete_document()
    doc["results"]["TEST-030"]["injection_resistance"] = None

    passed, summary = evaluate(doc)
    assert not passed
    assert "Injection resistance: not measurable" in summary


def test_false_escalation_regression_blocks():
    doc = complete_document()
    for i in range(18, 23):
        doc["results"][f"TEST-{i:03d}"]["escalation_counts"] = {
            "tp": 0,
            "fn": 0,
            "fp": 1,
            "tn": 0,
        }

    passed, summary = evaluate(doc)
    assert not passed
    assert "False escalation rate: above threshold" in summary


def test_missing_cost_blocks():
    doc = complete_document()
    doc["results"]["TEST-000"].pop("cost_usd")

    passed, summary = evaluate(doc)
    assert not passed
    assert "Mean cost per case (USD): not measurable" in summary


def test_incomplete_coverage_blocks():
    doc = complete_document()
    del doc["results"]["TEST-034"]

    passed, summary = evaluate(doc)
    assert not passed
    assert "Incomplete, duplicated or unexpected case coverage" in summary


def test_multi_configuration_results_block():
    doc = deepcopy(complete_document())
    doc["signature"]["configurations"] = ["baseline", "prompt_v2"]

    passed, summary = evaluate(doc)
    assert not passed
    assert "Exactly one production configuration" in summary
