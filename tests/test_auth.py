"""Focused JWT authentication tests."""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from scoring.api import app

SECRET = "mulewatch-day4-test-secret-at-least-32-characters"
HASHER = PasswordHash.recommended()


def configure(monkeypatch):
    monkeypatch.setenv("MULEWATCH_JWT_SECRET", SECRET)
    monkeypatch.setenv("MULEWATCH_ANALYST_USERNAME", "analyst")
    monkeypatch.setenv(
        "MULEWATCH_ANALYST_PASSWORD_HASH",
        HASHER.hash("analyst-test-password"),
    )
    monkeypatch.setenv("MULEWATCH_LEAD_USERNAME", "lead")
    monkeypatch.setenv(
        "MULEWATCH_LEAD_PASSWORD_HASH",
        HASHER.hash("lead-test-password"),
    )


def test_login_and_me(monkeypatch):
    configure(monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/auth/token",
        data={"username": "analyst", "password": "analyst-test-password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json() == {"username": "analyst", "role": "analyst"}


def test_invalid_password(monkeypatch):
    configure(monkeypatch)
    response = TestClient(app).post(
        "/auth/token",
        data={"username": "analyst", "password": "wrong"},
    )
    assert response.status_code == 401


def test_expired_token(monkeypatch):
    configure(monkeypatch)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "analyst",
            "role": "analyst",
            "iat": now - timedelta(hours=2),
            "nbf": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        SECRET,
        algorithm="HS256",
    )

    response = TestClient(app).get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_forged_token(monkeypatch):
    configure(monkeypatch)
    token = jwt.encode(
        {
            "sub": "lead",
            "role": "lead",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        },
        "wrong-signing-secret-at-least-32-characters",
        algorithm="HS256",
    )

    response = TestClient(app).get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_missing_configuration(monkeypatch):
    monkeypatch.delenv("MULEWATCH_JWT_SECRET", raising=False)

    response = TestClient(app).post(
        "/auth/token",
        data={"username": "analyst", "password": "anything"},
    )
    assert response.status_code == 503


def test_analyst_cannot_access_lead_dependency(monkeypatch):
    from fastapi import Depends, FastAPI

    from api.auth import require_lead

    configure(monkeypatch)

    test_app = FastAPI()

    @test_app.get("/lead-only")
    def lead_only(user=Depends(require_lead)):
        return {"username": user.username}

    client = TestClient(test_app)

    login = TestClient(app).post(
        "/auth/token",
        data={"username": "analyst", "password": "analyst-test-password"},
    )
    assert login.status_code == 200

    response = client.get(
        "/lead-only",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 403
