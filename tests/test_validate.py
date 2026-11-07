from datetime import date

import pandas as pd

from pipeline.validate import validate_transactions

RUN_DATE = date(2026, 1, 1)


def sample():
    return pd.DataFrame(
        {
            "source_transaction_id": ["tx-1", "tx-2"],
            "run_date": [RUN_DATE, RUN_DATE],
            "sender_account_id": ["A", "B"],
            "receiver_account_id": ["B", "C"],
            "transaction_type": ["TRANSFER", "PAYMENT"],
            "amount": [100.0, 200.0],
            "timestamp": [
                "2026-01-01T10:00:00Z",
                "2026-01-01T11:00:00Z",
            ],
            "is_fraud": [False, False],
        }
    )


def test_valid_transactions():
    clean, quarantine = validate_transactions(sample(), RUN_DATE)
    assert len(clean) == 2
    assert quarantine.empty


def test_negative_amount_quarantined():
    data = sample()
    data.loc[0, "amount"] = -100
    clean, quarantine = validate_transactions(data, RUN_DATE)
    assert len(clean) == 1
    assert "amount" in quarantine.iloc[0]["failure_reason"]


def test_duplicate_ids_quarantined():
    data = sample()
    data.loc[1, "source_transaction_id"] = "tx-1"
    clean, quarantine = validate_transactions(data, RUN_DATE)
    assert clean.empty
    assert len(quarantine) == 2
    assert quarantine["failure_reason"].str.contains("duplicate").all()


def test_same_sender_receiver_quarantined():
    data = sample()
    data.loc[0, "receiver_account_id"] = "A"
    clean, quarantine = validate_transactions(data, RUN_DATE)
    assert len(clean) == 1
    assert "sender and receiver" in quarantine.iloc[0]["failure_reason"]


def test_wrong_date_quarantined():
    data = sample()
    data.loc[0, "timestamp"] = "2026-01-02T10:00:00Z"
    clean, quarantine = validate_transactions(data, RUN_DATE)
    assert len(clean) == 1
    assert "run_date" in quarantine.iloc[0]["failure_reason"]


def test_unknown_transaction_type_quarantined():
    data = sample()
    data.loc[0, "transaction_type"] = "UNKNOWN"
    clean, quarantine = validate_transactions(data, RUN_DATE)
    assert len(clean) == 1
    assert "transaction_type" in quarantine.iloc[0]["failure_reason"]
