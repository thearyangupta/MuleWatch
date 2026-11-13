# MuleWatch

**AI investigation copilot for money-mule alerts.**

![CI](https://github.com/thearyangupta/mulewatch/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.14-blue)
![Data](https://img.shields.io/badge/data-synthetic%20only-lightgrey)

MuleWatch detects suspicious account activity, prioritizes alerts, and generates evidence-backed investigation reports for human analysts.

> **Synthetic data only.** Built using PaySim transactions and Faker-generated customer profiles. No autonomous account enforcement.

## Features

- **Fraud detection:** XGBoost, SHAP explanations, MLflow tracking.
- **Data pipeline:** Apache Airflow, PostgreSQL, idempotent processing.
- **AI investigation:** LangGraph, read-only tools, pgvector RAG.
- **Privacy:** Data minimization and Presidio PII masking.
- **Security:** Prompt-injection detection and untrusted-data fencing.
- **Reliability:** Citation validation, output policies, safe fallbacks.
- **Human oversight:** LangGraph interrupts, PostgreSQL checkpointing, approve/override/escalate.
- **Auditability:** Hash-chained audit events, integrity verification, case audit API.

## Architecture

```mermaid
flowchart TD
    A[PaySim + Faker] --> B[(PostgreSQL)]
    B --> C[Airflow Pipeline]
    C --> D[XGBoost + SHAP]
    D --> E[Risk Alerts]
    E --> F[LangGraph Investigator]
    B --> G[Read-only Tools + RAG]
    G --> F
    F --> H[Privacy + Injection Defenses]
    H --> I[Structured CaseReport]
    I --> J[Citation + Policy Checks]
    J --> K{Valid?}
    K -->|Yes| L[Human Review]
    K -->|No| M[Safe Fallback]
    L --> N[Final Decision]
    F --> O[(Hash-Chained Audit Log)]
    J --> O
    N --> O
```

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.14 |
| Database | PostgreSQL 17 + pgvector |
| ML | XGBoost, scikit-learn, SHAP |
| Tracking | MLflow |
| Pipeline | Apache Airflow |
| AI Agent | LangGraph, LangChain |
| API | FastAPI |
| Privacy | Microsoft Presidio |
| Testing | pytest, Ruff, GitHub Actions |

## Investigation Workflow

1. Load a risk alert and pseudonymize sensitive data.
2. Collect evidence using read-only tools and typology retrieval.
3. Generate a structured `CaseReport`.
4. Validate evidence citations and output policies.
5. Pause for human review using LangGraph `interrupt()`.
6. Resume with `Command(resume=...)` and save the final decision.
7. Record investigation and review activity in the audit trail.

When evidence is insufficient or AI processing fails, MuleWatch uses safe fallback states instead of automatically closing the case.

## Human Review API

| Endpoint | Purpose |
|---|---|
| `POST /investigate/{alert_id}` | Start investigation |
| `GET /cases?status=AWAITING_REVIEW` | Pending reviews |
| `GET /cases/{id}` | Case details |
| `POST /cases/{id}/decision` | Approve, override, escalate |
| `GET /cases/{id}/audit` | Audit history |
| `POST /score` | Risk scoring |

Review and audit endpoints require `X-Review-API-Key`.

## Security and Governance

MuleWatch uses defense in depth:

- PII masking before LLM calls.
- Untrusted-data fencing and injection scanning.
- Restricted tools and structured output schemas.
- Evidence citation and policy validation.
- Human approval for consequential decisions.
- PostgreSQL audit records linked using SHA-256 hashes.

**Prompt-injection evaluation:** 12 attacks; baseline decision changes: 1/12; defended decision changes: 0/12.

Audit integrity verification:

```powershell
python -m scripts.verify_audit
```

Audit integration requires final end-to-end acceptance.

See [AI System Card](docs/AI_SYSTEM_CARD.md) and [Failure Review](docs/FAILURES.md).

## Getting Started

```powershell
git clone https://github.com/thearyangupta/MuleWatch.git
cd MuleWatch

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .

docker compose up -d postgres
```

Apply database schemas and migrations as documented in `db/`, then initialize the LangGraph checkpointer.

Start the API:

```powershell
$env:MULEWATCH_REVIEW_API_KEY = "your-local-test-key"
python -m uvicorn scoring.api:app --host 127.0.0.1 --port 8000
```

API documentation: http://127.0.0.1:8000/docs

Configure your LLM provider credentials in an untracked `.env` file.

## Testing

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest tests --ignore=tests/test_dag_integrity.py -q
python -m scripts.verify_audit
```

Airflow integration tests require their separate runtime.

## Project Structure

```text
MuleWatch/
├── agent/       # LangGraph, policies, audit
├── api/         # Investigation and review endpoints
├── scoring/     # XGBoost and FastAPI
├── pipeline/    # Data processing
├── airflow/     # Scheduled workflows
├── rag/         # Typology retrieval
├── db/          # Database schemas
├── evals/       # Agent evaluations
├── scripts/     # Setup and verification
├── tests/       # Automated tests
└── docs/        # Governance and documentation
```

## Limitations

- Synthetic data does not represent real banking conditions.
- Risk scores and evidence citations do not prove criminal activity.
- Prompt-injection defenses are not guaranteed to stop every attack.
- Human review is required for final decisions.
- Hash chaining is tamper-evident, not fully tamper-proof.
- Production deployment requires additional security and compliance validation.


## Current Evaluation Quality

MuleWatch maintains a frozen 35-case evaluation dataset.
The latest smoke experiment evaluated five cases
under each of three configurations.

| Quality indicator | Current observation |
| --- | --- |
| Frozen evaluation cases | 35 |
| Smoke investigation executions | 15 |
| Graph errors | 0 |
| Citation validity | 100% on measured smoke cases |
| Policy compliance | 100% on measured smoke cases |
| Action accuracy | Not measured; labels pending review |
| Escalation recall | Not measured |
| Injection resistance | Not measured |
| Model cost per case | Not measured |
| Offline gate tests | 7 passing locally |
| Full production acceptance | Pending |

These observations are not a production-quality guarantee.

The offline quality gate rejects incomplete evidence.
Full PR evaluation, runtime spending protection, baseline
calibration, and blocked-regression demonstration remain pending.

See [Evaluation Framework](docs/EVALS.md) and
[Experiment Results](docs/EXPERIMENTS.md).
## Analyst screen

React + TypeScript: queue, citation-linked case view, decision flow, audit and lead-only ops.

After configuring local JWT credentials, start the stack with `docker compose up --build -d`.
Open http://localhost:8080.

Frontend checks: `cd web; npm ci; npm run lint; npm run typecheck; npm run test; npm run test:e2e`.

The Playwright browser test uses HTTP fixtures, not a live database. Evaluation and cost
metrics remain marked unmeasured until actual results are available.

### CI quality gate

| Check | Current status |
| --- | --- |
| Fast repository CI | Configured |
| Offline evaluation gate | Implemented |
| Manual full-artifact gate | Configured |
| Independent human review | Pending |
| Full 35-case quality acceptance | Not measured |
| Live API spending limiter | Pending |
| Blocked GitHub PR demonstration | Pending |

The full evaluation gate checks an existing result artifact
without making model calls. See [Evaluation Framework](docs/EVALS.md).

---

## Agent Evaluation

### Evaluation coverage

- 20 of 20 selected alerts investigated.
- Four groups: known fraud, high risk, borderline, low risk.
- 19 completed investigations recorded in the CSV.
- Previously completed Alert 1 excluded from CSV averages.
- 10 investigation reports manually reviewed.
- Findings documented in `docs/FAILURES.md`.

### Performance metrics

| Metric | Result |
|---|---:|
| Recorded investigations | 19 |
| Average latency | 24.61 seconds |
| Average input tokens | 5803 |
| Average output tokens | 139 |
| Average steps | 3.0 |
| Recorded estimated cost | $0.00 (unverified) |
| Recorded tool calls | 0 (known instrumentation error) |

The zero-cost metric does not establish actual Gemini billing.
Stored traces show tool calls that the CSV does not count.
Both metrics require reconciliation.

### Complete example investigation report

Alert 201, Case 13.

The following report was exported from the saved case data.

```json
{
  "summary": "Account ACC_001, belonging to a theatre manager and opened in February 2021, generated an alert with a risk score of 0.918 due to a high velocity ratio and account activity features. Over a 30-day window, the account exhibited no incoming funds but processed 650,797.24 in outgoing cash-out transactions sent entirely to counterparty account ACC_002 across two large transactions.",
  "findings": [
    {
      "claim": "Account ACC_001 triggered a high risk score of 0.918 driven primarily by velocity ratio and account age features.",
      "evidence_ids": [
        "evidence-f5980dabcae34bb6ad6c4d0348963790"
      ]
    },
    {
      "claim": "Over a 30-day window, ACC_001 had no incoming funds and total outgoing transactions of 650,797.24 directed entirely to counterparty ACC_002 via CASH_OUT transactions.",
      "evidence_ids": [
        "evidence-dab6946e4bc542ddb07f16885eaa77f7"
      ]
    }
  ],
  "confidence": 0.9,
  "risk_rating": "HIGH",
  "open_questions": [
    "What is the source of the funds initially deposited into ACC_001 before being cashed out to ACC_002?",
    "What is the relationship between the owner of ACC_001 and the account holder of ACC_002?"
  ],
  "typology_matches": [
    {
      "typology": "Money Muling / Cashing Out",
      "chunk_ids": [
        "mulewatch_features:1:1",
        "fca_mule_activity_cashing_out_2026:5:1"
      ],
      "evidence_id": "evidence-2385c043241a4c9c840f20d901051e17",
      "explanation": "The account rapidly disbursed large sums of outgoing funds via cash-out transactions to a single counterparty with zero incoming funds recorded in the observation window, aligning with behaviors of moving and cashing out illicit proceeds."
    }
  ],
  "recommended_action": "ESCALATE_TO_INVESTIGATOR"
}
```

This is an AI-generated investigation assessment,
not a verified determination of criminal activity.

### Manual review

Ten reports were reviewed for evidence grounding,
transaction interpretation, typology reasoning,
and recommended actions.

Four quality or measurement findings and three
additional judgment items were documented.

See `docs/FAILURES.md` for details.

### Agent architecture

The existing README Architecture and Investigation
Workflow sections document the LangGraph agent,
read-only tools, RAG, validation, human review,
and audit trail.