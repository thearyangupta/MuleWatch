# MuleWatch — Design Document

## 1. User

The primary user of MuleWatch is a financial-crime analyst investigating accounts that have been flagged for potentially suspicious money-mule activity.

## 2. Input

MuleWatch receives an alert on an account that has been flagged for investigation.

The alert identifies the account that requires further investigation.

## 3. Output

MuleWatch produces a case summary containing:

- Evidence relevant to the investigation
- Citations to the supporting information
- A risk rating
- A recommended action

The final decision remains with the human analyst.

## 4. Success Metrics

MuleWatch will be evaluated using:

- Decision accuracy on labelled cases
- Analyst time saved
- Cost per case

## 5. System Boundaries

MuleWatch operates under the following boundaries:

- The agent recommends actions but never acts autonomously.
- The agent has read-only access to data.
- Every investigation step is logged for auditability.
- A human analyst approves every final decision.
- When evidence is insufficient or uncertain, the system returns "insufficient evidence" rather than guessing.