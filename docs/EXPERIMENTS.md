# Controlled Experiments

## Objective

Compare one changed variable at a time using the frozen
35-case MuleWatch evaluation set.

## Configurations

| Name | Prompt | Model | Step limit |
|---|---|---|---|
| baseline | v1 | current | 6 |
| prompt_v2 | v2 | current | 6 |
| step_limit_4 | v1 | current | 4 |
| strong_model | v1 | chosen stronger model | 6 |

The stronger model must be supplied explicitly.

## Method

- Reuse the frozen evaluation runner.
- Run each configuration at least twice.
- Compare means and observed ranges.
- Treat differences within repeated-run spread as noise.
- Keep production defaults unchanged.
- Keep Langfuse export disabled during experiments.

## Metrics

Available from the existing runner:
- Action accuracy on reviewed labels
- Escalation recall
- False escalation rate
- Citation validity
- Policy pass rate
- Step-limit hits
- Local p95 latency

Not yet measured:
- Actual USD cost per case
- Dedicated faithfulness score
- Paired injection-resistance score

Do not substitute citation validity for faithfulness.

## Results

Versioned JSON results are saved under evals/results
with UTC timestamp and Git SHA.

## Production decision

Status: PENDING EXPERIMENT RESULTS.

Do not promote a configuration until:
1. At least three single-variable experiments have run.
2. Each has at least two repeats.
3. Results have been compared for mean and spread.
4. Safety regressions and errors have been reviewed.
5. A written production choice has been recorded.

The production default remains prompt v1, current model,
and six-step budget until an explicit release decision.



## Development Smoke Test

Status: PASSED (development validation only)

Git SHA: 7bc445e9a47d
Cases: 5
Configurations: baseline, prompt_v2, step_limit_4
Repeats: 1
Total evaluations: 15
Completed: 15
Graph errors: 0
Result: evals/results/day4_smoke_7bc445e9a47d.json

All cases reached AWAITING_REVIEW.

Validated:
- Frozen evidence integrity
- Three configuration execution paths
- Per-case result persistence
- Successful smoke-test completion

Not yet validated:
- Resume after process interruption
- Final report/action accuracy
- Escalation recall and false escalation rate
- Faithfulness and injection resistance
- Cost per case
- Statistical mean and spread across repeated runs

Production decision:
Keep the existing production configuration unchanged.
Do not claim one experiment configuration is superior.

Deferred:
Full repeated benchmark and production configuration selection.

## Checkpointed Development Smoke Test

Status: DEVELOPMENT VALIDATION COMPLETE
Production experiment acceptance: DEFERRED

### Execution

- Git SHA: 7bc445e9a47d
- Frozen evidence integrity: PASS
- Cases per configuration: 5
- Configurations: baseline, prompt_v2, step_limit_4
- Repeats: 1
- Total completed evaluations: 15/15
- Graph errors: 0
- All evaluations reached AWAITING_REVIEW.
- Results: evals/results/day4_smoke_7bc445e9a47d.json

### Observed Metrics

| Metric | Baseline | Prompt V2 | Step limit 4 |
| --- | --- | --- | --- |
| Action accuracy | N/A | N/A | N/A |
| Citation validity | 100% | 100% | 100% |
| Policy pass | 100% | 100% | 100% |
| Mean latency | 15.0022s | 13.2958s | 12.8166s |
| Graph errors | 0 | 0 | 0 |

These are five-case, single-repeat development measurements.
They do not establish statistical significance or model superiority.

### Ground-Truth Limitation

The evaluated golden cases are marked:
- scored = false
- label_status = PENDING_HUMAN_REVIEW

The action_accuracy scorer correctly excludes unreviewed labels.
No accuracy or escalation claims may be made from these cases.

### Deferred Acceptance Requirements

- Independent human adjudication of golden labels
- At least three single-variable experiments with repeated runs
- Mean and spread for comparable measured metrics
- Action accuracy and escalation confusion metrics
- Faithfulness and paired injection-resistance assessment
- Cost per case and p95 latency
- Evidence-based production configuration decision

### Production Decision

Retain the existing production configuration unchanged.
The development smoke test does not justify promotion.

### Engineering Decision

Keep checkpointed evaluation execution for future experiments.
Do not repeat the expensive full-suite run until labels,
metrics, and acceptance criteria are ready.