import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from agent.graph import build_graph, initial_state

OUTPUT_DIR = Path("evaluation/results")
CSV_PATH = OUTPUT_DIR / "alert_results.csv"
JSON_PATH = OUTPUT_DIR / "alert_results.json"

ALERT_GROUPS = {
    "KNOWN_FRAUD": [1, 177, 253, 272, 503],
    "HIGH_RISK": [151, 152, 201, 301, 302],
    "BORDERLINE": [45, 46, 47, 48, 49],
    "LOW_RISK": [1016, 1015, 1014, 1012, 1013],
}

FIELDS = [
    "alert_id",
    "group",
    "case_id",
    "status",
    "risk_rating",
    "recommended_action",
    "tool_calls",
    "tool_names",
    "steps_taken",
    "step_limit_hit",
    "typology_checked",
    "input_tokens_tracked",
    "output_tokens_tracked",
    "estimated_cost_usd_tracked",
    "latency_seconds",
    "error",
]


def load_existing_results():
    if not JSON_PATH.exists():
        return {}

    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    return {int(row["alert_id"]): row for row in payload.get("results", [])}


def save_results(results):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = sorted(results.values(), key=lambda row: row["alert_id"])

    with CSV_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Tokens and estimated cost are graph-tracked values, "
            "not necessarily complete provider billing."
        ),
        "results": rows,
    }

    JSON_PATH.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )


def get_tool_metrics(result):
    """Count recorded tool calls from persisted trace events."""
    trace = result.get("tool_trace") or {}
    events = trace.get("events", [])

    calls = [
        event.get("tool")
        for event in events
        if isinstance(event, dict) and event.get("tool")
    ]

    return len(calls), ";".join(calls)


def evaluate_alert(graph, alert_id, group):
    start = time.perf_counter()

    row = {
        "alert_id": alert_id,
        "group": group,
        "case_id": None,
        "status": "ERROR",
        "risk_rating": None,
        "recommended_action": None,
        "tool_calls": None,
        "tool_names": None,
        "steps_taken": None,
        "step_limit_hit": None,
        "typology_checked": None,
        "input_tokens_tracked": None,
        "output_tokens_tracked": None,
        "estimated_cost_usd_tracked": None,
        "latency_seconds": None,
        "error": None,
    }

    try:
        result = graph.invoke(initial_state(alert_id))
        report = result.get("report") or {}
        tool_count, tool_names = get_tool_metrics(result)

        row.update(
            case_id=result.get("case_id"),
            status=result.get("status"),
            risk_rating=report.get("risk_rating"),
            recommended_action=report.get("recommended_action"),
            tool_calls=tool_count,
            tool_names=tool_names,
            steps_taken=result.get("steps_taken"),
            step_limit_hit=result.get("limit_hit"),
            typology_checked=result.get("typology_checked"),
            input_tokens_tracked=result.get("input_tokens"),
            output_tokens_tracked=result.get("output_tokens"),
            estimated_cost_usd_tracked=result.get("estimated_cost_usd"),
        )

        if result.get("validation_error"):
            row["error"] = result["validation_error"]

    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"

    finally:
        row["latency_seconds"] = round(time.perf_counter() - start, 3)

    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-new",
        type=int,
        default=0,
        help="Maximum new live investigations; default 0 means dry run.",
    )
    args = parser.parse_args()

    if args.max_new < 0:
        parser.error("--max-new cannot be negative")

    existing = load_existing_results()

    completed_alerts = {1}

    for alert_id, row in existing.items():
        if row.get("case_id") is not None and row.get("status") == "COMPLETE":
            completed_alerts.add(alert_id)

    pending = [
        (group, alert_id)
        for group, alert_ids in ALERT_GROUPS.items()
        for alert_id in alert_ids
        if alert_id not in completed_alerts
    ]

    print("Completed alert IDs:", sorted(completed_alerts))
    print("Pending alert IDs:", [alert_id for _, alert_id in pending])
    print("Pending count:", len(pending))

    if args.max_new == 0:
        print("DRY RUN: No Gemini requests made.")
        return

    graph = build_graph()

    for group, alert_id in pending[: args.max_new]:
        print(f"\nInvestigating alert {alert_id} [{group}]")

        row = evaluate_alert(graph, alert_id, group)
        existing[alert_id] = row
        save_results(existing)

        print(
            f"Alert={alert_id} "
            f"Status={row['status']} "
            f"Case={row['case_id']} "
            f"Action={row['recommended_action']} "
            f"Latency={row['latency_seconds']}s"
        )

        if row["error"]:
            print("Error:", row["error"])
            print("Stopping batch after failure.")
            break

    print("\nSaved:", CSV_PATH)
    print("Saved:", JSON_PATH)


if __name__ == "__main__":
    main()
