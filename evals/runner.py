import argparse
import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from agent import graph as graph_module
from agent.evidence import create_evidence
from evals.load_frozen_evidence import load_frozen_evidence
from evals.scorers import (
    abstention_correctness,
    action_accuracy,
    citation_validity,
    escalation_counts,
    evidence_recall,
    policy_pass,
    summarize,
)

ROOT = Path(__file__).resolve().parent


def prepare_cases():
    """Load frozen cases and match them with golden-set labels."""
    database, constructed = load_frozen_evidence()

    golden = json.loads((ROOT / "golden_set.yaml").read_text(encoding="utf-8-sig"))

    scenarios = {scenario["id"]: scenario for scenario in constructed["scenarios"]}

    cases = []

    for label in golden["cases"]:
        case_id = label["case_id"]

        if label["source"] == "database":
            evidence = database["cases"][case_id.removeprefix("ALERT-")]
        else:
            evidence = scenarios[case_id]

        cases.append(
            {
                "case_id": case_id,
                "category": label["category"],
                "source": label["source"],
                "label": label,
                "evidence": evidence,
            }
        )

    if len(cases) != 35:
        raise ValueError(f"Expected 35 frozen cases, found {len(cases)}")

    return cases


def _fixture_evidence(source, summary, data):
    """Create evidence using the existing project schema."""
    return create_evidence(
        source=source,
        summary=summary,
        data=data,
    )


def _frozen_functions(case):
    """Build case-specific adapters for external evidence sources."""
    fixture = case["evidence"]
    is_database_case = case["source"] == "database"

    if is_database_case:
        alert = fixture["alert"]
        transactions = fixture["transactions"]
        features = fixture.get("latest_feature_on_or_before_alert")
    else:
        alert = {
            "id": -1,
            "account_id": "SYNTHETIC_ACCOUNT",
            "alert_date": "2026-01-01",
            "risk_score": 0,
            "model_version": "synthetic",
            "threshold": 1,
            "reasons": [],
            "status": "NEW",
        }

        transactions = fixture.get("transactions", [])
        features = None

    typology_data = json.loads(
        (ROOT / "snapshot" / "typology_chunks.json").read_text(encoding="utf-8-sig")
    )
    fixed_chunks = typology_data["chunks"][:5]

    def load_alert(state, privacy=None):
        privacy = privacy or graph_module.CasePrivacy()
        safe_alert = privacy.mask(dict(alert))

        return {
            "alert": safe_alert,
            "status": "INVESTIGATING",
            "messages": [
                HumanMessage(
                    content=(
                        "Investigate frozen alert:\n"
                        + graph_module.fence_untrusted_data(safe_alert)
                    )
                )
            ],
        }

    def activity(account_id, days=30):
        data = {
            "ok": True,
            "account_id": account_id,
            "transactions": transactions,
            "frozen_snapshot": True,
            "coverage_note": ("Partial evidence fixture; not full account history"),
        }

        if not is_database_case:
            for field in (
                "untrusted_payment_reference",
                "untrusted_retrieved_text",
            ):
                if field in fixture:
                    data[field] = fixture[field]

        return _fixture_evidence(
            "get_account_activity",
            "Frozen account activity",
            data,
        )

    def score(account_id):
        return _fixture_evidence(
            "score_account",
            "Frozen feature snapshot",
            {
                "ok": True,
                "account_id": account_id,
                "features": features,
                "frozen_snapshot": True,
            },
        )

    def typology(query):
        data = {
            "ok": True,
            "chunks": fixed_chunks,
            "frozen_snapshot": True,
            "retrieval_mode": ("fixed_fixture_not_ranked_search"),
        }

        if fixture.get("untrusted_retrieved_text"):
            data["untrusted_retrieved_text"] = fixture["untrusted_retrieved_text"]

        return _fixture_evidence(
            "search_typologies",
            "Frozen typology chunks",
            data,
        )

    def save(state, privacy=None):
        """Replace the production database save operation."""
        status = state["status"]

        if status == "VERIFIED":
            status = "AWAITING_REVIEW" if state.get("human_review") else "COMPLETE"

        return {
            "status": status,
            "case_id": -1,
        }

    return load_alert, activity, score, typology, save


def _deny_db(*args, **kwargs):
    """Fail immediately if evaluation attempts PostgreSQL access."""
    raise RuntimeError("Evaluation forbids live PostgreSQL connections")


def _build_frozen_tools(activity, score, typology):
    """Create LangChain tools backed only by frozen adapters."""

    @tool("account_activity_tool")
    def frozen_activity_tool(
        account_id: str,
        days: int = 30,
    ) -> str:
        """Retrieve frozen account transaction activity."""
        evidence = activity(account_id, days)
        return evidence.model_dump_json()

    @tool("account_score_tool")
    def frozen_score_tool(account_id: str) -> str:
        """Retrieve frozen account risk features."""
        evidence = score(account_id)
        return evidence.model_dump_json()

    @tool("typology_search_tool")
    def frozen_typology_tool(query: str) -> str:
        """Retrieve frozen money-mule typology evidence."""
        evidence = typology(query)
        return evidence.model_dump_json()

    return {
        "account_activity_tool": frozen_activity_tool,
        "account_score_tool": frozen_score_tool,
        "typology_search_tool": frozen_typology_tool,
    }


def run_graph_case(case):
    """Run one real LangGraph case with frozen external I/O."""
    load, activity, score, typology, save = _frozen_functions(case)

    frozen_tools = _build_frozen_tools(
        activity,
        score,
        typology,
    )

    with ExitStack() as stack:
        replacements = [
            ("load_alert", load),
            ("get_account_activity", activity),
            ("score_account", score),
            ("search_typologies", typology),
            ("save", save),
        ]

        for name, replacement in replacements:
            stack.enter_context(
                patch.object(
                    graph_module,
                    name,
                    replacement,
                )
            )
        stack.enter_context(
            patch.object(
                graph_module,
                "TOOLS_BY_NAME",
                frozen_tools,
            )
        )
        stack.enter_context(
            patch.object(
                graph_module,
                "TOOLS",
                list(frozen_tools.values()),
            )
        )
        stack.enter_context(
            patch.object(
                graph_module.psycopg,
                "connect",
                _deny_db,
            )
        )
        app = graph_module.build_graph(
            checkpointer=MemorySaver(),
            human_review=True,
        )

        if case["source"] == "database":
            alert_id = int(case["case_id"].split("-")[1])
        else:
            alert_id = -1

        thread_id = "eval-" + case["case_id"]

        state = graph_module.initial_state(
            alert_id,
            thread_id=thread_id,
            human_review=True,
        )

        config = {
            "configurable": {
                "thread_id": thread_id,
            },
            "recursion_limit": 35,
        }
        app.invoke(state, config=config)

        snapshot = app.get_state(config)
        values = snapshot.values

        interrupted = bool(
            snapshot.tasks
            and any(getattr(task, "interrupts", ()) for task in snapshot.tasks)
        )

        trace = []

        for message in values.get("messages", []):
            if isinstance(message, AIMessage):
                for call in message.tool_calls:
                    trace.append(
                        {
                            "tool": call["name"],
                            "tool_call_id": call["id"],
                        }
                    )

            elif isinstance(message, ToolMessage):
                trace.append(
                    {
                        "tool_call_id": message.tool_call_id,
                        "result": message.content,
                    }
                )

        return {
            "status": values.get("status"),
            "report": values.get("report"),
            "evidence": values.get("evidence", []),
            "trace": trace,
            "steps": values.get("steps_taken", 0),
            "limit_hit": values.get("limit_hit", False),
            "hitl_interrupted": interrupted,
            "graph_executed": True,
        }


def evaluate_case(case, run_graph=False):
    """Evaluate one case without fabricating unavailable metrics."""
    label = case["label"]

    result = {
        "status": "NOT_RUN",
        "report": None,
        "evidence": [],
        "trace": [],
        "steps": 0,
        "limit_hit": False,
        "hitl_interrupted": False,
        "graph_executed": False,
    }

    if run_graph:
        try:
            result = run_graph_case(case)
        except Exception as exc:
            result["status"] = "GRAPH_ERROR"
            result["error"] = f"{type(exc).__name__}: {exc}"

    report = result.get("report")
    trace = result.get("trace", [])

    retrieved = [
        chunk.get("chunk_id")
        for evidence in result.get("evidence", [])
        if isinstance(evidence, dict)
        for chunk in evidence.get("data", {}).get("chunks", [])
        if isinstance(chunk, dict)
    ]

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "label_status": label.get("label_status"),
        "scored": label.get("scored", False),
        "status": result["status"],
        "graph_executed": result["graph_executed"],
        "hitl_interrupted": result["hitl_interrupted"],
        "action_accuracy": action_accuracy(
            report,
            label,
        ),
        "escalation_counts": escalation_counts(
            report,
            label,
        ),
        "evidence_recall": evidence_recall(
            trace,
            label,
        ),
        "citation_validity": citation_validity(
            report,
            result.get("evidence", []),
        ),
        "policy_pass": policy_pass(report),
        "abstention_correctness": (
            abstention_correctness(
                result["status"],
                label,
            )
        ),
        "injection_resistance": None,
        "hit_rate_at_5": None,
        "context_precision_at_5": None,
        "steps": result["steps"],
        "limit_hit": result["limit_hit"],
        "retrieved_chunk_ids": retrieved,
        "report": report,
        "trace": trace,
        "error": result.get("error"),
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--run-graph",
        action="store_true",
        help="Execute the actual LLM graph",
    )

    parser.add_argument(
        "--out",
        default="evals/results",
    )

    args = parser.parse_args()

    cases = prepare_cases()

    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)

    rows = []

    for case in cases:
        row = evaluate_case(
            case,
            run_graph=args.run_graph,
        )

        rows.append(row)

        destination = output / (case["case_id"] + ".json")

        destination.write_text(
            json.dumps(
                row,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        print(
            case["case_id"],
            row["status"],
        )

    summary = summarize(rows)

    summary["graph_execution"] = {
        "requested": args.run_graph,
        "executed": sum(bool(row["graph_executed"]) for row in rows),
        "errors": sum(row["status"] == "GRAPH_ERROR" for row in rows),
        "hitl_interrupts": sum(bool(row["hitl_interrupted"]) for row in rows),
    }

    summary["limitations"] = [
        "Unadjudicated labels excluded from action accuracy",
        "Fixed typology chunks do not support ranked retrieval metrics",
        "Injection resistance requires paired controlled runs",
        "Judge calibration requires independent human labels",
        "Synthetic cases are fixture-only",
    ]

    (output / "summary.json").write_text(
        json.dumps(
            summary,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            summary,
            indent=2,
        )
    )

    if args.run_graph and summary["graph_execution"]["errors"]:
        raise SystemExit(
            "Graph evaluation encountered errors; inspect per-case results."
        )


if __name__ == "__main__":
    main()
