"""Week 4 Day 1: PII leakage regression tests."""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from faker import Faker
from langchain_core.messages import AIMessage, HumanMessage

from agent.evidence import create_evidence
from agent.graph import execute_tools, investigate
from agent.pii import CasePrivacy, PrivacyError


class RecordingModel:
    """Fake LLM that records every outgoing request."""

    def __init__(self):
        self.requests = []

    def invoke(self, messages):
        self.requests.append(messages)

        return AIMessage(
            content="Investigation reviewed",
            usage_metadata={
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        )


def test_consistent_customer_alias():
    privacy = CasePrivacy()

    first = privacy.alias("customer-17")
    second = privacy.alias("customer-17")
    third = privacy.alias("customer-18")

    assert first == second
    assert first == "CUST_001"
    assert third == "CUST_002"


def test_account_alias_resolution():
    privacy = CasePrivacy()

    alias = privacy.alias(
        "REAL_ACCOUNT_123",
        "account",
    )

    assert alias == "ACC_001"
    assert privacy.resolve_account(alias) == "REAL_ACCOUNT_123"

    with pytest.raises(PrivacyError):
        privacy.resolve_account("ACC_999")


def test_structured_pii_is_removed():
    faker = Faker()
    privacy = CasePrivacy()

    customer = {
        "name": faker.name(),
        "email": faker.email(),
        "phone": faker.phone_number(),
        "address": faker.address(),
        "customer_id": 17,
        "account_id": "REAL_ACCOUNT_123",
    }

    safe = privacy.mask(customer)
    payload = json.dumps(safe)

    for key in ("name", "email", "phone", "address"):
        assert customer[key] not in payload

    assert "REAL_ACCOUNT_123" not in payload
    assert safe["name"].startswith("CUST_")
    assert safe["account_id"].startswith("ACC_")


def test_actual_investigation_llm_payload_and_logs(caplog):
    faker = Faker()
    privacy = CasePrivacy()
    model = RecordingModel()

    name = faker.name()
    email = faker.email()
    phone = faker.phone_number()

    state = {
        "alert_id": 1,
        "messages": [
            HumanMessage(content=(f"Investigate {name}, email {email}, phone {phone}"))
        ],
        "steps_taken": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
    }

    with caplog.at_level(logging.DEBUG):
        investigate(
            state,
            model,
            "You are an investigator.",
            privacy,
        )

    assert len(model.requests) == 1

    payload = repr(model.requests)

    for secret in (name, email, phone):
        assert secret not in payload
        assert secret not in caplog.text


def test_tool_executes_using_real_id_but_masks_evidence():
    privacy = CasePrivacy()

    alias = privacy.alias(
        "REAL_ACCOUNT_123",
        "account",
    )

    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "account_score_tool",
                        "args": {"account_id": alias},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            )
        ],
        "evidence": [],
        "typology_checked": False,
        "steps_taken": 0,
    }

    fake_evidence = create_evidence(
        source="score_account",
        summary="Score for REAL_ACCOUNT_123",
        data={
            "ok": True,
            "account_id": "REAL_ACCOUNT_123",
            "risk_score": 0.91,
            "model_version": "1",
            "reasons": [],
        },
    )

    mock_tool = MagicMock()
    mock_tool.invoke.return_value = fake_evidence.model_dump_json()

    with patch.dict(
        "agent.graph.TOOLS_BY_NAME",
        {"account_score_tool": mock_tool},
    ):
        result = execute_tools(
            state,
            privacy,
        )

    mock_tool.invoke.assert_called_once_with({"account_id": "REAL_ACCOUNT_123"})

    payload = json.dumps(
        result["evidence"],
        default=str,
    )

    assert "REAL_ACCOUNT_123" not in payload
    assert alias in payload


def test_unknown_alias_does_not_execute_tool():
    privacy = CasePrivacy()

    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "account_score_tool",
                        "args": {"account_id": "ACC_999"},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            )
        ],
        "evidence": [],
        "typology_checked": False,
        "steps_taken": 0,
    }

    mock_tool = MagicMock()

    with patch.dict(
        "agent.graph.TOOLS_BY_NAME",
        {"account_score_tool": mock_tool},
    ):
        result = execute_tools(
            state,
            privacy,
        )

    mock_tool.invoke.assert_not_called()

    assert "privacy_rejection" in result["messages"][0].content


def test_masking_failure_blocks_model(monkeypatch):
    privacy = CasePrivacy()
    model = RecordingModel()

    def fail(_):
        raise PrivacyError("PII masking failed")

    monkeypatch.setattr(
        privacy,
        "mask",
        fail,
    )

    state = {
        "alert_id": 1,
        "messages": [HumanMessage(content="Sensitive information")],
        "steps_taken": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
    }

    with pytest.raises(PrivacyError):
        investigate(
            state,
            model,
            "System prompt",
            privacy,
        )

    assert model.requests == []


@pytest.mark.parametrize(
    "phone",
    [
        "+1-495-452-3141x6865",
        "(495) 452-3141 ext. 6865",
        "495-452-3141 extension 6865",
        "495.452.3141 x6865",
    ],
)
def test_phone_extensions_are_fully_masked(phone):
    privacy = CasePrivacy()

    safe = privacy.mask_text(f"Customer phone: {phone}")

    assert phone not in safe
    assert "6865" not in safe
    assert "[REDACTED_PII]" in safe
