import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import psycopg
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from psycopg.rows import dict_row

from agent.audit import append_audit_event
from agent.fallback import insufficient_evidence, manual_review
from agent.injection import fence_untrusted_data, scan_evidence
from agent.pii import CasePrivacy, PrivacyError
from agent.policy import validate_policy
from agent.report import CaseReport, generate_report
from agent.state import InvestigationState
from agent.state_machine import (
    ReviewDecision,
    outcome_status,
    validate_transition,
)
from agent.tools import (
    get_account_activity,
    score_account,
    search_typologies,
)
from agent.verify import verify_report

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

MAX_STEPS = 6

DATABASE_URL = os.getenv(
    "MULEWATCH_DATABASE_URL",
    "postgresql://mulewatch_readonly:mulewatch_readonly_dev@localhost:5432/mulewatch",
)

CASE_DATABASE_URL = os.getenv(
    "MULEWATCH_CASE_DATABASE_URL",
    "postgresql://mulewatch:mulewatch_dev@localhost:5432/mulewatch",
)

MODEL_NAME = os.getenv(
    "MULEWATCH_LLM_MODEL",
    "google_genai:gemini-2.5-flash-lite",
)

INPUT_PRICE_PER_MILLION = float(os.getenv("MULEWATCH_INPUT_PRICE_PER_MILLION", "0"))

OUTPUT_PRICE_PER_MILLION = float(os.getenv("MULEWATCH_OUTPUT_PRICE_PER_MILLION", "0"))

PROMPT_PATH = PROJECT_ROOT / "prompts" / "investigate_v1.md"


@tool
def account_activity_tool(
    account_id: str,
    days: int = 30,
) -> str:
    """Inspect an account's recent activity using its account alias."""
    return get_account_activity(account_id, days).model_dump_json()


@tool
def account_score_tool(account_id: str) -> str:
    """Retrieve an account's risk score using its account alias."""
    return score_account(account_id).model_dump_json()


@tool
def typology_search_tool(query: str) -> str:
    """Search documented money-mule typologies."""
    return search_typologies(query).model_dump_json()


TOOLS = [
    account_activity_tool,
    account_score_tool,
    typology_search_tool,
]

TOOLS_BY_NAME = {item.name: item for item in TOOLS}


def create_model():
    return init_chat_model(
        MODEL_NAME,
        temperature=0,
    ).bind_tools(TOOLS)


def create_report_model():
    return init_chat_model(
        MODEL_NAME,
        temperature=0,
    )


def load_alert(
    state: InvestigationState,
    privacy: CasePrivacy | None = None,
) -> dict:
    """Load the alert, then mask it before entering graph state."""
    if privacy is None:
        privacy = CasePrivacy()

    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    account_id,
                    alert_date,
                    risk_score,
                    model_version,
                    threshold,
                    reasons,
                    status
                FROM alerts
                WHERE id = %s
                """,
                (state["alert_id"],),
            )

            alert = cursor.fetchone()

    if alert is None:
        raise ValueError(f"Alert {state['alert_id']} not found")

    alert["alert_date"] = alert["alert_date"].isoformat()

    safe_alert = privacy.mask(alert)

    return {
        "alert": safe_alert,
        "status": "INVESTIGATING",
        "messages": [
            HumanMessage(
                content=(
                    "Investigate this money-mule alert:\n"
                    + fence_untrusted_data(safe_alert)
                )
            )
        ],
    }


def _safe_model_messages(
    messages: list,
    privacy: CasePrivacy,
) -> list:
    """Build a model-safe copy of the existing message history."""
    safe_messages = []

    for message in messages:
        if isinstance(message, AIMessage):
            safe_calls = [
                {
                    **call,
                    "args": privacy.mask(call["args"]),
                }
                for call in message.tool_calls
            ]

            safe_messages.append(
                AIMessage(
                    content=privacy.mask(message.content),
                    tool_calls=safe_calls,
                )
            )

        elif isinstance(message, ToolMessage):
            safe_data = privacy.mask(json.loads(message.content))
            safe_messages.append(
                ToolMessage(
                    content=fence_untrusted_data(safe_data),
                    tool_call_id=message.tool_call_id,
                )
            )

        elif isinstance(message, HumanMessage):
            safe_messages.append(HumanMessage(content=privacy.mask(message.content)))

        elif isinstance(message, SystemMessage):
            safe_messages.append(SystemMessage(content=privacy.mask(message.content)))

        else:
            raise PrivacyError("Unsupported model message type")

    return safe_messages


def investigate(
    state: InvestigationState,
    model,
    prompt: str,
    privacy: CasePrivacy | None = None,
) -> dict:
    """Call the model with masked content only."""
    if privacy is None:
        privacy = CasePrivacy()

    response = model.invoke(
        [
            SystemMessage(content=privacy.mask(prompt)),
            *_safe_model_messages(
                state["messages"],
                privacy,
            ),
        ]
    )

    usage = response.usage_metadata or {}

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    estimated_cost = (
        input_tokens * INPUT_PRICE_PER_MILLION
        + output_tokens * OUTPUT_PRICE_PER_MILLION
    ) / 1_000_000

    safe_calls = [
        {
            **call,
            "args": privacy.mask(call["args"]),
        }
        for call in response.tool_calls
    ]

    safe_response = AIMessage(
        content=privacy.mask(response.content),
        tool_calls=safe_calls,
        usage_metadata=response.usage_metadata,
    )

    return {
        "messages": [safe_response],
        "steps_taken": state["steps_taken"] + 1,
        "input_tokens": state["input_tokens"] + input_tokens,
        "output_tokens": state["output_tokens"] + output_tokens,
        "estimated_cost_usd": (state["estimated_cost_usd"] + estimated_cost),
    }


def execute_tools(
    state: InvestigationState,
    privacy: CasePrivacy | None = None,
    config: RunnableConfig | None = None,
) -> dict:
    """Resolve aliases privately, then mask tool results."""
    if privacy is None:
        privacy = CasePrivacy()

    last_message = state["messages"][-1]

    messages = []
    evidence_items = list(state["evidence"])
    typology_checked = state["typology_checked"]
    steps_taken = state["steps_taken"]

    reserved = 0 if typology_checked else 1

    for call in last_message.tool_calls:
        name = call["name"]
        is_typology = name == "typology_search_tool"

        available = MAX_STEPS - steps_taken

        permitted = available > reserved or (
            is_typology and not typology_checked and available > 0
        )

        if not permitted:
            result = {
                "ok": False,
                "error": {
                    "type": "step_limit",
                    "message": "Investigation budget exhausted",
                },
            }

        elif name not in TOOLS_BY_NAME:
            result = {
                "ok": False,
                "error": {
                    "type": "unknown_tool",
                    "message": "Tool is not allowed",
                },
            }
            steps_taken += 1

        else:
            steps_taken += 1

            try:
                arguments = dict(call["args"])

                if name in {
                    "account_activity_tool",
                    "account_score_tool",
                }:
                    arguments["account_id"] = privacy.resolve_account(
                        arguments["account_id"]
                    )

                raw_result = TOOLS_BY_NAME[name].invoke(
                    arguments,
                    config=config,
                )

                result = privacy.mask(json.loads(raw_result))

                if isinstance(result, dict) and isinstance(result.get("data"), dict):
                    result["data"].update(scan_evidence(result["data"]))

                if "evidence_id" in result:
                    evidence_items.append(result)

                if (
                    is_typology
                    and result.get("data", {}).get("ok")
                    and result.get("data", {}).get("chunks")
                ):
                    typology_checked = True

            except PrivacyError:
                result = {
                    "ok": False,
                    "error": {
                        "type": "privacy_rejection",
                        "message": "Unknown or unsafe account alias",
                    },
                }

            except Exception:
                result = {
                    "ok": False,
                    "error": {
                        "type": "tool_error",
                        "message": "Tool execution failed",
                    },
                }

        messages.append(
            ToolMessage(
                content=json.dumps(
                    result,
                    default=str,
                ),
                tool_call_id=call["id"],
            )
        )

    return {
        "messages": messages,
        "evidence": evidence_items,
        "typology_checked": typology_checked,
        "steps_taken": steps_taken,
    }


def route_after_investigate(
    state: InvestigationState,
) -> Literal["tools", "ensure_typology"]:
    if state["steps_taken"] >= MAX_STEPS:
        return "ensure_typology"

    last_message = state["messages"][-1]

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"

    return "ensure_typology"


def route_after_tools(
    state: InvestigationState,
) -> Literal["investigate", "ensure_typology"]:
    reserved = 0 if state["typology_checked"] else 1

    if state["steps_taken"] + reserved >= MAX_STEPS:
        return "ensure_typology"

    return "investigate"


def ensure_typology(
    state: InvestigationState,
    privacy: CasePrivacy | None = None,
) -> dict:
    """Retrieve required typology evidence."""
    if privacy is None:
        privacy = CasePrivacy()

    if state["typology_checked"]:
        return {}

    if state["steps_taken"] >= MAX_STEPS:
        return {
            "typology_checked": False,
            "limit_hit": True,
        }

    alert = state["alert"]

    query = (
        "money mule rapid pass-through funds "
        "short dwell time suspicious transaction patterns "
        f"risk indicators: {alert.get('reasons', [])}"
    )

    try:
        evidence = search_typologies(query)

        result = privacy.mask(evidence.model_dump(mode="json"))
        if isinstance(result.get("data"), dict):
            result["data"].update(scan_evidence(result["data"]))

        succeeded = bool(
            result.get("data", {}).get("ok") and result.get("data", {}).get("chunks")
        )

    except PrivacyError:
        raise

    except Exception:
        result = {
            "source": "search_typologies",
            "error": {
                "type": "tool_error",
                "message": "Typology retrieval failed",
            },
        }
        succeeded = False

    steps_taken = state["steps_taken"] + 1

    return {
        "evidence": [
            *state["evidence"],
            result,
        ],
        "typology_checked": succeeded,
        "steps_taken": steps_taken,
        "limit_hit": steps_taken >= MAX_STEPS,
    }


def assess(
    state: InvestigationState,
    model,
    privacy: CasePrivacy | None = None,
) -> dict:
    """Generate a structured report or safely abstain."""
    if privacy is None:
        privacy = CasePrivacy()

    if not state["typology_checked"]:
        fallback = insufficient_evidence(
            "Required typology evidence was not retrieved."
        )

        return {
            "status": fallback.status,
            "report": None,
            "validation_error": fallback.reason,
        }

    try:
        report = generate_report(
            model,
            privacy.mask(state["alert"]),
            privacy.mask(state["evidence"]),
        )

        return {
            "status": "VERIFYING",
            "report": privacy.mask(report.model_dump(mode="json")),
            "validation_error": "",
        }

    except PrivacyError:
        raise

    except Exception:
        fallback = manual_review("Automated report generation failed.")

        return {
            "status": fallback.status,
            "report": None,
            "validation_error": fallback.reason,
        }


def verify(
    state: InvestigationState,
    model,
    privacy: CasePrivacy | None = None,
) -> dict:
    """Verify citations and output policy, retrying once."""
    if privacy is None:
        privacy = CasePrivacy()

    if state["status"] in {
        "INSUFFICIENT_EVIDENCE",
        "NEEDS_MANUAL_REVIEW",
    }:
        return {}

    report_data = state.get("report")
    error = state.get("validation_error", "")

    for attempt in range(2):
        try:
            if report_data is None:
                raise ValueError(error or "Report generation failed")

            report = CaseReport.model_validate(report_data)

            verify_report(
                report,
                state["evidence"],
            )

            policy = validate_policy(report)

            if not policy.passed:
                raise ValueError("; ".join(policy.violations))

            return {
                "report": report.model_dump(mode="json"),
                "status": "VERIFIED",
                "validation_error": "",
            }

        except Exception:
            error = "Report validation or policy check failed"

            if attempt == 1:
                break

            try:
                report = generate_report(
                    model,
                    privacy.mask(state["alert"]),
                    privacy.mask(state["evidence"]),
                    feedback=error,
                )

                report_data = privacy.mask(report.model_dump(mode="json"))

            except PrivacyError:
                raise

            except Exception:
                fallback = manual_review("Report regeneration failed.")

                return {
                    "status": fallback.status,
                    "report": None,
                    "validation_error": fallback.reason,
                }

    fallback = manual_review("Report failed citation or output-policy validation.")

    return {
        "status": fallback.status,
        "report": None,
        "validation_error": fallback.reason,
    }


def write_investigation_audit(cursor, state: InvestigationState) -> None:
    """Record the saved investigation's ordered, privacy-safe history."""
    case_id = state["case_id"]

    append_audit_event(
        cursor,
        case_id=case_id,
        actor="system",
        action="INVESTIGATION_STARTED",
        details={
            "alert_id": state["alert_id"],
            "thread_id": state.get("thread_id"),
        },
    )

    append_audit_event(
        cursor,
        case_id=case_id,
        actor="system",
        action="ALERT_LOADED",
        details={
            "alert_id": state["alert_id"],
            "scoring_model_version": state["alert"].get("model_version"),
        },
    )

    for message in state["messages"]:
        if isinstance(message, AIMessage):
            usage = message.usage_metadata or {}

            append_audit_event(
                cursor,
                case_id=case_id,
                actor="agent",
                action="LLM_CALLED",
                details={
                    "model": MODEL_NAME,
                    "prompt_version": PROMPT_PATH.name,
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "tool_calls": len(message.tool_calls),
                },
            )

            for call in message.tool_calls:
                append_audit_event(
                    cursor,
                    case_id=case_id,
                    actor="agent",
                    action="TOOL_REQUESTED",
                    details={
                        "tool": call["name"],
                        "tool_call_id": call["id"],
                        # Avoid persisting raw tool arguments.
                        "argument_names": sorted(call["args"].keys()),
                    },
                )

        elif isinstance(message, ToolMessage):
            append_audit_event(
                cursor,
                case_id=case_id,
                actor="tool",
                action="TOOL_RESULT",
                details={
                    "tool_call_id": message.tool_call_id,
                    # Never persist the raw result.
                    "result_recorded": True,
                },
            )

    append_audit_event(
        cursor,
        case_id=case_id,
        actor="agent",
        action="INVESTIGATION_ASSESSED",
        details={
            "status": state["status"],
            "steps_taken": state["steps_taken"],
            "typology_checked": state["typology_checked"],
            "input_tokens_total": state["input_tokens"],
            "output_tokens_total": state["output_tokens"],
            "estimated_cost_usd": state["estimated_cost_usd"],
        },
    )

    append_audit_event(
        cursor,
        case_id=case_id,
        actor="system",
        action="POLICY_CHECK_RESULT",
        details={
            "passed": state["status"] == "VERIFIED",
            "outcome": state["status"],
            "note": (
                "Verified output accepted"
                if state["status"] == "VERIFIED"
                else "Investigation requires fallback or review"
            ),
        },
    )


def save(
    state: InvestigationState,
    privacy: CasePrivacy | None = None,
) -> dict:
    """Persist masked evidence and tool traces."""
    if privacy is None:
        privacy = CasePrivacy()

    trace = []

    for message in state["messages"]:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                trace.append(
                    {
                        "tool": call["name"],
                        "arguments": privacy.mask(call["args"]),
                        "tool_call_id": call["id"],
                    }
                )

        elif isinstance(message, ToolMessage):
            trace.append(
                {
                    "tool_call_id": message.tool_call_id,
                    "result": privacy.mask(message.content),
                }
            )

    trace_record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "events": trace,
        "evidence": privacy.mask(state["evidence"]),
    }

    if state["status"] == "VERIFIED":
        final_status = "AWAITING_REVIEW" if state.get("human_review") else "COMPLETE"
    elif state["status"] == "NEEDS_MANUAL_REVIEW":
        final_status = "NEEDS_MANUAL_REVIEW"
    else:
        final_status = "INSUFFICIENT_EVIDENCE"

    report_data = state.get("report")

    if report_data is not None:
        report_data = privacy.mask(report_data)

    with psycopg.connect(CASE_DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO cases (
                    alert_id,
                    status,
                    summary,
                    report,
                    tool_trace,
                    thread_id,
                    agent_action
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s::jsonb,
                    %s::jsonb,
                    %s,
                    %s
                )
                RETURNING id
                """,
                (
                    state["alert_id"],
                    final_status,
                    (report_data["summary"] if report_data else None),
                    json.dumps(report_data),
                    json.dumps(
                        trace_record,
                        default=str,
                    ),
                    state.get("thread_id"),
                    (report_data.get("recommended_action") if report_data else None),
                ),
            )

            case_id = cursor.fetchone()[0]

            audit_state = {
                **state,
                "case_id": case_id,
            }

            write_investigation_audit(
                cursor,
                audit_state,
            )

            append_audit_event(
                cursor,
                case_id=case_id,
                actor="system",
                action="CASE_SAVED",
                details={
                    "status": final_status,
                    "agent_action": (
                        report_data.get("recommended_action") if report_data else None
                    ),
                    "human_review_required": (final_status == "AWAITING_REVIEW"),
                },
            )

    return {
        "status": final_status,
        "case_id": case_id,
    }


def route_after_save(
    state: InvestigationState,
) -> Literal["review", "end"]:
    if state.get("human_review") and state["status"] == "AWAITING_REVIEW":
        return "review"
    return "end"


def review(state: InvestigationState) -> dict:
    """Pause until an authenticated reviewer submits a decision."""
    if state["status"] != "AWAITING_REVIEW":
        raise ValueError("Case is not awaiting review")

    payload = interrupt(
        {
            "case_id": state["case_id"],
            "report": state["report"],
            "agent_action": state["report"]["recommended_action"],
        }
    )

    decision = ReviewDecision.model_validate(payload)
    agent_action = CaseReport.model_validate(state["report"]).recommended_action

    final_action = decision.resolved_action(agent_action)
    final_status = outcome_status(final_action)

    validate_transition("AWAITING_REVIEW", final_status)

    return {
        "review_decision": decision.model_dump(mode="json"),
        "final_action": final_action.value,
        "reviewer_id": decision.reviewer_id,
        "reviewer_comment": decision.comment,
        "agreement": final_action == agent_action,
        "status": final_status,
    }


def finalize_review(state: InvestigationState) -> dict:
    """Persist the human outcome; never replace the AI report."""
    decision = state.get("review_decision")
    if not decision:
        raise ValueError("Missing human review decision")

    with psycopg.connect(CASE_DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE cases
                SET
                    status = %s,
                    final_action = %s,
                    review_decision = %s,
                    reviewer_id = %s,
                    reviewer_comment = %s,
                    agreement = %s,
                    reviewed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                  AND status = 'AWAITING_REVIEW'
                  AND thread_id = %s
                RETURNING id
                """,
                (
                    state["status"],
                    state["final_action"],
                    decision["decision"],
                    state["reviewer_id"],
                    state["reviewer_comment"],
                    state["agreement"],
                    state["case_id"],
                    state["thread_id"],
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError("Case was already reviewed or checkpoint mismatch")

            append_audit_event(
                cursor,
                case_id=state["case_id"],
                actor=state["reviewer_id"],
                action="HUMAN_DECISION_RECORDED",
                details={
                    "decision": decision["decision"],
                    "agent_action": state["report"]["recommended_action"],
                    "final_action": state["final_action"],
                    "final_status": state["status"],
                    "agreement": state["agreement"],
                    "reviewer_id": state["reviewer_id"],
                    "comment_recorded": bool(state["reviewer_comment"]),
                },
            )

            append_audit_event(
                cursor,
                case_id=state["case_id"],
                actor="system",
                action="CASE_FINALIZED",
                details={
                    "status": state["status"],
                    "final_action": state["final_action"],
                },
            )

    return {"case_id": row[0]}


def build_graph(
    model=None,
    report_model=None,
    checkpointer=None,
    human_review: bool = False,
):
    """Compile one graph with one private privacy context."""
    if model is None:
        model = create_model()

    if report_model is None:
        report_model = create_report_model()

    prompt = PROMPT_PATH.read_text(encoding="utf-8")

    privacy = CasePrivacy()
    builder = StateGraph(InvestigationState)

    builder.add_node(
        "load_alert",
        lambda state: load_alert(state, privacy),
    )

    builder.add_node(
        "investigate",
        lambda state: investigate(state, model, prompt, privacy),
    )

    builder.add_node(
        "tools",
        lambda state, config: execute_tools(
            state,
            privacy,
            config,
        ),
    )

    builder.add_node(
        "ensure_typology",
        lambda state: ensure_typology(state, privacy),
    )

    builder.add_node(
        "assess",
        lambda state: assess(state, report_model, privacy),
    )

    builder.add_node(
        "verify",
        lambda state: verify(state, report_model, privacy),
    )

    builder.add_node(
        "save",
        lambda state: save(state, privacy),
    )

    builder.add_edge(START, "load_alert")
    builder.add_edge("load_alert", "investigate")

    builder.add_conditional_edges(
        "investigate",
        route_after_investigate,
        {
            "tools": "tools",
            "ensure_typology": "ensure_typology",
        },
    )

    builder.add_conditional_edges(
        "tools",
        route_after_tools,
        {
            "investigate": "investigate",
            "ensure_typology": "ensure_typology",
        },
    )

    builder.add_edge("ensure_typology", "assess")
    builder.add_edge("assess", "verify")
    builder.add_edge("verify", "save")

    if human_review:
        if checkpointer is None:
            raise ValueError("Human review requires a persistent checkpointer")

        builder.add_node("review", review)
        builder.add_node("finalize_review", finalize_review)

        builder.add_conditional_edges(
            "save",
            route_after_save,
            {
                "review": "review",
                "end": END,
            },
        )

        builder.add_edge("review", "finalize_review")
        builder.add_edge("finalize_review", END)
    else:
        builder.add_edge("save", END)

    return builder.compile(checkpointer=checkpointer)


def initial_state(
    alert_id: int,
    *,
    thread_id: str | None = None,
    human_review: bool = False,
) -> InvestigationState:
    return {
        "alert_id": alert_id,
        "alert": {},
        "evidence": [],
        "messages": [],
        "steps_taken": 0,
        "limit_hit": False,
        "typology_checked": False,
        "report": None,
        "status": "PENDING",
        "thread_id": thread_id,
        "human_review": human_review,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
    }
