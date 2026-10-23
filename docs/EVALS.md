# MuleWatch Evaluation Framework

## Purpose

MuleWatch uses a frozen evaluation dataset and deterministic
scorers to detect regressions in investigation quality.

The evaluation framework distinguishes measured results,
unmeasured results, and independently reviewed labels.

Missing measurements must never be treated as successful scores.

## Golden Set

The frozen golden set is maintained in:

- `evals/golden_set.yaml`
- `evals/snapshot/`
- `evals/human_labelling.csv`
- `evals/LABELLING_GUIDE.md`

The current set contains 35 cases spanning clean, borderline,
clear, cross-day, prompt-injection, and thin-evidence scenarios.

The action labels are preliminary and require independent
human adjudication before use as accuracy ground truth.

## Evaluation Metrics

| Metric | Purpose |
| --- | --- |
| Action accuracy | Agreement with reviewed acceptable actions |
| Escalation recall | Correct escalations / all expected escalations |
| False escalation rate | Incorrect escalations / expected non-escalations |
| Citation validity | Whether cited evidence is valid |
| Policy pass | Whether the output meets policy constraints |
| Injection resistance | Robustness under controlled prompt-injection tests |
| Cost per case | Measured model expenditure per investigation |

A metric with insufficient evidence is `NOT MEASURED`.

## Quality Gate

Implementation: `evals/gate.py`

Focused tests: `tests/test_eval_gate.py`

GitHub workflow: `.github/workflows/evals.yml`

The offline gate requires:

- Exact frozen-case coverage
- One selected production configuration
- Executed investigation graphs without errors
- Independently reviewed labels
- Complete required metric measurements
- Configured threshold compliance

The current thresholds are provisional policy values, not
validated baselines. They must be calibrated using independently
reviewed evaluation results before production acceptance.

## Experiment

Saved smoke result:

`evals/results/day4_smoke_7bc445e9a47d.json`

Three configurations were compared:

- Baseline
- Prompt V2
- Step limit 4

Five cases were evaluated per configuration, producing
15 investigation executions.

Observed:

- Zero graph errors
- Citation validity: 100% on measured cases
- Policy pass: 100% on measured cases
- Action accuracy: NOT MEASURED
- Escalation recall: NOT MEASURED

This is a smoke experiment, not a statistically reliable
production-quality benchmark.

See `docs/EXPERIMENTS.md` for experiment details.

## Judge Calibration

Independent human adjudication is required before using
golden labels to measure action accuracy.

Judge agreement and disagreement analysis remain pending.

No unreviewed preliminary label should be silently promoted
to accepted ground truth.

## CI Architecture

Existing `.github/workflows/ci.yml` remains responsible for
the broader repository checks.

The separate evaluation workflow currently runs offline
gate tests and verifies that incomplete smoke evidence is
rejected.

It does not yet execute a full paid LLM evaluation on PRs.

## Remaining Acceptance Work

1. Complete independent golden-label adjudication.
2. Implement paired injection-resistance evaluation.
3. Add reliable per-case model cost measurements.
4. Enforce a runtime spending cap before further paid calls.
5. Calibrate thresholds against reviewed baseline results.
6. Enable full snapshot evaluation for PRs and manual runs.
7. Publish current-versus-baseline scorecards by category.
8. Demonstrate a regression blocked by a pull request.
9. Configure required GitHub branch-protection checks.

Until these requirements are satisfied, full production
evaluation acceptance remains pending.

## Reproduction

Run focused offline tests:

`python -m pytest tests/test_eval_gate.py -q`

Check the saved smoke evaluation:

`python -m evals.gate evals/results/day4_smoke_7bc445e9a47d.json`

The smoke evaluation is expected to fail acceptance because
required evidence is unavailable.
