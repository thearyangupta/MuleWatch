import mlflow
import mlflow.xgboost
import pandas as pd
import psycopg
import xgboost as xgb
from psycopg.rows import dict_row
from sklearn.metrics import average_precision_score
from xgboost import XGBClassifier

FEATURE_COLUMNS = [
    "pass_through_ratio",
    "median_dwell_minutes",
    "fan_in",
    "fan_out",
    "transfer_cashout_chains",
    "account_age_days",
    "velocity_ratio",
]


def get_mule_account_ids(
    connection: psycopg.Connection,
) -> set[str]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT sender_account_id AS account_id
            FROM transactions
            WHERE is_fraud = TRUE

            UNION

            SELECT receiver_account_id AS account_id
            FROM transactions
            WHERE is_fraud = TRUE
            """
        )

        rows = cursor.fetchall()

    return {row["account_id"] for row in rows}


def add_mule_labels(
    feature_rows: list[dict],
    mule_account_ids: set[str],
) -> list[dict]:
    labelled_rows = []

    for row in feature_rows:
        labelled_row = row.copy()

        labelled_row["mule_label"] = int(row["account_id"] in mule_account_ids)

        labelled_rows.append(labelled_row)

    return labelled_rows


def time_based_split(
    labelled_rows: list[dict],
    train_fraction: float = 0.8,
) -> tuple[list[dict], list[dict]]:
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1")

    unique_dates = sorted({row["feature_date"] for row in labelled_rows})

    split_index = int(len(unique_dates) * train_fraction)

    train_dates = set(unique_dates[:split_index])

    train_rows = [row for row in labelled_rows if row["feature_date"] in train_dates]

    test_rows = [row for row in labelled_rows if row["feature_date"] not in train_dates]

    return train_rows, test_rows


def rows_to_xy(
    rows: list[dict],
) -> tuple[pd.DataFrame, pd.Series]:
    features = pd.DataFrame(
        [{column: row[column] for column in FEATURE_COLUMNS} for row in rows],
        columns=FEATURE_COLUMNS,
    )

    labels = pd.Series(
        [row["mule_label"] for row in rows],
        name="mule_label",
        dtype="int64",
    )

    return features, labels


def train_gradient_boosting(
    train_rows: list[dict],
) -> XGBClassifier:
    X_train, y_train = rows_to_xy(train_rows)

    negative_count = (y_train == 0).sum()
    positive_count = (y_train == 1).sum()

    if positive_count == 0:
        raise ValueError("Training data contains no positive mule labels")

    scale_pos_weight = negative_count / positive_count

    model = XGBClassifier(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.1,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        n_jobs=-1,
        eval_metric="logloss",
    )

    model.fit(X_train, y_train)

    return model


def evaluate_pr_auc(
    model: XGBClassifier,
    test_rows: list[dict],
) -> float:
    X_test, y_test = rows_to_xy(test_rows)

    probabilities = model.predict_proba(X_test)[:, 1]

    return float(
        average_precision_score(
            y_test,
            probabilities,
        )
    )


def register_model(
    model: XGBClassifier,
    pr_auc: float,
    model_name: str = "mulewatch-mule-model",
) -> str:
    mlflow.set_experiment("mulewatch-account-scoring")

    with mlflow.start_run():
        mlflow.log_params(
            {
                "model_type": "XGBoost",
                "n_estimators": 200,
                "max_depth": 3,
                "learning_rate": 0.1,
                "features": ",".join(FEATURE_COLUMNS),
            }
        )

        mlflow.log_metric(
            "pr_auc",
            pr_auc,
        )

        model_info = mlflow.xgboost.log_model(
            xgb_model=model,
            name="model",
            registered_model_name=model_name,
        )

    return str(model_info.registered_model_version)


def get_shap_reasons(
    model: XGBClassifier,
    feature_row: dict,
    top_n: int = 3,
) -> list[dict]:
    features = pd.DataFrame(
        [{column: feature_row[column] for column in FEATURE_COLUMNS}],
        columns=FEATURE_COLUMNS,
    )

    matrix = xgb.DMatrix(
        features,
        feature_names=FEATURE_COLUMNS,
    )

    contributions = model.get_booster().predict(
        matrix,
        pred_contribs=True,
    )[0]

    feature_contributions = contributions[:-1]

    reasons = [
        {
            "feature": feature,
            "value": float(feature_row[feature]),
            "shap_value": float(shap_value),
        }
        for feature, shap_value in zip(
            FEATURE_COLUMNS,
            feature_contributions,
            strict=True,
        )
    ]

    reasons.sort(
        key=lambda reason: abs(reason["shap_value"]),
        reverse=True,
    )

    return reasons[:top_n]
