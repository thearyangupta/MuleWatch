import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from scoring.train import (
    FEATURE_COLUMNS,
    get_batch_shap_reasons,
    get_shap_reasons,
)


def test_batch_shap_matches_single_account_explanations():
    rng = np.random.default_rng(42)

    values = rng.uniform(
        low=0.1,
        high=10.0,
        size=(24, len(FEATURE_COLUMNS)),
    )

    features = pd.DataFrame(
        values,
        columns=FEATURE_COLUMNS,
    )

    labels = np.array([0, 1] * 12)

    model = XGBClassifier(
        n_estimators=8,
        max_depth=2,
        random_state=42,
        n_jobs=1,
    )
    model.fit(features, labels)

    rows = features.to_dict(orient="records")

    expected = [get_shap_reasons(model, row, top_n=3) for row in rows]

    actual = get_batch_shap_reasons(
        model,
        rows,
        top_n=3,
    )

    assert len(actual) == len(expected)

    for batch_reasons, single_reasons in zip(
        actual,
        expected,
        strict=True,
    ):
        assert [reason["feature"] for reason in batch_reasons] == [
            reason["feature"] for reason in single_reasons
        ]

        for batch_reason, single_reason in zip(
            batch_reasons,
            single_reasons,
            strict=True,
        ):
            assert batch_reason["value"] == single_reason["value"]
            assert np.isclose(
                batch_reason["shap_value"],
                single_reason["shap_value"],
                rtol=1e-6,
                atol=1e-7,
            )


def test_batch_shap_empty_input():
    assert get_batch_shap_reasons(None, []) == []
