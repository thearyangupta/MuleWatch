"""Hash-chained, append-only audit events."""

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv()

CASE_DATABASE_URL = os.getenv(
    "MULEWATCH_CASE_DATABASE_URL",
    "postgresql://mulewatch:mulewatch_dev@localhost:5432/mulewatch",
)

GENESIS_HASH = "0" * 64
AUDIT_LOCK_ID = 2026101405


def canonical_bytes(
    *,
    case_id: int | None,
    actor: str,
    action: str,
    details: dict[str, Any],
    created_at: datetime,
    previous_hash: str,
) -> bytes:
    """Produce deterministic bytes for hashing."""
    if created_at.tzinfo is None:
        raise ValueError("Audit timestamp must be timezone-aware")

    payload = {
        "case_id": case_id,
        "actor": actor,
        "action": action,
        "details": details,
        "created_at": created_at.astimezone(timezone.utc).isoformat(),
        "previous_hash": previous_hash,
    }

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def calculate_hash(
    *,
    case_id: int | None,
    actor: str,
    action: str,
    details: dict[str, Any],
    created_at: datetime,
    previous_hash: str,
) -> str:
    return hashlib.sha256(
        canonical_bytes(
            case_id=case_id,
            actor=actor,
            action=action,
            details=details,
            created_at=created_at,
            previous_hash=previous_hash,
        )
    ).hexdigest()


def append_audit_event(
    cursor: psycopg.Cursor,
    *,
    case_id: int | None,
    actor: str,
    action: str,
    details: dict[str, Any],
) -> int:
    """
    Append an event inside the caller's DB transaction.

    The caller must commit the transaction.
    """
    if not actor.strip() or not action.strip():
        raise ValueError("Actor and action are required")

    if not isinstance(details, dict):
        raise ValueError("Audit details must be a dictionary")

    cursor.execute(
        "SELECT pg_advisory_xact_lock(%s)",
        (AUDIT_LOCK_ID,),
    )

    cursor.execute(
        """
        SELECT event_hash
        FROM audit_log
        ORDER BY id DESC
        LIMIT 1
        """
    )

    last_row = cursor.fetchone()
    previous_hash = last_row[0] if last_row else GENESIS_HASH
    cursor.execute("SELECT clock_timestamp()")
    created_at = cursor.fetchone()[0]

    event_hash = calculate_hash(
        case_id=case_id,
        actor=actor,
        action=action,
        details=details,
        created_at=created_at,
        previous_hash=previous_hash,
    )

    cursor.execute(
        """
        INSERT INTO audit_log (
            case_id,
            actor,
            action,
            details,
            created_at,
            previous_hash,
            event_hash
        )
        VALUES (
            %s, %s, %s, %s::jsonb,
            %s, %s, %s
        )
        RETURNING id
        """,
        (
            case_id,
            actor,
            action,
            json.dumps(
                details,
                sort_keys=True,
                allow_nan=False,
            ),
            created_at,
            previous_hash,
            event_hash,
        ),
    )

    return cursor.fetchone()[0]


def verify_rows(
    rows: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Verify a complete, globally ordered audit chain."""
    previous_hash = GENESIS_HASH
    previous_id = 0

    for row in rows:
        event_id = row["id"]

        if event_id <= previous_id:
            return False, "Audit IDs are not increasing"

        if row["previous_hash"] != previous_hash:
            return (
                False,
                f"Broken chain at event {event_id}",
            )

        expected_hash = calculate_hash(
            case_id=row["case_id"],
            actor=row["actor"],
            action=row["action"],
            details=row["details"],
            created_at=row["created_at"],
            previous_hash=row["previous_hash"],
        )

        if row["event_hash"] != expected_hash:
            return (
                False,
                f"Content hash mismatch at event {event_id}",
            )

        previous_hash = row["event_hash"]
        previous_id = event_id

    return True, f"Verified {len(rows)} audit events"


def verify_audit_chain(
    connection: psycopg.Connection | None = None,
) -> tuple[bool, str]:
    """Read and verify the entire global chain."""
    if connection is None:
        with psycopg.connect(
            CASE_DATABASE_URL,
            row_factory=dict_row,
        ) as own_connection:
            return verify_audit_chain(own_connection)

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT id, case_id, actor, action, details,
                   created_at, previous_hash, event_hash
            FROM audit_log
            ORDER BY id
            """
        )
        rows = cursor.fetchall()

    return verify_rows(rows)
