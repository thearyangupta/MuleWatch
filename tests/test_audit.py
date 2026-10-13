"""Unit tests for MuleWatch audit-chain integrity."""

from copy import deepcopy
from datetime import datetime, timezone

from agent.audit import (
    GENESIS_HASH,
    calculate_hash,
    verify_rows,
)


def make_event(
    event_id: int,
    previous_hash: str,
    action: str,
) -> dict:
    created_at = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)

    details = {
        "status": "ESCALATED",
        "test": True,
    }

    event_hash = calculate_hash(
        case_id=5,
        actor="reviewer-test",
        action=action,
        details=details,
        created_at=created_at,
        previous_hash=previous_hash,
    )

    return {
        "id": event_id,
        "case_id": 5,
        "actor": "reviewer-test",
        "action": action,
        "details": details,
        "created_at": created_at,
        "previous_hash": previous_hash,
        "event_hash": event_hash,
    }


def test_empty_chain_is_valid():
    assert verify_rows([])[0] is True


def test_single_event_is_valid():
    event = make_event(1, GENESIS_HASH, "CASE_SAVED")
    assert verify_rows([event])[0] is True


def test_multiple_events_are_valid():
    first = make_event(1, GENESIS_HASH, "CASE_SAVED")
    second = make_event(2, first["event_hash"], "HUMAN_DECISION_RECORDED")

    assert verify_rows([first, second])[0] is True


def test_modified_event_is_detected():
    event = make_event(1, GENESIS_HASH, "CASE_SAVED")

    tampered = deepcopy(event)
    tampered["details"]["status"] = "CLOSED"

    valid, message = verify_rows([tampered])

    assert valid is False
    assert "Content hash mismatch" in message


def test_modified_actor_is_detected():
    event = make_event(1, GENESIS_HASH, "CASE_SAVED")
    event["actor"] = "unknown-reviewer"

    assert verify_rows([event])[0] is False


def test_modified_timestamp_is_detected():
    event = make_event(1, GENESIS_HASH, "CASE_SAVED")
    event["created_at"] = datetime(2026, 10, 15, tzinfo=timezone.utc)

    assert verify_rows([event])[0] is False


def test_broken_previous_hash_is_detected():
    first = make_event(1, GENESIS_HASH, "CASE_SAVED")
    second = make_event(2, GENESIS_HASH, "CASE_FINALIZED")

    assert verify_rows([first, second])[0] is False


def test_reordered_events_are_detected():
    first = make_event(1, GENESIS_HASH, "CASE_SAVED")
    second = make_event(2, first["event_hash"], "CASE_FINALIZED")

    assert verify_rows([second, first])[0] is False


def test_hash_is_deterministic():
    event = make_event(1, GENESIS_HASH, "CASE_SAVED")

    expected = calculate_hash(
        case_id=event["case_id"],
        actor=event["actor"],
        action=event["action"],
        details=event["details"],
        created_at=event["created_at"],
        previous_hash=event["previous_hash"],
    )

    assert expected == event["event_hash"]


def test_different_actions_produce_different_hashes():
    first = make_event(1, GENESIS_HASH, "CASE_SAVED")
    second = make_event(1, GENESIS_HASH, "CASE_FINALIZED")

    assert first["event_hash"] != second["event_hash"]
