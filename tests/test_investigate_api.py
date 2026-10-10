from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from agent.evidence import create_evidence
from agent.report import CaseReport
from scoring.api import app


class FakeModel:
    def invoke(self, messages):
        return AIMessage(
            content="Ready for assessment.",
            usage_metadata={
                "input_tokens": 20,
                "output_tokens": 10,
                "total_tokens": 30,
            },
        )


class FakeReportModel:
    pass


fake_alert = {
    "id": 1,
    "account_id": "ACC_TEST",
    "alert_date": date(2026, 1, 10),
    "risk_score": 0.91,
    "model_version": "1",
    "threshold": 0.8,
    "reasons": [],
    "status": "NEW",
}

fake_evidence = create_evidence(
    source="search_typologies",
    summary="Money-mule typology guidance",
    data={
        "ok": True,
        "chunks": [
            {
                "chunk_id": "chunk-1",
                "content": "Rapid movement of funds",
            }
        ],
    },
)

fake_report = CaseReport.model_validate(
    {
        "summary": "Potential rapid pass-through activity.",
        "risk_rating": "MEDIUM",
        "recommended_action": "ENHANCED_MONITORING",
        "findings": [],
        "typology_matches": [
            {
                "typology": "Rapid movement",
                "explanation": "Matches retrieved guidance.",
                "evidence_id": fake_evidence.evidence_id,
                "chunk_ids": ["chunk-1"],
            }
        ],
        "open_questions": [],
        "confidence": 0.7,
    }
)


class FakeCursor:
    def __init__(self, write=False):
        self.write = write

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params):
        self.query = query

    def fetchone(self):
        if self.write:
            return (101,)
        return fake_alert.copy()


class FakeConnection:
    def __init__(self, write=False):
        self.write = write

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return FakeCursor(write=self.write)


def fake_connect(dsn, **kwargs):
    return FakeConnection(write="row_factory" not in kwargs)


def test_investigate_endpoint():
    with (
        patch(
            "agent.graph.psycopg.connect",
            side_effect=fake_connect,
        ),
        patch(
            "agent.graph.search_typologies",
            return_value=fake_evidence,
        ),
        patch(
            "agent.graph.generate_report",
            return_value=fake_report,
        ),
        patch(
            "api.investigate.build_graph",
            side_effect=lambda: __import__(
                "agent.graph",
                fromlist=["build_graph"],
            ).build_graph(
                model=FakeModel(),
                report_model=FakeReportModel(),
            ),
        ),
    ):
        response = TestClient(app).post("/investigate/1")

    assert response.status_code == 200

    body = response.json()

    assert body["case_id"] == 101
    assert body["status"] == "COMPLETE"
    assert body["report"]["risk_rating"] == "MEDIUM"
    assert body["report"]["recommended_action"] == "ENHANCED_MONITORING"


def test_invalid_alert_id():
    response = TestClient(app).post("/investigate/0")

    assert response.status_code == 422
