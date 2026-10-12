from typing import Literal

from pydantic import BaseModel, Field

FallbackStatus = Literal[
    "INSUFFICIENT_EVIDENCE",
    "NEEDS_MANUAL_REVIEW",
]


class FallbackResult(BaseModel):
    status: FallbackStatus
    reason: str
    open_questions: list[str] = Field(default_factory=list)


def insufficient_evidence(
    reason: str = "Required evidence is unavailable.",
) -> FallbackResult:
    return FallbackResult(
        status="INSUFFICIENT_EVIDENCE",
        reason=reason,
        open_questions=[
            "Which required investigation evidence is missing?",
            "Can the missing evidence be retrieved independently?",
        ],
    )


def manual_review(
    reason: str = "Automated assessment could not be completed.",
) -> FallbackResult:
    return FallbackResult(
        status="NEEDS_MANUAL_REVIEW",
        reason=reason,
        open_questions=[
            "Can an investigator review the collected evidence?",
            "Does the case require another assessment attempt?",
        ],
    )
