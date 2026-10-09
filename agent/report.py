from enum import Enum

from pydantic import BaseModel, Field


class RiskRating(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RecommendedAction(str, Enum):
    CLOSE_NO_ACTION = "CLOSE_NO_ACTION"
    ENHANCED_MONITORING = "ENHANCED_MONITORING"
    ESCALATE_TO_INVESTIGATOR = "ESCALATE_TO_INVESTIGATOR"


class Finding(BaseModel):
    claim: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class TypologyMatch(BaseModel):
    typology: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    chunk_ids: list[str] = Field(min_length=1)


class CaseReport(BaseModel):
    summary: str = Field(min_length=1)
    risk_rating: RiskRating
    recommended_action: RecommendedAction
    findings: list[Finding]
    typology_matches: list[TypologyMatch]
    open_questions: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


def generate_report(
    model,
    alert: dict,
    evidence: list[dict],
    feedback: str = "",
) -> CaseReport:
    """Generate a typed report from the collected evidence."""

    from langchain_core.messages import HumanMessage, SystemMessage

    structured_model = model.with_structured_output(CaseReport)

    instructions = (
        "You are a financial crime investigation assistant. "
        "Produce a structured CaseReport using only the supplied evidence. "
        "Every finding must cite existing evidence IDs. "
        "Every typology match must cite a retrieved typology evidence ID "
        "and its actual chunk IDs. "
        "Do not invent transactions, facts, or citations. "
        "Do not recommend freezing accounts. "
        "A suspicious indicator is not proof of criminal activity."
    )

    import json

    payload = {
        "alert": alert,
        "evidence": evidence,
        "validation_feedback": feedback,
    }

    result = structured_model.invoke(
        [
            SystemMessage(content=instructions),
            HumanMessage(content=json.dumps(payload, default=str)),
        ]
    )

    return CaseReport.model_validate(result)
