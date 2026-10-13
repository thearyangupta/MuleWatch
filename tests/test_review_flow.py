from unittest.mock import patch

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agent.report import RecommendedAction
from agent.state_machine import (
    InvalidTransition,
    ReviewDecision,
    outcome_status,
    validate_transition,
)


def test_legal_transition():
    validate_transition("INVESTIGATING", "AWAITING_REVIEW")
    validate_transition("AWAITING_REVIEW", "CLOSED")


def test_illegal_transition():
    with pytest.raises(InvalidTransition):
        validate_transition("CLOSED", "AWAITING_REVIEW")


def test_approve_keeps_agent_action():
    decision = ReviewDecision(
        decision="approve",
        reviewer_id="analyst-1",
        comment="Evidence independently reviewed.",
    )
    result = decision.resolved_action(RecommendedAction.ENHANCED_MONITORING)
    assert result == RecommendedAction.ENHANCED_MONITORING


def test_override_changes_action():
    decision = ReviewDecision(
        decision="override",
        reviewer_id="analyst-1",
        comment="Additional evidence warrants escalation.",
        final_action="ESCALATE_TO_INVESTIGATOR",
    )
    result = decision.resolved_action(RecommendedAction.ENHANCED_MONITORING)
    assert result == RecommendedAction.ESCALATE_TO_INVESTIGATOR


def test_override_requires_different_action():
    decision = ReviewDecision(
        decision="override",
        reviewer_id="analyst-1",
        comment="Reviewed.",
        final_action="ENHANCED_MONITORING",
    )
    with pytest.raises(ValueError):
        decision.resolved_action(RecommendedAction.ENHANCED_MONITORING)


def test_escalate_action():
    decision = ReviewDecision(
        decision="escalate",
        reviewer_id="analyst-1",
        comment="Escalate for specialist investigation.",
    )
    action = decision.resolved_action(RecommendedAction.CLOSE_NO_ACTION)
    assert outcome_status(action) == "ESCALATED"


def test_review_comment_required():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReviewDecision(
            decision="approve",
            reviewer_id="analyst-1",
            comment="",
        )


def test_review_interrupt_and_resume():
    """Exercise real LangGraph interrupt/resume semantics."""

    class ReviewState(dict):
        pass

    from typing import TypedDict

    class State(TypedDict):
        status: str
        decision: str

    def review_node(state: State):
        answer = interrupt({"status": state["status"]})
        return {
            "status": "CLOSED",
            "decision": answer["decision"],
        }

    builder = StateGraph(State)
    builder.add_node("review", review_node)
    builder.add_edge(START, "review")
    builder.add_edge("review", END)

    graph = builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-review-1"}}

    graph.invoke(
        {
            "status": "AWAITING_REVIEW",
            "decision": "",
        },
        config=config,
    )

    snapshot = graph.get_state(config)
    assert "review" in snapshot.next

    result = graph.invoke(
        Command(resume={"decision": "approve"}),
        config=config,
    )

    assert result["status"] == "CLOSED"
    assert result["decision"] == "approve"


def test_unauthorized_review_rejected():
    from fastapi.testclient import TestClient

    from scoring.api import app

    with patch.dict(
        "os.environ",
        {"MULEWATCH_REVIEW_API_KEY": "test-secret"},
    ):
        response = TestClient(app).get("/cases")

    assert response.status_code == 401


def test_review_api_not_configured():
    from fastapi.testclient import TestClient

    from scoring.api import app

    with patch.dict(
        "os.environ",
        {},
    ):
        with patch(
            "api.cases.os.getenv",
            return_value=None,
        ):
            response = TestClient(app).get("/cases")

    assert response.status_code == 503
