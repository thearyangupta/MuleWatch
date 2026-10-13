# MuleWatch — AI System Card

## 1. System overview

MuleWatch is an AI-assisted investigation copilot for
potential money-mule activity.

It combines transaction features, machine-learning
risk scoring, retrieval-augmented generation, and a
LangGraph investigation workflow.

The system generates evidence-backed recommendations
for human reviewers.

It does not independently freeze accounts, report
individuals to authorities, or make final enforcement
decisions.

## 2. Intended users

- Financial crime analysts
- Fraud investigation teams
- Authorized human reviewers
- Developers evaluating AI governance controls

MuleWatch is a demonstration and research project
using synthetic data.

It is not approved for production banking use.

## 3. Data

Current development data includes:
- PaySim synthetic transaction records
- Faker-generated customer profiles
- Derived account behavior features
- Model scores and explanations
- Retrieved money-mule typology references

The project is not intended to process real customer
information in its current configuration.

## 4. Models and components

### Risk scoring
- XGBoost classifier
- MLflow model tracking
- SHAP-based explanations
- Model version recorded with alerts

### Investigation
- LangGraph state-machine workflow
- Configurable LLM via MULEWATCH_LLM_MODEL
- Structured Pydantic CaseReport
- Read-only investigation tools
- Retrieval from a typology knowledge base

### Model and prompt versioning
- Investigation prompt: prompts/investigate_v1.md
- LLM identifier: recorded in audit metadata
- Scoring model version: recorded with alert metadata

Runtime model identifiers and configuration must be
verified for each deployed version.

## 5. Human oversight

Verified cases pause at AWAITING_REVIEW.

Reviewers may:
- Approve the agent recommendation
- Override it with another permitted action
- Escalate to an investigator

The system stores the original agent action, final
human action, reviewer identifier, review timestamp,
and human-agent agreement.

Repeated final decisions are rejected.

## 6. Privacy controls

MuleWatch uses:
- Data minimization
- PII pseudonymization
- Masking before model calls
- Privacy-focused automated tests
- Read-only investigation data access

Audit records store minimal event metadata rather
than full model prompts or raw tool outputs.

Privacy controls reduce exposure but are not a
guarantee against every possible data leak.

## 7. Prompt-injection defenses

Controls include:
- Explicit untrusted-data fencing
- Suspicious instruction detection
- Limited permitted tools
- Typed tool arguments
- Structured output schemas
- Citation validation
- Output policy checks
- Human approval

Week 4 evaluation:
- Attack cases: 12
- Baseline changed decisions: 1/12
- Defended changed decisions: 0/12

These results describe the tested attack set only.
They do not establish general immunity to injection.

## 8. Output policy and resilience

MuleWatch checks for:
- Unsupported evidence
- Inconsistent risk/action recommendations
- Unsupported criminal guilt assertions
- Inappropriate enforcement instructions
- Protected-characteristic justifications

When automated analysis is insufficient or fails,
the system can return INSUFFICIENT_EVIDENCE or
NEEDS_MANUAL_REVIEW.

An LLM failure must not automatically close a case.

## 9. Auditability

The system records:
- Investigation and alert context
- Tool activity metadata
- LLM model and prompt identifiers
- Token usage
- Validation outcomes
- Case status transitions
- Human review decisions

Audit events are stored in PostgreSQL and linked
through SHA-256 hashes.

A verification script checks the complete global
hash chain.

The audit API provides case-specific event history.

## 10. Known limitations

- Synthetic data does not reproduce all real fraud
  patterns or operational conditions.
- A high risk score is not proof of criminal activity.
- Citation validation does not prove a claim is true.
- Model recommendations may be incorrect.
- Human reviewers can also make mistakes.
- Prompt-injection defenses have limited evaluation.
- The audit trail reconstructs investigation activity
  from saved state; original tool-call timestamps are
  not currently captured individually.
- Audit metadata records tool argument names rather
  than their full masked values.
- Audit events are written at case persistence time,
  not streamed throughout graph execution.
- Historical cases created before audit integration
  do not have complete historical audit events.
- A database superuser may bypass append-only
  protections.
- A hash chain without an independently protected
  anchor cannot prove that its final events were not
  removed or that the entire chain was not rewritten.
- API-key authentication is a development-level
  control, not a complete production identity system.
- Live end-to-end audit acceptance must be completed
  before claiming full audit coverage.

## 11. Prohibited uses

MuleWatch must not be used to:
- Automatically freeze or close bank accounts
- Make criminal guilt determinations
- Deny financial services without appropriate review
- Infer criminality from protected characteristics
- Replace trained investigators
- Process real customer data without appropriate
  authorization, privacy review and security controls

## 12. Evaluation and monitoring

Current evaluations include:
- Prompt-injection attack tests
- Policy and fallback tests
- Human review acceptance tests
- Audit-chain integrity tests

Future evaluation should measure:
- Evidence citation correctness
- Human override rates
- False positive and false negative behavior
- Model drift
- Prompt-injection robustness
- Audit coverage and completeness

## 13. Governance status

This is a development and educational system card.

The project has implemented important safeguards,
but it has not undergone an independent security
audit or production financial-services validation.
