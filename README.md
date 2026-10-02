# MuleWatch

MuleWatch is an AI investigation copilot for money-mule alerts.

Instead of only asking whether an individual transaction is risky, MuleWatch starts from a flagged account and builds the evidence needed for an analyst to investigate it. The system is designed to support a human analyst: it recommends and explains, but does not take autonomous action.

## Current v0

Week 1 establishes the data, feature, scoring, and alert foundations:

1. PaySim transactions and Faker-generated customer data are stored in PostgreSQL.
2. Account-level money-mule features are calculated from transaction behaviour.
3. An XGBoost account-level model produces a risk score.
4. MLflow tracks the registered model version.
5. `POST /score` returns the account risk score, model version, and top three SHAP reasons.
6. Accounts are ranked by risk score and converted into a daily alert queue using an operational alert budget.
7. Alerts are idempotent per account and date.

Current flow:

```text
PaySim + Faker
      |
      v
 PostgreSQL
      |
      v
Account Features
      |
      v
XGBoost + MLflow
      |
      +------> FastAPI POST /score
      |
      v
Daily Alert Queue
```

## Run

### Requirements

- Python 3.14+
- Docker with Docker Compose
- PaySim CSV at:

```text
data/raw/PS_20174392719_1491204439457_log.csv
```

### Install dependencies

Create and activate a virtual environment, then install the project dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1

pip install faker pandas "psycopg[binary]" scikit-learn xgboost mlflow fastapi uvicorn httpx
```

### Start PostgreSQL

```powershell
docker compose up -d postgres
```

Create the database schema and read-only database role:

```powershell
Get-Content db\schema.sql | docker compose exec -T postgres psql -U mulewatch -d mulewatch

Get-Content db\roles.sql | docker compose exec -T postgres psql -U mulewatch -d mulewatch
```

### Seed the development database

```powershell
python pipeline\seed.py
```

The development seed samples 200,000 PaySim transactions and generates synthetic customer profiles using Faker.

### Train and register the scoring model

```powershell
python scoring\train.py
```

Training creates the local MLflow tracking state and registered account-scoring model used by the API.

### Start PostgreSQL and the API

```powershell
docker compose up -d --build
```

Check both services:

```powershell
docker compose ps
```

The API is available at:

```text
http://127.0.0.1:8000
```

### Score an account

Example PowerShell request:

```powershell
$body = @{
    account_id = "C1436118706"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/score" `
    -ContentType "application/json" `
    -Body $body
```

The response contains:

- `risk_score`
- `model_version`
- top three SHAP `reasons`

## Daily alerts

The daily alert pipeline scores active accounts for a date, ranks them by model risk score, and selects up to the configured analyst alert budget.

The alert threshold is operational rather than a fixed probability such as `0.5`. It is determined by the score of the lowest-ranked account selected within that day's available alert capacity.

Each alert stores:

- account ID
- alert date
- risk score
- model version
- SHAP reasons
- status

New alerts begin with:

```text
NEW
```

A database uniqueness constraint on:

```text
(account_id, alert_date)
```

together with conflict-safe insertion makes repeated alert generation idempotent.

## Example alerts

On the seeded development sample for `2026-01-31`, 26 active accounts were scored.

The configured daily alert budget was 50, so all 26 accounts were selected.

### C1500556384

Risk score:

```text
0.6871
```

Largest SHAP contributions:

```text
account_age_days = 2738
SHAP = +0.7209

fan_in = 1
SHAP = +0.1188

velocity_ratio = 0
SHAP = -0.0524
```

### C362803701

Risk score:

```text
0.6871
```

Largest SHAP contributions:

```text
account_age_days = 2741
SHAP = +0.7209

fan_in = 1
SHAP = +0.1188

velocity_ratio = 0
SHAP = -0.0524
```

### C810812783

Risk score:

```text
0.6720
```

Largest SHAP contributions:

```text
account_age_days = 3346
SHAP = +0.6284

fan_in = 1
SHAP = +0.1171

velocity_ratio = 0
SHAP = -0.0272
```

These SHAP explanations describe how the current model arrived at its scores. They are not proof that an account is a money mule.

## Data and model disclaimer

MuleWatch currently uses PaySim transaction data together with Faker-generated synthetic customer information.

For the Week 1 model, an account receives a proxy mule label when it sent or received a PaySim transaction labelled as fraud.

This is a development approximation and is not real-world money-mule ground truth.

The current model and alert outputs are for learning and development. MuleWatch is designed to support analyst investigation and human approval rather than autonomously act on an account.