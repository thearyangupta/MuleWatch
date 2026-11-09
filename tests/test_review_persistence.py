import os
import uuid
from typing import TypedDict

import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class ReviewState(TypedDict):
    status: str
    decision: str


def review_node(state: ReviewState):
    answer = interrupt({"status": state["status"]})
    return {
        "status": "CLOSED",
        "decision": answer["decision"],
    }


def build_review_graph(checkpointer):
    builder = StateGraph(ReviewState)
    builder.add_node("review", review_node)
    builder.add_edge(START, "review")
    builder.add_edge("review", END)
    return builder.compile(checkpointer=checkpointer)


def test_review_checkpoint_survives_new_graph_connection():
    database_url = os.getenv("MULEWATCH_E2E_CHECKPOINT_DATABASE_URL")

    if not database_url:
        pytest.skip("Disposable checkpoint database not configured")

    if os.getenv("MULEWATCH_ALLOW_CHECKPOINT_TEST_WRITES") != "YES":
        pytest.skip("Checkpoint test writes not explicitly authorized")

    # Only an explicitly identified disposable database is permitted.
    from urllib.parse import urlparse

    parsed = urlparse(database_url)
    database_name = parsed.path.lstrip("/")

    if database_name != "mulewatch_checkpoint_test":
        pytest.fail("Checkpoint database must be mulewatch_checkpoint_test")

    thread_id = f"review-persistence-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    # First graph instance: create the interrupted checkpoint.
    with PostgresSaver.from_conn_string(database_url) as saver:
        saver.setup()
        graph = build_review_graph(saver)

        graph.invoke(
            {"status": "AWAITING_REVIEW", "decision": ""},
            config=config,
        )

        assert "review" in graph.get_state(config).next

    # New connection and graph: recover and resume the same thread.
    with PostgresSaver.from_conn_string(database_url) as saver:
        graph = build_review_graph(saver)

        assert "review" in graph.get_state(config).next

        result = graph.invoke(
            Command(resume={"decision": "approve"}),
            config=config,
        )

        assert result["status"] == "CLOSED"
        assert result["decision"] == "approve"
        assert not graph.get_state(config).next
