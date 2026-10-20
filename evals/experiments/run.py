import argparse
import json
import math
import os
import statistics
import subprocess
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from agent import graph as graph_module
from evals import runner
from evals.scorers import summarize

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evals" / "results"
PROMPT_V1 = ROOT / "prompts" / "investigate_v1.md"
PROMPT_V2 = ROOT / "prompts" / "investigate_v2.md"


def git_sha():
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()


def configurations(strong_model):
    baseline_model = graph_module.MODEL_NAME

    configs = [
        {
            "name": "baseline",
            "prompt": PROMPT_V1,
            "model": baseline_model,
            "step_limit": 6,
            "changed_variable": "none",
        },
        {
            "name": "prompt_v2",
            "prompt": PROMPT_V2,
            "model": baseline_model,
            "step_limit": 6,
            "changed_variable": "prompt",
        },
        {
            "name": "step_limit_4",
            "prompt": PROMPT_V1,
            "model": baseline_model,
            "step_limit": 4,
            "changed_variable": "step_limit",
        },
    ]

    if strong_model:
        if strong_model == baseline_model:
            raise ValueError("Strong model must differ from the baseline model")
        configs.append(
            {
                "name": "strong_model",
                "prompt": PROMPT_V1,
                "model": strong_model,
                "step_limit": 6,
                "changed_variable": "model",
            }
        )

    return configs


def percentile(values, fraction):
    if not values:
        return None

    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)

    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def aggregate_runs(runs):
    metric_names = (
        "action_accuracy",
        "escalation_recall",
        "false_escalation_rate",
        "citation_validity",
        "policy_pass",
        "abstention_correctness",
        "step_limit_hits",
        "mean_steps",
        "p95_latency_seconds",
    )

    result = {}

    for metric in metric_names:
        values = [
            run["metrics"][metric]
            for run in runs
            if run["metrics"].get(metric) is not None
        ]

        result[metric] = {
            "mean": statistics.mean(values) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "spread": (max(values) - min(values) if len(values) >= 2 else None),
            "samples": len(values),
        }

    return result


def run_once(config, cases):
    rows = []
    durations = []

    with ExitStack() as stack:
        stack.enter_context(
            patch.object(
                graph_module,
                "MAX_STEPS",
                config["step_limit"],
            )
        )
        stack.enter_context(
            patch.object(
                graph_module,
                "MODEL_NAME",
                config["model"],
            )
        )
        stack.enter_context(
            patch.object(
                runner,
                "MODEL_NAME",
                config["model"],
            )
        )
        stack.enter_context(
            patch.object(
                graph_module,
                "PROMPT_PATH",
                config["prompt"],
            )
        )
        stack.enter_context(
            patch.object(
                runner,
                "PROMPT_PATH",
                config["prompt"],
            )
        )

        for case in cases:
            start = time.perf_counter()
            row = runner.evaluate_case(
                case,
                run_graph=True,
            )

            elapsed = time.perf_counter() - start
            durations.append(elapsed)
            rows.append(
                {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "status": row["status"],
                    "graph_executed": row["graph_executed"],
                    "action_accuracy": row["action_accuracy"],
                    "escalation_counts": row["escalation_counts"],
                    "evidence_recall": row["evidence_recall"],
                    "citation_validity": row["citation_validity"],
                    "policy_pass": row["policy_pass"],
                    "abstention_correctness": (row["abstention_correctness"]),
                    "injection_resistance": None,
                    "hit_rate_at_5": None,
                    "context_precision_at_5": None,
                    "steps": row["steps"],
                    "limit_hit": row["limit_hit"],
                    "latency_seconds": round(elapsed, 3),
                }
            )

            print(
                config["name"],
                case["case_id"],
                row["status"],
                flush=True,
            )

    scored = summarize(rows)["overall"]

    metrics = {
        "action_accuracy": scored["action_accuracy"],
        "escalation_recall": scored["escalation_recall"],
        "false_escalation_rate": (scored["false_escalation_rate"]),
        "citation_validity": scored["citation_validity"],
        "policy_pass": scored["policy_pass"],
        "abstention_correctness": (scored["abstention_correctness"]),
        "step_limit_hits": scored["step_limit_hits"],
        "mean_steps": scored["mean_steps"],
        "p95_latency_seconds": percentile(durations, 0.95),
        "faithfulness": None,
        "injection_resistance": None,
        "cost_per_case_usd": None,
    }

    return {
        "metrics": metrics,
        "case_count": len(rows),
        "graph_errors": sum(row["status"] == "GRAPH_ERROR" for row in rows),
        "case_results": rows,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--strong-model",
        default=None,
        help="Actual configured provider:model for stronger model",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--only",
        choices=(
            "baseline",
            "prompt_v2",
            "step_limit_4",
            "strong_model",
        ),
        nargs="*",
    )

    args = parser.parse_args()

    if args.repeats < 2:
        parser.error("Workbook requires at least two repeats")

    configs = configurations(args.strong_model)

    if args.only:
        configs = [config for config in configs if config["name"] in args.only]

        if len(configs) != len(set(args.only)):
            parser.error(
                "Requested experiment unavailable; strong_model needs --strong-model"
            )

    cases = runner.prepare_cases()
    sha = git_sha()
    os.environ["MULEWATCH_TRACING_ENABLED"] = "0"

    experiment = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": sha,
        "frozen_cases": len(cases),
        "repeats": args.repeats,
        "configurations": [],
        "limitations": [
            "Model cost unavailable without validated pricing",
            "Faithfulness requires a dedicated groundedness scorer",
            "Injection resistance requires paired attack runs",
            "Latency is local end-to-end evaluation time",
            "Unreviewed labels are excluded by existing scorers",
            "Results do not constitute production acceptance",
        ],
    }

    for config in configs:
        runs = []

        for repeat in range(args.repeats):
            print(
                f"START {config['name']} repeat {repeat + 1}/{args.repeats}",
                flush=True,
            )

            runs.append(run_once(config, cases))

        experiment["configurations"].append(
            {
                "name": config["name"],
                "changed_variable": config["changed_variable"],
                "prompt_version": config["prompt"].name,
                "model": config["model"],
                "step_limit": config["step_limit"],
                "runs": runs,
                "summary": aggregate_runs(runs),
            }
        )

    RESULTS.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    destination = RESULTS / (f"{timestamp}_{sha[:12]}.json")

    destination.write_text(
        json.dumps(experiment, indent=2),
        encoding="utf-8",
    )

    print(f"RESULTS: {destination}")

    print("\nCONFIGURATION | ACTION ACCURACY | P95 LATENCY")

    for config in experiment["configurations"]:
        metrics = config["summary"]
        print(
            config["name"],
            metrics["action_accuracy"]["mean"],
            metrics["p95_latency_seconds"]["mean"],
        )

    errors = sum(
        run["graph_errors"]
        for config in experiment["configurations"]
        for run in config["runs"]
    )

    if errors:
        raise SystemExit(f"{errors} graph errors; do not choose production config")


if __name__ == "__main__":
    main()
