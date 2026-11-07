from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from pipeline import validate

RUN_DATE = date(2026, 1, 1)


def test_quality_gate_preserves_quarantine_before_failure(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection

    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(validate.psycopg, "connect", connect)

    staged = pd.DataFrame({"id": [1, 2]})
    clean = pd.DataFrame({"id": [1]})
    quarantined = pd.DataFrame({"id": [2]})

    monkeypatch.setattr(
        validate,
        "load_staged_transactions",
        lambda connection, run_date: staged,
    )
    monkeypatch.setattr(
        validate,
        "validate_transactions",
        lambda transactions, run_date: (clean, quarantined),
    )

    write_quarantine = MagicMock()
    upsert_clean = MagicMock()

    monkeypatch.setattr(validate, "write_quarantined_rows", write_quarantine)
    monkeypatch.setattr(validate, "upsert_clean_transactions", upsert_clean)

    with pytest.raises(ValueError, match="Quarantine rate"):
        validate.validate_staged_transactions(
            RUN_DATE,
            database_url="postgresql://unused",
        )

    write_quarantine.assert_called_once()
    connection.commit.assert_called_once()
    upsert_clean.assert_not_called()


def test_quality_gate_accepts_batch_below_threshold(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection

    monkeypatch.setattr(
        validate.psycopg,
        "connect",
        MagicMock(return_value=connection),
    )

    staged = pd.DataFrame({"id": list(range(100))})
    clean = pd.DataFrame({"id": list(range(96))})
    quarantined = pd.DataFrame({"id": list(range(4))})

    monkeypatch.setattr(
        validate,
        "load_staged_transactions",
        lambda connection, run_date: staged,
    )
    monkeypatch.setattr(
        validate,
        "validate_transactions",
        lambda transactions, run_date: (clean, quarantined),
    )

    write_quarantine = MagicMock()
    upsert_clean = MagicMock()

    monkeypatch.setattr(validate, "write_quarantined_rows", write_quarantine)
    monkeypatch.setattr(validate, "upsert_clean_transactions", upsert_clean)

    assert validate.validate_staged_transactions(
        RUN_DATE,
        database_url="postgresql://unused",
    ) == (96, 4)

    write_quarantine.assert_called_once()
    upsert_clean.assert_called_once()
