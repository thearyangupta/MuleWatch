import pytest
from pydantic import ValidationError

from agent.report import CaseReport
from agent.verify import (
    CitationVerificationError,
    verify_report,
)


@pytest.fixture
def evidence():
    return [
        {
            "evidence_id": "E1",
            "source": "get_account_activity",
            "summary": "Account activity",
            "data": {
                "ok": True,
                "total_incoming": 100000,
            },
        },
        {
            "evidence_id": "E2",
            "source": "search_typologies",
            "summary": "Typology search",
            "data": {
                "ok": True,
                "chunks": [
                    {
                        "chunk_id": "chunk-1",
                        "content": "Rapid movement of funds",
                    }
                ],
            },
        },
    ]


@pytest.fixture
def valid_report():
    return {
        "summary": "Potential rapid pass-through activity.",
        "risk_rating": "MEDIUM",
        "recommended_action": "ENHANCED_MONITORING",
        "findings": [
            {
                "claim": "Account received 100000.",
                "evidence_ids": ["E1"],
            }
        ],
        "typology_matches": [
            {
                "typology": "Rapid movement of funds",
                "explanation": "Pattern warrants investigation.",
                "evidence_id": "E2",
                "chunk_ids": ["chunk-1"],
            }
        ],
        "open_questions": [],
        "confidence": 0.7,
    }


def test_valid_report_passes(evidence, valid_report):
    report = CaseReport.model_validate(valid_report)
    verify_report(report, evidence)


def test_unknown_evidence_rejected(evidence, valid_report):
    valid_report["findings"][0]["evidence_ids"] = ["E999"]

    report = CaseReport.model_validate(valid_report)

    with pytest.raises(CitationVerificationError):
        verify_report(report, evidence)


def test_unknown_typology_chunk_rejected(evidence, valid_report):
    valid_report["typology_matches"][0]["chunk_ids"] = ["invented-chunk"]

    report = CaseReport.model_validate(valid_report)

    with pytest.raises(CitationVerificationError):
        verify_report(report, evidence)


def test_wrong_typology_source_rejected(evidence, valid_report):
    valid_report["typology_matches"][0]["evidence_id"] = "E1"

    report = CaseReport.model_validate(valid_report)

    with pytest.raises(CitationVerificationError):
        verify_report(report, evidence)


def test_freeze_action_rejected(valid_report):
    valid_report["recommended_action"] = "FREEZE_ACCOUNT"

    with pytest.raises(ValidationError):
        CaseReport.model_validate(valid_report)


def test_invalid_confidence_rejected(valid_report):
    valid_report["confidence"] = 1.5

    with pytest.raises(ValidationError):
        CaseReport.model_validate(valid_report)
