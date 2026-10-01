from unittest.mock import MagicMock, patch

import numpy as np
from fastapi.testclient import TestClient

from scoring.api import app

client = TestClient(app)


def test_score_schema_validation():
    response = client.post(
        "/score",
        json={},
    )

    assert response.status_code == 422


@patch("scoring.api.psycopg.connect")
def test_unknown_account_returns_404(
    mock_connect,
):
    connection = MagicMock()
    cursor = MagicMock()

    mock_connect.return_value.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor

    cursor.fetchone.return_value = (None,)

    response = client.post(
        "/score",
        json={
            "account_id": "UNKNOWN_ACCOUNT",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Account not found"}


@patch("scoring.api.get_shap_reasons")
@patch("scoring.api.load_registered_model")
@patch("scoring.api.build_daily_feature_row")
@patch("scoring.api.get_latest_feature_date")
@patch("scoring.api.psycopg.connect")
def test_score_returns_reasons(
    mock_connect,
    mock_latest_date,
    mock_build_features,
    mock_load_model,
    mock_shap_reasons,
):
    mock_latest_date.return_value = "2026-01-31"

    feature_row = {
        "account_id": "ACC_A",
        "feature_date": "2026-01-31",
        "pass_through_ratio": 0.97,
        "median_dwell_minutes": 40.0,
        "fan_in": 9,
        "fan_out": 2,
        "transfer_cashout_chains": 1,
        "account_age_days": 21,
        "velocity_ratio": 3.5,
    }

    mock_build_features.return_value = feature_row

    model = MagicMock()
    model.predict_proba.return_value = np.array([[0.27, 0.73]])
    mock_load_model.return_value = model

    mock_shap_reasons.return_value = [
        {
            "feature": "pass_through_ratio",
            "value": 0.97,
            "shap_value": 1.42,
        },
        {
            "feature": "fan_in",
            "value": 9.0,
            "shap_value": 0.81,
        },
        {
            "feature": "median_dwell_minutes",
            "value": 40.0,
            "shap_value": 0.37,
        },
    ]

    response = client.post(
        "/score",
        json={
            "account_id": "ACC_A",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["risk_score"] == 0.73
    assert body["model_version"] == "1"

    assert len(body["reasons"]) == 3

    assert all(
        "feature" in reason and "value" in reason and "shap_value" in reason
        for reason in body["reasons"]
    )
