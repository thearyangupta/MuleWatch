# MuleWatch Model Evaluation

## Account Labelling

MuleWatch derives account-level training labels from
fraud-labelled transactions in the synthetic dataset.

The training implementation obtains account identifiers
associated with transactions where is_fraud = TRUE.

An account receives mule_label = 1 when its account ID
belongs to that identified set. Otherwise it receives 0.

## Important Limitations

- Fraud involvement is a proxy for money-mule behaviour.
- Fraud labels do not prove that an account is a money mule.
- Synthetic data may not reflect real banking behaviour.
- Model predictions are risk indicators, not final decisions.
- Human review remains necessary.

## Training Method

- Account-level engineered features
- Time-based training/test split
- XGBoost classifier
- Average precision / PR-AUC evaluation
- MLflow experiment tracking and model registration

## Evaluation Evidence

Measured PR-AUC: 0.016914 (MLflow experiment: mulewatch-account-scoring).

Registered model: mulewatch-mule-model, version 1.

The scoring API currently references model version 1.
This configuration alone does not prove registration.

## Intended Use

Prioritise synthetic money-mule alerts for investigation.

The model must not autonomously make financial or
customer-impacting decisions.
