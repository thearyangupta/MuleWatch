from pathlib import Path

graph_path = Path("agent/graph.py")
state_path = Path("agent/state.py")

graph = graph_path.read_text(encoding="utf-8")
state = state_path.read_text(encoding="utf-8")


def replace_once(source: str, old: str, new: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one source anchor, found {count}: {old[:70]}")
    return source.replace(old, new, 1)


state = replace_once(
    state,
    "    case_id: NotRequired[int]",
    """    case_id: NotRequired[int]
    thread_id: NotRequired[str]
    human_review: NotRequired[bool]
    review_decision: NotRequired[dict[str, Any]]
    final_action: NotRequired[str]
    reviewer_id: NotRequired[str]
    reviewer_comment: NotRequired[str]
    agreement: NotRequired[bool]""",
)

graph = replace_once(
    graph,
    "from langgraph.graph import END, START, StateGraph",
    """from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agent.state_machine import (
    ReviewDecision,
    outcome_status,
    validate_transition,
)""",
)

graph = replace_once(
    graph,
    '''    if state["status"] == "VERIFIED":
        final_status = "COMPLETE"''',
    """    if state["status"] == "VERIFIED":
        final_status = (
            "AWAITING_REVIEW"
            if state.get("human_review")
            else "COMPLETE"
        )""",
)

graph = replace_once(
    graph,
    """                    tool_trace
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s::jsonb,
                    %s::jsonb
                )
                RETURNING id""",
    """                    tool_trace,
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
                RETURNING id""",
)

graph = replace_once(
    graph,
    """                    json.dumps(
                        trace_record,
                        default=str,
                    ),
                ),""",
    """                    json.dumps(
                        trace_record,
                        default=str,
                    ),
                    state.get("thread_id"),
                    (
                        report_data.get("recommended_action")
                        if report_data else None
                    ),
                ),""",
)

anchor = "\ndef build_graph(\n"

review_code = '''

def route_after_save(
    state: InvestigationState,
) -> Literal["review", "end"]:
    if (
        state.get("human_review")
        and state["status"] == "AWAITING_REVIEW"
    ):
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
    agent_action = CaseReport.model_validate(
        state["report"]
    ).recommended_action

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
                raise ValueError(
                    "Case was already reviewed or checkpoint mismatch"
                )

    return {"case_id": row[0]}

'''

graph = replace_once(
    graph,
    anchor,
    review_code + anchor,
)

graph = replace_once(
    graph,
    """def build_graph(
    model=None,
    report_model=None,
):""",
    """def build_graph(
    model=None,
    report_model=None,
    checkpointer=None,
    human_review: bool = False,
):""",
)

graph = replace_once(
    graph,
    """    builder.add_edge("verify", "save")
    builder.add_edge("save", END)

    return builder.compile()""",
    """    builder.add_edge("verify", "save")

    if human_review:
        if checkpointer is None:
            raise ValueError(
                "Human review requires a persistent checkpointer"
            )

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

    return builder.compile(checkpointer=checkpointer)""",
)

graph = replace_once(
    graph,
    """def initial_state(alert_id: int) -> InvestigationState:""",
    """def initial_state(
    alert_id: int,
    *,
    thread_id: str | None = None,
    human_review: bool = False,
) -> InvestigationState:""",
)

graph = replace_once(
    graph,
    """        "status": "PENDING",
        "input_tokens": 0,""",
    """        "status": "PENDING",
        "thread_id": thread_id,
        "human_review": human_review,
        "input_tokens": 0,""",
)

# Write only after every source anchor has passed.
state_path.write_text(state, encoding="utf-8")
graph_path.write_text(graph, encoding="utf-8")

print("Day 4 graph and state patches applied.")
