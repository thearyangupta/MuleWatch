from agent.policy import validate_policy
from agent.report import CaseReport


def make_report(**overrides):
    data = {
        "summary": "Unusual transaction activity requires review.",
        "risk_rating": "MEDIUM",
        "recommended_action": "ENHANCED_MONITORING",
        "findings": [
            {
                "claim": "Multiple transfers were observed.",
                "evidence_ids": ["E1"],
            }
        ],
        "typology_matches": [],
        "open_questions": [],
        "confidence": 0.75,
    }

    data.update(overrides)

    return CaseReport.model_validate(data)


def test_valid_report_passes():
    result = validate_policy(make_report())

    assert result.passed is True
    assert result.violations == []


def test_high_risk_closure_rejected():
    report = make_report(
        risk_rating="HIGH",
        recommended_action="CLOSE_NO_ACTION",
    )

    result = validate_policy(report)

    assert result.passed is False


def test_low_confidence_closure_rejected():
    report = make_report(
        confidence=0.3,
        recommended_action="CLOSE_NO_ACTION",
    )

    result = validate_policy(report)

    assert result.passed is False


def test_missing_findings_rejected():
    report = make_report(findings=[])

    result = validate_policy(report)

    assert result.passed is False


def test_guilt_assertion_rejected():
    report = make_report(summary="The customer is a criminal.")

    result = validate_policy(report)

    assert result.passed is False


def test_prohibited_enforcement_rejected():
    report = make_report(summary="Freeze the account immediately.")

    result = validate_policy(report)

    assert result.passed is False


def test_protected_attribute_reasoning_rejected():
    report = make_report(summary="The account is suspicious because of their religion.")

    result = validate_policy(report)

    assert result.passed is False


def test_neutral_reference_to_protected_attribute():
    report = make_report(summary="The investigation must not infer risk from religion.")

    result = validate_policy(report)

    assert result.passed is True


def test_cited_typology_without_findings_is_allowed():
    report = make_report(
        findings=[],
        typology_matches=[
            {
                "typology": "Rapid movement",
                "explanation": "Retrieved guidance supports further review.",
                "evidence_id": "E2",
                "chunk_ids": ["chunk-1"],
            }
        ],
    )

    result = validate_policy(report)

    assert result.passed is True
