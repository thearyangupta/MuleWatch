from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    """A traceable piece of evidence returned by an investigator tool."""

    evidence_id: str
    source: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


def create_evidence(
    *,
    source: str,
    summary: str,
    data: dict[str, Any],
) -> EvidenceItem:
    """Wrap a tool result in an evidence item with a unique evidence ID."""

    return EvidenceItem(
        evidence_id=f"evidence-{uuid4().hex}",
        source=source,
        summary=summary,
        data=data,
    )
