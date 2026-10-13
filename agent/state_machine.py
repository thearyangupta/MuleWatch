from typing import Literal

from pydantic import BaseModel, Field

from agent.report import RecommendedAction

CaseStatus = Literal[
    "NEW",
    "INVESTIGATING",
    "AWAITING_REVIEW",
    "CLOSED",
    "ESCALATED",
    "NEEDS_MANUAL_REVIEW",
    "INSUFFICIENT_EVIDENCE",
]

DecisionType = Literal["approve", "override", "escalate"]

ALLOWED_TRANSITIONS = {
    "NEW": {"INVESTIGATING"},
    "INVESTIGATING": {
        "AWAITING_REVIEW",
        "NEEDS_MANUAL_REVIEW",
        "INSUFFICIENT_EVIDENCE",
    },
    "AWAITING_REVIEW": {"CLOSED", "ESCALATED"},
    "CLOSED": set(),
    "ESCALATED": set(),
    "NEEDS_MANUAL_REVIEW": set(),
    "INSUFFICIENT_EVIDENCE": set(),
}


class InvalidTransition(ValueError):
    pass


def validate_transition(current: str, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"Illegal case transition: {current} -> {target}")


class ReviewDecision(BaseModel):
    decision: DecisionType
    reviewer_id: str = Field(min_length=1, max_length=128)
    comment: str = Field(min_length=1, max_length=2000)
    final_action: RecommendedAction | None = None

    def resolved_action(self, agent_action: RecommendedAction) -> RecommendedAction:
        if self.decision == "approve":
            if self.final_action is not None:
                raise ValueError("Approve must not supply an override action.")
            return agent_action

        if self.decision == "escalate":
            if self.final_action is not None:
                raise ValueError("Escalate must not supply an override action.")
            return RecommendedAction.ESCALATE_TO_INVESTIGATOR

        if self.final_action is None:
            raise ValueError("Override requires final_action.")

        if self.final_action == agent_action:
            raise ValueError("Override must change the agent recommendation.")

        return self.final_action


def outcome_status(action: RecommendedAction) -> str:
    if action == RecommendedAction.ESCALATE_TO_INVESTIGATOR:
        return "ESCALATED"
    return "CLOSED"
