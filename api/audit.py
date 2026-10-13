"""Authenticated audit history endpoint."""

import psycopg
from fastapi import APIRouter, Depends
from psycopg.rows import dict_row

from agent.audit import (
    CASE_DATABASE_URL,
    verify_audit_chain,
)
from api.cases import get_case_row, require_reviewer

router = APIRouter(
    prefix="/cases",
    tags=["Case Audit"],
)


@router.get(
    "/{case_id}/audit",
    dependencies=[Depends(require_reviewer)],
)
def get_case_audit(case_id: int):
    """Return the ordered audit history of a case."""
    # Reuse the existing 404 behavior.
    case = get_case_row(case_id)

    with psycopg.connect(
        CASE_DATABASE_URL,
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")

        verified, verification_message = verify_audit_chain(connection)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, case_id, actor, action, details,
                       created_at, previous_hash, event_hash
                FROM audit_log
                WHERE case_id = %s
                ORDER BY id ASC
                """,
                (case_id,),
            )
            events = cursor.fetchall()

    return {
        "case_id": case_id,
        "alert_id": case["alert_id"],
        "case_status": case["status"],
        "chain_valid": verified,
        "verification_message": verification_message,
        "event_count": len(events),
        "events": events,
    }
