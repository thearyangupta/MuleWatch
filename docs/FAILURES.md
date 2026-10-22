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