"""PII masking and case-scoped pseudonymisation."""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

for logger_name in (
    "presidio-analyzer",
    "presidio-anonymizer",
    "spacy",
):
    logging.getLogger(logger_name).disabled = True

_PHONE_WITH_EXTENSION = re.compile(
    r"(?<![\w])"
    r"(?:\+?1[\s.\-]?)?"
    r"(?:\(\d{3}\)|\d{3})[\s.\-]?"
    r"\d{3}[\s.\-]?\d{4}"
    r"(?:\s*(?:ext\.?|extension|x|#)\s*\d+)"
    r"(?!\w)",
    re.IGNORECASE,
)


class PrivacyError(RuntimeError):
    pass


@dataclass
class CasePrivacy:
    """Private mapping; never place this object in LangGraph state."""

    analyzer: AnalyzerEngine = field(default_factory=AnalyzerEngine)
    anonymizer: AnonymizerEngine = field(default_factory=AnonymizerEngine)
    identities: dict[str, str] = field(default_factory=dict)
    reverse: dict[str, str] = field(default_factory=dict)
    next_customer: int = 1
    next_account: int = 1

    def alias(self, value: Any, kind: str = "customer") -> str:
        raw = str(value)
        if raw in self.reverse:
            return raw

        key = f"{kind}:{raw}"

        if key not in self.identities:
            if kind == "account":
                token = f"ACC_{self.next_account:03d}"
                self.next_account += 1
            else:
                token = f"CUST_{self.next_customer:03d}"
                self.next_customer += 1

            self.identities[key] = token
            self.reverse[token] = raw

        return self.identities[key]

    def resolve_account(self, alias: str) -> str:
        """Only approved, previously registered aliases can be resolved."""
        if not alias.startswith("ACC_"):
            raise PrivacyError("Unrecognised account alias")

        if alias not in self.reverse:
            raise PrivacyError("Unknown account alias")

        return self.reverse[alias]

    def mask_text(self, text: str) -> str:
        if not text:
            return text

        try:
            for key, token in sorted(
                self.identities.items(),
                key=lambda item: len(item[0].split(":", 1)[1]),
                reverse=True,
            ):
                original = key.split(":", 1)[1]
                if original:
                    text = text.replace(original, token)

            text = _PHONE_WITH_EXTENSION.sub("[REDACTED_PII]", text)

            results = self.analyzer.analyze(
                text=text,
                language="en",
                entities=[
                    "PERSON",
                    "EMAIL_ADDRESS",
                    "PHONE_NUMBER",
                    "LOCATION",
                ],
            )
            if results:
                text = self.anonymizer.anonymize(
                    text=text,
                    analyzer_results=results,
                    operators={
                        "DEFAULT": OperatorConfig(
                            "replace",
                            {"new_value": "[REDACTED_PII]"},
                        )
                    },
                ).text

            return text

        except Exception as exc:
            raise PrivacyError("PII masking failed") from exc

    def mask(self, value: Any) -> Any:
        if isinstance(value, dict):
            result = {}

            for key, item in value.items():
                name = key.lower()

                if item is None:
                    result[key] = None

                elif name in {
                    "name",
                    "full_name",
                    "first_name",
                    "last_name",
                    "customer_id",
                }:
                    result[key] = self.alias(item, "customer")

                elif name in {
                    "account_id",
                    "sender_account_id",
                    "receiver_account_id",
                    "counterparty_account_id",
                }:
                    result[key] = self.alias(item, "account")

                elif name in {
                    "email",
                    "phone",
                    "address",
                }:
                    result[key] = "[REDACTED_PII]"

                else:
                    result[key] = self.mask(item)

            return result

        if isinstance(value, list):
            return [self.mask(item) for item in value]

        if isinstance(value, tuple):
            return [self.mask(item) for item in value]

        if isinstance(value, str):
            return self.mask_text(value)

        return value
