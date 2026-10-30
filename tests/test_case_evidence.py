from fastapi.testclient import TestClient

from scoring.api import app


def test_evidence_requires_configured_auth(monkeypatch):
    monkeypatch.delenv("MULEWATCH_REVIEW_API_KEY", raising=False)
    response = TestClient(app).get("/cases/1/evidence")
    assert response.status_code == 503


def test_evidence_rejects_missing_key(monkeypatch):
    monkeypatch.setenv("MULEWATCH_REVIEW_API_KEY", "test-review-key")
    response = TestClient(app).get("/cases/1/evidence")
    assert response.status_code == 401


def test_evidence_rejects_invalid_key(monkeypatch):
    monkeypatch.setenv("MULEWATCH_REVIEW_API_KEY", "test-review-key")
    response = TestClient(app).get(
        "/cases/1/evidence", headers={"X-Review-API-Key": "wrong-key"}
    )
    assert response.status_code == 401


def test_evidence_endpoint_returns_masked_data(monkeypatch):
    from unittest.mock import MagicMock

    from api import cases

    monkeypatch.setenv("MULEWATCH_REVIEW_API_KEY", "test-review-key")

    row = {
        "case_id": 42,
        "alert_id": 7,
        "status": "open",
        "report": {
            "findings": [{"claim": "Unusual activity", "evidence_ids": ["ev-1"]}],
            "typology_matches": [],
        },
        "tool_trace": {
            "evidence_id": "ev-1",
            "source": "transaction_analysis",
            "summary": "Sensitive customer information",
            "data": {
                "transaction_count": 12,
                "customer_name": "Private Customer",
                "account_number": "123456789012",
            },
        },
        "account_id": "123456789012",
        "risk_score": 0.85,
        "model_version": "test-model",
        "reasons": [],
    }

    cursor = MagicMock()
    cursor.fetchone.return_value = row

    connection = MagicMock()
    connection.__enter__.return_value.cursor.return_value.__enter__.return_value = (
        cursor
    )

    monkeypatch.setattr(
        cases.psycopg,
        "connect",
        lambda *args, **kwargs: connection,
    )

    response = TestClient(app).get(
        "/cases/42/evidence",
        headers={"X-Review-API-Key": "test-review-key"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["account_token"] == "****9012"
    assert payload["tool_trace"] == {}
    assert payload["evidence"][0]["evidence_id"] == "ev-1"

    serialized = response.text
    assert "Private Customer" not in serialized
    assert "123456789012" not in serialized
    assert payload["evidence"][0]["data"]["transaction_count"] == 12


def test_evidence_endpoint_warns_on_missing_citations(monkeypatch):
    from unittest.mock import MagicMock

    from api import cases

    monkeypatch.setenv("MULEWATCH_REVIEW_API_KEY", "test-review-key")

    row = {
        "case_id": 42,
        "alert_id": 7,
        "status": "open",
        "report": {
            "findings": [
                {"claim": "Unverified finding", "evidence_ids": ["missing-1"]}
            ],
            "typology_matches": [],
        },
        "tool_trace": {},
        "account_id": "123456789012",
        "risk_score": 0.85,
        "model_version": "test-model",
        "reasons": [],
    }

    cursor = MagicMock()
    cursor.fetchone.return_value = row

    connection = MagicMock()
    connection.__enter__.return_value.cursor.return_value.__enter__.return_value = (
        cursor
    )

    monkeypatch.setattr(
        cases.psycopg,
        "connect",
        lambda *args, **kwargs: connection,
    )

    response = TestClient(app).get(
        "/cases/42/evidence",
        headers={"X-Review-API-Key": "test-review-key"},
    )

    assert response.status_code == 200, response.text
    assert any(
        "cited evidence" in warning.lower() for warning in response.json()["warnings"]
    )


def test_evidence_endpoint_returns_404_for_missing_case(monkeypatch):
    from unittest.mock import MagicMock

    from api import cases

    monkeypatch.setenv("MULEWATCH_REVIEW_API_KEY", "test-review-key")

    cursor = MagicMock()
    cursor.fetchone.return_value = None

    connection = MagicMock()
    connection.__enter__.return_value.cursor.return_value.__enter__.return_value = (
        cursor
    )

    monkeypatch.setattr(
        cases.psycopg,
        "connect",
        lambda *args, **kwargs: connection,
    )

    response = TestClient(app).get(
        "/cases/999999/evidence",
        headers={"X-Review-API-Key": "test-review-key"},
    )

    assert response.status_code == 404


def test_evidence_endpoint_blocks_sensitive_report_and_reasons(monkeypatch):
    from unittest.mock import MagicMock

    from api import cases

    monkeypatch.setenv("MULEWATCH_REVIEW_API_KEY", "test-review-key")
    secret = "PRIVATE_TEST_CUSTOMER_98765"

    row = {
        "case_id": 42,
        "alert_id": 7,
        "status": "open",
        "report": {
            "summary": f"Customer {secret} requires review",
            "risk_rating": "HIGH",
            "recommended_action": "ENHANCED_MONITORING",
            "confidence": 0.9,
            "findings": [
                {
                    "claim": f"Investigation involving {secret}",
                    "evidence_ids": ["ev-1"],
                }
            ],
            "typology_matches": [],
            "open_questions": [secret],
        },
        "tool_trace": {
            "evidence_id": "ev-1",
            "source": secret,
            "data": {
                "transaction_count": 12,
                "customer_name": secret,
            },
        },
        "account_id": "123456789012",
        "risk_score": 0.85,
        "model_version": "test-model",
        "reasons": [
            {"feature": secret, "shap_value": 0.5},
        ],
    }

    cursor = MagicMock()
    cursor.fetchone.return_value = row

    connection = MagicMock()
    connection.__enter__.return_value.cursor.return_value.__enter__.return_value = (
        cursor
    )

    monkeypatch.setattr(
        cases.psycopg,
        "connect",
        lambda *args, **kwargs: connection,
    )

    response = TestClient(app).get(
        "/cases/42/evidence",
        headers={"X-Review-API-Key": "test-review-key"},
    )

    assert response.status_code == 200, response.text

    payload = response.json()
    assert secret not in response.text
    assert payload["account_token"] == "****9012"
    assert payload["tool_trace"] == {}
    assert payload["evidence"][0]["evidence_id"] == "ev-1"
    assert payload["evidence"][0]["data"]["transaction_count"] == 12
    assert payload["report"]["findings"][0]["evidence_ids"] == ["ev-1"]
    assert payload["model_reasons"] == []
