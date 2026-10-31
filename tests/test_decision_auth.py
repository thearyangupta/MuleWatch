"""Authorization tests for the real case decision route."""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from scoring.api import app

SECRET = "mulewatch-day4-decision-test-secret-at-least-32-characters"


def token(username="analyst", role="analyst", secret=SECRET):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": username,
            "role": role,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=30),
        },
        secret,
        algorithm="HS256",
    )


def configure(monkeypatch):
    from pwdlib import PasswordHash

    hasher = PasswordHash.recommended()
    monkeypatch.setenv("MULEWATCH_JWT_SECRET", SECRET)
    monkeypatch.setenv("MULEWATCH_ANALYST_USERNAME", "analyst")
    monkeypatch.setenv(
        "MULEWATCH_ANALYST_PASSWORD_HASH",
        hasher.hash("analyst-test-password"),
    )
    monkeypatch.setenv("MULEWATCH_LEAD_USERNAME", "lead")
    monkeypatch.setenv(
        "MULEWATCH_LEAD_PASSWORD_HASH",
        hasher.hash("lead-test-password"),
    )
    monkeypatch.setenv("MULEWATCH_REVIEW_API_KEY", "legacy-test-key")


def decision():
    return {
        "decision": "approve",
        "comment": "Reviewed the supporting evidence.",
    }


def test_api_key_alone_cannot_decide(monkeypatch):
    configure(monkeypatch)

    response = TestClient(app).post(
        "/cases/1/decision",
        headers={"X-Review-API-Key": "legacy-test-key"},
        json=decision(),
    )

    assert response.status_code == 401


def test_reviewer_impersonation_rejected(monkeypatch):
    configure(monkeypatch)

    response = TestClient(app).post(
        "/cases/1/decision",
        headers={"Authorization": f"Bearer {token()}"},
        json={**decision(), "reviewer_id": "lead"},
    )

    assert response.status_code == 422


def test_forged_decision_token_rejected(monkeypatch):
    configure(monkeypatch)

    response = TestClient(app).post(
        "/cases/1/decision",
        headers={
            "Authorization": (
                f"Bearer {token(secret='forged-signing-secret-32-characters')}"
            )
        },
        json=decision(),
    )

    assert response.status_code == 401


def test_invalid_decision_comment_rejected(monkeypatch):
    configure(monkeypatch)

    payload = decision()
    payload["comment"] = ""

    response = TestClient(app).post(
        "/cases/1/decision",
        headers={"Authorization": f"Bearer {token()}"},
        json=payload,
    )

    assert response.status_code == 422


def test_authenticated_decision_uses_jwt_reviewer(monkeypatch):
    """The reviewer passed to LangGraph must come from the JWT."""
    from contextlib import nullcontext
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import api.cases as cases

    configure(monkeypatch)

    case_id = 42
    thread_id = "test-review-jwt-42"

    fake_case = {
        "id": case_id,
        "status": "AWAITING_REVIEW",
        "thread_id": thread_id,
        "report": {
            "summary": "Synthetic investigation requires review.",
            "risk_rating": "HIGH",
            "recommended_action": "ESCALATE_TO_INVESTIGATOR",
            "findings": [
                {
                    "claim": "Synthetic transaction pattern requires review.",
                    "evidence_ids": ["TEST-E1"],
                }
            ],
            "typology_matches": [],
            "open_questions": [],
            "confidence": 0.9,
        },
    }

    connection = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = (True,)
    connection.cursor.return_value.__enter__.return_value = cursor

    monkeypatch.setattr(
        cases.psycopg,
        "connect",
        lambda *args, **kwargs: connection,
    )

    monkeypatch.setattr(
        cases,
        "get_case_row",
        lambda requested_id: fake_case,
    )

    graph = MagicMock()
    graph.get_state.return_value = SimpleNamespace(next=("review",))
    graph.invoke.return_value = {"status": "CLOSED"}

    monkeypatch.setattr(
        cases,
        "review_graph",
        lambda: nullcontext(graph),
    )

    monkeypatch.setattr(
        cases,
        "investigation_trace",
        lambda **kwargs: nullcontext(None),
    )

    monkeypatch.setattr(
        cases,
        "thread_config",
        lambda value: {"configurable": {"thread_id": value}},
    )

    monkeypatch.setattr(
        cases,
        "traced_config",
        lambda config, handler: config,
    )

    response = TestClient(app).post(
        f"/cases/{case_id}/decision",
        headers={"Authorization": f"Bearer {token()}"},
        json=decision(),
    )

    assert response.status_code == 200, response.text

    graph.invoke.assert_called_once()

    command = graph.invoke.call_args.args[0]

    assert command.resume["reviewer_id"] == "analyst"
    assert command.resume["decision"] == "approve"
    assert command.resume["comment"] == decision()["comment"]
    assert command.resume["final_action"] is None

    assert response.json()["id"] == case_id
