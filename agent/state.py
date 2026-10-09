from typing import Annotated, Any, NotRequired, TypedDict

from langgraph.graph.message import add_messages


class InvestigationState(TypedDict):
    alert_id: int
    alert: dict[str, Any]
    evidence: list[dict[str, Any]]
    messages: Annotated[list, add_messages]
    steps_taken: int
    limit_hit: bool
    typology_checked: bool
    report: dict[str, Any] | None
    status: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    validation_error: NotRequired[str]
    case_id: NotRequired[int]
