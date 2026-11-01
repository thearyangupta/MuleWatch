"""Test-only JWT authentication helpers."""

from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from scoring.api import app

TEST_SECRET = "mulewatch-ci-test-secret-at-least-32-characters"
TEST_PASSWORD = "mulewatch-ci-test-password"


def analyst_headers(monkeypatch):
    """Return a valid analyst Bearer token using test-only credentials."""
    monkeypatch.setenv("MULEWATCH_JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("MULEWATCH_ANALYST_USERNAME", "analyst")
    monkeypatch.setenv(
        "MULEWATCH_ANALYST_PASSWORD_HASH",
        PasswordHash.recommended().hash(TEST_PASSWORD),
    )
    monkeypatch.setenv("MULEWATCH_LEAD_USERNAME", "lead")
    monkeypatch.setenv(
        "MULEWATCH_LEAD_PASSWORD_HASH",
        PasswordHash.recommended().hash(TEST_PASSWORD),
    )

    response = TestClient(app).post(
        "/auth/token",
        data={
            "username": "analyst",
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 200, response.text

    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
