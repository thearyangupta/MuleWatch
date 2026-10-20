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
