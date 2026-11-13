# MuleWatch — Investigation Failure Review

## Case 2 — Alert 177

**Evaluation category:** Known fraud
**Reported risk:** HIGH
**Recommended action:** ENHANCED_MONITORING
**Review status:** Provisional — underlying transaction evidence requires verification.

### Potential failure: Under-escalation

The report identifies a risk score above the alert threshold and describes a fraud-flagged transaction, yet recommends enhanced monitoring rather than escalation.

**Why it matters:** The recommended action may be too weak relative to the evidence presented.

### Potential failure: Typology overgeneralization

The agent matched money-mule guidance despite reporting no outgoing transactions during the examined window.

The evidence may support suspicious incoming activity, but it does not establish rapid pass-through.

### Follow-up for evaluation

- Verify the fraud-flagged transaction against the stored account-activity evidence.
- Determine whether the report accurately describes the observed transaction pattern.
- Review whether escalation would be more appropriate.
- Preserve this case as a candidate failure example for the guardrails.


---

# Guardrail and Governance Follow-up

## Previously observed investigation issues

### Under-escalation — MITIGATED, NOT PROVEN FIXED

The earlier Case 2 / Alert 177 investigation
recommended ENHANCED_MONITORING despite significant
risk indicators.

Human review now allows analysts to override the
recommendation or escalate the case.

The underlying recommendation quality still requires
evaluation. Human oversight mitigates the consequence;
it does not correct the model's reasoning.

### Typology overgeneralization — OPEN

A money-mule typology was associated with evidence
that did not clearly demonstrate rapid pass-through.

Citation and policy validation improve report quality,
but do not guarantee semantic correctness.

Required follow-up:
- Verify transaction evidence against the source data.
- Evaluate typology precision.
- Measure unsupported factual claims.

### Prompt injection — MITIGATED

A 12-case attack set was evaluated.

Baseline decision changes: 1/12.
Defended decision changes: 0/12.

The result is limited to the tested examples.

### Unsafe output — MITIGATED

Code-level policy checks reject selected unsupported,
contradictory, discriminatory, or inappropriate output.

### LLM failure — MITIGATED

Safe fallback states prevent an unavailable or failed
LLM from automatically producing a no-action closure.

### Missing human oversight — FIXED FOR TESTED FLOW

LangGraph interrupts pause verified cases for review.

Approve, override, and escalate paths were accepted
through the local API.

Duplicate decisions were rejected with HTTP 409.

### Missing tamper-evident audit — IMPLEMENTED;
LIVE ACCEPTANCE PENDING

A hash-chained audit writer, database safeguards,
verification script, and case audit endpoint have
been added.

Mark this fully accepted only after database and
end-to-end API tests pass.

---
---

## Manual Review of 10 Investigations

### Review scope

Reviewed completed alerts:
177, 253, 201, 302, 45, 48, 1013, 1014, 151, 503.

Source: PostgreSQL cases.report and cases.tool_trace.

### Confirmed findings

#### F1 - Tool-call evaluation metric is incorrect

All 10 reviewed investigations have three tool calls in
their stored traces:

- account_score_tool
- account_activity_tool
- typology_search_tool

However, the evaluation CSV records tool_calls=0.

Impact: recorded tool-use metrics do not represent actual
execution and require correction before reporting.

#### F2 - Unsupported transaction sequence

Alert 177, Case 7.

The report describes incoming funds followed by cash-outs.

The stored activity profile shows:

- Total incoming: 1,027,693.98
- Total outgoing: 0
- Pass-through ratio: 0.0

The observed evidence does not establish outgoing
cash-outs following the incoming transactions.

Impact: the typology explanation overstates the evidence.

#### F3 - Inconsistent transaction terminology

Alert 1014, Case 23.

The report uses inconsistent descriptions of the
transaction activity, including outgoing CASH_IN
transactions and outgoing transfers.

Impact: the transaction mechanism is not described
consistently.

#### F4 - Weak typology justification

Alert 302, Case 15.

The report identifies a high velocity ratio but does
not establish a complete money-mule movement pattern.

The activity evidence shows two outgoing PAYMENT
transactions totaling 10,754.72 and no incoming funds
within the observed window.

Impact: the typology explanation needs stronger
transaction-level support.

### Cases requiring further judgment

#### J1 - Action consistency

Alerts 151 and 302 have similar model risk scores
(approximately 0.9177), but different actions:

- Alert 151: ENHANCED_MONITORING
- Alert 302: ESCALATE_TO_INVESTIGATOR

This requires review of the action rationale.

#### J2 - Low-risk evaluation group escalation

Alert 1013, Case 25.

Evaluation group: LOW_RISK.
Reported risk: MEDIUM.
Recommended action: ESCALATE_TO_INVESTIGATOR.

This is not automatically an incorrect decision.
The report should be judged against the actual evidence.

#### J3 - Known-fraud group recommendations

Alerts 177, 253, and 503 recommend ENHANCED_MONITORING.

These recommendations warrant human review, but the
evaluation category alone does not prove under-escalation.

### Positive observations

- All 10 investigations completed.
- All 10 stored traces contain account scoring,
  account activity, and typology-search tool calls.
- Findings contain evidence references.
- Reports include questions for further investigation.

### Evaluation limitations

Tracked input and output token counts are nonzero.

The recorded estimated cost is $0.00, but this is
not verified provider spending.

Tool-call counts and cost calculations need
reconciliation before final performance reporting.

### Review conclusion

10 reports reviewed.

4 confirmed quality or measurement findings.

3 additional judgment items identified.

The review does not establish actual criminal activity.
