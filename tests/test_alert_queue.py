from fastapi.testclient import TestClient

from scoring.api import app
from tests.jwt_helpers import analyst_headers


def _headers(monkeypatch):
    return analyst_headers(monkeypatch)


def test_queue_requires_auth(monkeypatch):
    _headers(monkeypatch)
    assert TestClient(app).get("/cases").status_code == 401


def test_queue_rejects_invalid_page(monkeypatch):
    headers = _headers(monkeypatch)
    assert TestClient(app).get("/cases?page=0", headers=headers).status_code == 422


def test_queue_rejects_invalid_risk(monkeypatch):
    headers = _headers(monkeypatch)
    assert (
        TestClient(app).get("/cases?risk=CRITICAL", headers=headers).status_code == 422
    )


def test_queue_rejects_reversed_dates(monkeypatch):
    headers = _headers(monkeypatch)
    response = TestClient(app).get(
        "/cases?date_from=2026-10-27&date_to=2026-10-01", headers=headers
    )
    assert response.status_code == 422


def test_status_requires_auth(monkeypatch):
    _headers(monkeypatch)
    assert TestClient(app).get("/cases/alerts/1/status").status_code == 401
