import os
from datetime import date

import mlflow
import mlflow.xgboost
import pandas as pd
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from pipeline.features import build_daily_feature_row
from scoring.train import FEATURE_COLUMNS, get_shap_reasons

DATABASE_URL = os.getenv(
    "MULEWATCH_DATABASE_URL",
    "postgresql://mulewatch_readonly:mulewatch_readonly_dev@localhost:5432/mulewatch",
)

MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    "sqlite:///mlflow.db",
)

MODEL_NAME = "mulewatch-mule-model"
MODEL_VERSION = "1"

app = FastAPI(
    title="MuleWatch Scoring API",
)


class ScoreRequest(BaseModel):
    account_id: str


class Reason(BaseModel):
    feature: str
    value: float
    shap_value: float


class ScoreResponse(BaseModel):
    risk_score: float
    model_version: str
    reasons: list[Reason]


def get_latest_feature_date(
    connection: psycopg.Connection,
    account_id: str,
) -> date | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT MAX(timestamp)::date
            FROM transactions
            WHERE sender_account_id = %s
               OR receiver_account_id = %s
            """,
            (
                account_id,
                account_id,
            ),
        )

        row = cursor.fetchone()

    if row is None:
        return None

    return row[0]


def load_registered_model():
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

    model_uri = f"models:/{MODEL_NAME}/{MODEL_VERSION}"

    return mlflow.xgboost.load_model(model_uri)


@app.post(
    "/score",
    response_model=ScoreResponse,
)
def score_account(
    request: ScoreRequest,
) -> ScoreResponse:
    with psycopg.connect(DATABASE_URL) as connection:
        feature_date = get_latest_feature_date(
            connection=connection,
            account_id=request.account_id,
        )

        if feature_date is None:
            raise HTTPException(
                status_code=404,
                detail="Account not found",
            )

        feature_row = build_daily_feature_row(
            connection=connection,
            account_id=request.account_id,
            feature_date=feature_date,
        )

    model = load_registered_model()

    features = pd.DataFrame(
        [{column: feature_row[column] for column in FEATURE_COLUMNS}],
        columns=FEATURE_COLUMNS,
    )

    risk_score = float(model.predict_proba(features)[0, 1])

    reasons = get_shap_reasons(
        model=model,
        feature_row=feature_row,
        top_n=3,
    )

    return ScoreResponse(
        risk_score=risk_score,
        model_version=MODEL_VERSION,
        reasons=reasons,
    )
