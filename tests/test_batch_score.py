from datetime import date
from unittest.mock import MagicMock

from pipeline import tasks

RUN_DATE = date(2026, 1, 1)


def test_chunking_1200_accounts():
    accounts = [f"A{i}" for i in range(1200)]
    chunks = list(tasks.chunk_account_ids(accounts, 500))

    assert [len(chunk) for chunk in chunks] == [500, 500, 200]
    assert [account for chunk in chunks for account in chunk] == accounts


def test_score_batch_metadata_and_model_version(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection

    monkeypatch.setattr(
        tasks.psycopg,
        "connect",
        MagicMock(return_value=connection),
    )
    monkeypatch.setattr(
        tasks,
        "get_feature_account_ids",
        lambda connection, feature_date: ["A1", "A2"],
    )

    response = MagicMock()
    response.json.return_value = {
        "scores": [
            {
                "account_id": account,
                "risk_score": 0.8,
                "model_version": "1",
                "reasons": [],
            }
            for account in ["A1", "A2"]
        ]
    }

    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = response

    monkeypatch.setattr(
        tasks.httpx,
        "Client",
        MagicMock(return_value=client),
    )

    upsert = MagicMock()
    monkeypatch.setattr(tasks, "upsert_scores", upsert)

    result = tasks.score_features_for_date(
        RUN_DATE,
        database_url="postgresql://unused",
        scoring_api_url="http://localhost:8000",
    )

    assert result["scored_count"] == 2
    assert result["model_version"] == "1"
    client.post.assert_called_once()
    upsert.assert_called_once()


def test_scoring_http_failure_does_not_persist(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection

    monkeypatch.setattr(
        tasks.psycopg,
        "connect",
        MagicMock(return_value=connection),
    )
    monkeypatch.setattr(
        tasks,
        "get_feature_account_ids",
        lambda connection, feature_date: ["A1"],
    )

    client = MagicMock()
    client.__enter__.return_value = client
    client.post.side_effect = tasks.httpx.ConnectError("Simulated scoring outage")

    monkeypatch.setattr(
        tasks.httpx,
        "Client",
        MagicMock(return_value=client),
    )

    upsert = MagicMock()
    monkeypatch.setattr(tasks, "upsert_scores", upsert)

    import pytest

    with pytest.raises(tasks.httpx.ConnectError):
        tasks.score_features_for_date(
            RUN_DATE,
            database_url="postgresql://unused",
            scoring_api_url="http://localhost:8000",
        )

    upsert.assert_not_called()
