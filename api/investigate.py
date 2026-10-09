from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.graph import build_graph, initial_state
from agent.report import CaseReport

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
    """Run an investigation and return its persisted case."""

    if alert_id < 1:
        raise HTTPException(
            status_code=422,
            detail="alert_id must be positive",
        )

    try:
        graph = build_graph()
        result = graph.invoke(initial_state(alert_id))

    except ValueError as exc:
        if str(exc) == f"Alert {alert_id} not found":
            raise HTTPException(
                status_code=404,
                detail="Alert not found",
            ) from exc
        raise

    return InvestigationResponse(
        case_id=result["case_id"],
        status=result["status"],
        report=result.get("report"),
    )
