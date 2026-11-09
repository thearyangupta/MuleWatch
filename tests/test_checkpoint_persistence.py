import uuid
from typing import TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agent.review_runtime import CHECKPOINT_DATABASE_URL


class State(TypedDict):
    status: str
    decision: str


def pause(state: State):
    decision = interrupt({"status": state["status"]})
    return {
        "status": "CLOSED",
        "decision": decision["decision"],
    }


builder = StateGraph(State)
builder.add_node("pause", pause)
builder.add_edge(START, "pause")
builder.add_edge("pause", END)

thread_id = f"day4-persistence-{uuid.uuid4()}"
config = {"configurable": {"thread_id": thread_id}}

# First connection: pause and persist.
with PostgresSaver.from_conn_string(CHECKPOINT_DATABASE_URL) as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)

    graph.invoke(
        {"status": "AWAITING_REVIEW", "decision": ""},
        config=config,
    )

    assert "pause" in graph.get_state(config).next

print("PASS: graph paused in PostgreSQL")

with PostgresSaver.from_conn_string(CHECKPOINT_DATABASE_URL) as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)

    assert "pause" in graph.get_state(config).next

    result = graph.invoke(
        Command(resume={"decision": "approve"}),
        config=config,
    )

    assert result["status"] == "CLOSED"
    assert result["decision"] == "approve"

print("PASS: checkpoint restored and resumed")
