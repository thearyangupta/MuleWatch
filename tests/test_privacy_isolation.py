from unittest.mock import patch

import pytest

from agent.pii import CasePrivacy, PrivacyError


def test_account_alias_is_not_resolvable_in_another_context():
    first = CasePrivacy()
    second = CasePrivacy()

    alias = first.alias("ACCOUNT_PRIVATE_A", "account")

    assert first.resolve_account(alias) == "ACCOUNT_PRIVATE_A"

    with pytest.raises(PrivacyError):
        second.resolve_account(alias)


def test_customer_alias_mappings_are_independent():
    first = CasePrivacy()
    second = CasePrivacy()

    assert first.alias("CUSTOMER_A") == "CUST_001"
    assert second.alias("CUSTOMER_B") == "CUST_001"

    assert first.identities != second.identities


def test_fresh_graph_build_creates_fresh_privacy_context():
    from agent.graph import build_graph

    created = []
    real_privacy = CasePrivacy

    def tracked_privacy():
        context = real_privacy()
        created.append(context)
        return context

    with patch("agent.graph.CasePrivacy", side_effect=tracked_privacy):
        build_graph(model=object(), report_model=object())
        build_graph(model=object(), report_model=object())

    assert len(created) == 2
    assert created[0] is not created[1]

    created[0].alias("ACCOUNT_PRIVATE_A", "account")

    with pytest.raises(PrivacyError):
        created[1].resolve_account("ACC_001")
