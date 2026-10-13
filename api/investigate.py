from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.report import CaseReport
from api.cases import start_review_investigation

router = APIRouter()


class InvestigationResponse(BaseModel):
    case_id: int
    status: str
    report: CaseReport | None


@router.post(
    "/investigate/{alert_id}",
    response_model=InvestigationResponse,
)
def investigate_alert(alert_id: int) -> InvestigationResponse:
    """
    Start an investigation with human-in-the-loop review.

    A successfully verified investigation pauses at
    AWAITING_REVIEW instead of completing automatically.
    """

    if alert_id < 1:
        raise HTTPException(
            status_code=422,
            detail="alert_id must be positive",
        )

    result = start_review_investigation(alert_id)

    return InvestigationResponse(
        case_id=result.case_id,
        status=result.status,
        report=result.report,
    )
