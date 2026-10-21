"""Controlled MuleWatch experiment runner with checkpoint/resume support."""

import argparse
import json
import subprocess
import time
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from agent import graph as graph_module
from evals import runner

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evals" / "results"
PROMPTS = ROOT / "prompts"


def git_sha():
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()


def configs():
    return [
        {
            "name": "baseline",
            "prompt": PROMPTS / "investigate_v1.md",
            "step_limit": 6,
        },
        {
            "name": "prompt_v2",
            "prompt": PROMPTS / "investigate_v2.md",
            "step_limit": 6,
        },
        {
            "name": "step_limit_4",
            "prompt": PROMPTS / "investigate_v1.md",
            "step_limit": 4,
        },
    ]


def save_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def run_case(case, config):
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

        start = time.perf_counter()
        result = runner.evaluate_case(case, run_graph=True)
        elapsed = time.perf_counter() - start

    # Deliberately exclude raw reports, evidence, and tool traces.
    return {
        "case_id": result["case_id"],
        "category": result["category"],
        "status": result["status"],
        "graph_executed": result["graph_executed"],
        "hitl_interrupted": result["hitl_interrupted"],
        "action_accuracy": result["action_accuracy"],
        "citation_validity": result["citation_validity"],
        "policy_pass": result["policy_pass"],
        "abstention_correctness": result["abstention_correctness"],
        "steps": result["steps"],
        "limit_hit": result["limit_hit"],
        "latency_seconds": round(elapsed, 3),
        "error": result.get("error"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cases", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--only",
        nargs="*",
        choices=("baseline", "prompt_v2", "step_limit_4"),
    )
    parser.add_argument(
        "--run-id",
        default="day4_smoke",
        help="Stable identifier used to resume a run",
    )
    args = parser.parse_args()

    if not 1 <= args.max_cases <= 35:
        parser.error("--max-cases must be between 1 and 35")

    if args.repeats < 1:
        parser.error("--repeats must be at least 1")

    if not args.run_id.replace("_", "").isalnum():
        parser.error("--run-id must contain letters, numbers, underscores")

    # This run is a smoke test, not final benchmark acceptance.
    cases = runner.prepare_cases()[: args.max_cases]
    selected = configs()

    if args.only:
        selected = [config for config in selected if config["name"] in args.only]

    for config in selected:
        if not config["prompt"].is_file():
            raise FileNotFoundError(config["prompt"])

    sha = git_sha()
    path = RESULTS / f"{args.run_id}_{sha[:12]}.json"

    signature = {
        "git_sha": sha,
        "model": graph_module.MODEL_NAME,
        "case_ids": [case["case_id"] for case in cases],
        "repeats": args.repeats,
        "configurations": [
            {
                "name": config["name"],
                "prompt": config["prompt"].name,
                "step_limit": config["step_limit"],
            }
            for config in selected
        ],
    }

    if path.exists():
        document = json.loads(path.read_text(encoding="utf-8"))
        if document["signature"] != signature:
            raise RuntimeError(
                "Existing checkpoint has different settings. Use a different --run-id."
            )
        print("RESUMING:", path, flush=True)
    else:
        document = {
            "signature": signature,
            "type": "development_smoke_test",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "results": {},
        }
        save_atomic(path, document)

    total = len(cases) * len(selected) * args.repeats

    print(f"TOTAL: {total} case evaluations", flush=True)

    for config in selected:
        for repeat in range(1, args.repeats + 1):
            for case in cases:
                key = f"{config['name']}|{repeat}|{case['case_id']}"

                if key in document["results"]:
                    print("SKIP completed:", key, flush=True)
                    continue

                print("RUN:", key, flush=True)

                row = run_case(case, config)

                document["results"][key] = row
                document["updated_at"] = datetime.now(timezone.utc).isoformat()

                # Checkpoint immediately after each completed case.
                save_atomic(path, document)

                print(
                    "DONE:",
                    key,
                    row["status"],
                    flush=True,
                )

                if row["status"] == "GRAPH_ERROR":
                    print(
                        "GRAPH ERROR:",
                        row["error"],
                        flush=True,
                    )

    statuses = Counter(result["status"] for result in document["results"].values())

    print("\nRESULTS:", path)
    print("Completed:", len(document["results"]), "/", total)
    print("Statuses:", dict(statuses))
    print("Smoke test finished; no production config selected.")


if __name__ == "__main__":
    main()
