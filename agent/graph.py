import json
import os
from pathlib import Path
from typing import Literal

import psycopg
from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from psycopg.rows import dict_row

from agent.state import InvestigationState
from agent.tools import (
    get_account_activity,
    score_account,
    search_typologies,
)

MAX_STEPS = 6

DATABASE_URL = os.getenv(
    "MULEWATCH_DATABASE_URL",
    "postgresql://mulewatch_readonly:mulewatch_readonly_dev@localhost:5432/mulewatch",
)

MODEL_NAME = os.getenv(
    "MULEWATCH_LLM_MODEL",
    "openai:gpt-4o-mini",
)

INPUT_PRICE_PER_MILLION = float(os.getenv("MULEWATCH_INPUT_PRICE_PER_MILLION", "0"))

OUTPUT_PRICE_PER_MILLION = float(os.getenv("MULEWATCH_OUTPUT_PRICE_PER_MILLION", "0"))

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "investigate_v1.md"


@tool
def account_activity_tool(
    account_id: str,
    days: int = 30,
) -> str:
    """Inspect an account's recent transactions and activity."""
    return get_account_activity(account_id, days).model_dump_json()


@tool
def account_score_tool(account_id: str) -> str:
    """Retrieve an account's ML risk score and SHAP reasons."""
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
    """Initialize a configurable tool-enabled chat model."""
    return init_chat_model(
        MODEL_NAME,
        temperature=0,
    ).bind_tools(TOOLS)


def load_alert(state: InvestigationState) -> dict:
    """Fetch an existing alert with a parameterized read-only query."""

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

    return {
        "alert": alert,
        "status": "INVESTIGATING",
        "messages": [
            HumanMessage(
                content=(
                    "Investigate this money-mule alert:\n"
                    f"{json.dumps(alert, default=str)}"
                )
            )
        ],
    }


def investigate(
    state: InvestigationState,
    model,
    prompt: str,
) -> dict:
    """Invoke the LLM and record its usage."""

    response = model.invoke(
        [
            SystemMessage(content=prompt),
            *state["messages"],
        ]
    )

    usage = response.usage_metadata or {}

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    estimated_cost = (
        input_tokens * INPUT_PRICE_PER_MILLION
        + output_tokens * OUTPUT_PRICE_PER_MILLION
    ) / 1_000_000

    return {
        "messages": [response],
        "steps_taken": state["steps_taken"] + 1,
        "input_tokens": state["input_tokens"] + input_tokens,
        "output_tokens": state["output_tokens"] + output_tokens,
        "estimated_cost_usd": (state["estimated_cost_usd"] + estimated_cost),
    }


def execute_tools(state: InvestigationState) -> dict:
    """Execute only approved tools within the remaining budget."""

    last_message = state["messages"][-1]

    messages = []
    evidence_items = list(state["evidence"])
    typology_checked = state["typology_checked"]
    steps_taken = state["steps_taken"]

    # Reserve one step for the mandatory typology search
    # until a successful typology retrieval has occurred.
    reserved = 0 if typology_checked else 1

    for call in last_message.tool_calls:
        name = call["name"]

        is_typology = name == "typology_search_tool"

        # A typology call can use the reserved step.
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
                raw_result = TOOLS_BY_NAME[name].invoke(call["args"])
                result = json.loads(raw_result)

                if "evidence_id" in result:
                    evidence_items.append(result)

                if (
                    is_typology
                    and result.get("data", {}).get("ok")
                    and result.get("data", {}).get("chunks")
                ):
                    typology_checked = True

            except Exception as exc:
                result = {
                    "ok": False,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }

        messages.append(
            ToolMessage(
                content=json.dumps(result, default=str),
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
    """Choose tool execution or the mandatory typology stage."""

    if state["steps_taken"] >= MAX_STEPS:
        return "ensure_typology"

    last_message = state["messages"][-1]

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"

    return "ensure_typology"


def route_after_tools(
    state: InvestigationState,
) -> Literal["investigate", "ensure_typology"]:
    """Prevent another LLM call when the budget is exhausted."""

    reserved = 0 if state["typology_checked"] else 1

    if state["steps_taken"] + reserved >= MAX_STEPS:
        return "ensure_typology"

    return "investigate"


def ensure_typology(state: InvestigationState) -> dict:
    """Perform the mandatory typology search if not yet completed."""

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

        result = evidence.model_dump(mode="json")

        succeeded = bool(
            result.get("data", {}).get("ok") and result.get("data", {}).get("chunks")
        )

    except Exception as exc:
        result = {
            "source": "search_typologies",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
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


def assess(state: InvestigationState) -> dict:
    """Record a preliminary assessment for Day 4 reporting."""

    typology_checked = state["typology_checked"]

    status = "ASSESSING" if typology_checked else "INSUFFICIENT_EVIDENCE"

    return {
        "status": status,
        "limit_hit": state["steps_taken"] >= MAX_STEPS,
        "report": {
            "alert_id": state["alert_id"],
            "evidence_count": len(state["evidence"]),
            "typology_checked": typology_checked,
            "investigation_steps": state["steps_taken"],
            "note": (
                "Preliminary investigation complete."
                if typology_checked
                else "Required typology evidence is unavailable."
            ),
        },
    }


def save(state: InvestigationState) -> dict:
    """Finalize the preliminary state without database writes."""

    if state["status"] == "INSUFFICIENT_EVIDENCE":
        return {
            "status": "INSUFFICIENT_EVIDENCE",
        }

    return {
        "status": "COMPLETE",
    }


def build_graph(model=None):
    """Compile the bounded investigator state graph."""

    if model is None:
        model = create_model()

    prompt = PROMPT_PATH.read_text(encoding="utf-8")

    builder = StateGraph(InvestigationState)

    builder.add_node("load_alert", load_alert)

    builder.add_node(
        "investigate",
        lambda state: investigate(
            state,
            model,
            prompt,
        ),
    )

    builder.add_node("tools", execute_tools)
    builder.add_node("ensure_typology", ensure_typology)
    builder.add_node("assess", assess)
    builder.add_node("save", save)

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
    builder.add_edge("assess", "save")
    builder.add_edge("save", END)

    return builder.compile()


def initial_state(alert_id: int) -> InvestigationState:
    """Initialize a new investigation."""

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
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
    }
