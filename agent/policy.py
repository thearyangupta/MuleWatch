import re

from pydantic import BaseModel, Field

from agent.report import CaseReport, RecommendedAction, RiskRating


class PolicyResult(BaseModel):
    passed: bool
    violations: list[str] = Field(default_factory=list)


GUILT_ASSERTIONS = (
    re.compile(
        r"\b(?:the\s+)?(?:customer|account\s+holder|person|user)"
        r"\s+(?:is|was)\s+(?:a\s+)?(?:criminal|fraudster|money\s+mule)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:guilty\s+of|committed)\s+(?:fraud|money\s+laundering)\b",
        re.IGNORECASE,
    ),
)

PROHIBITED_ENFORCEMENT = re.compile(
    r"\b(?:freeze|block|seize)\s+"
    r"(?:the\s+|this\s+|an?\s+)?"
    r"(?:account|funds|assets)\b",
    re.IGNORECASE,
)

PROTECTED_ATTRIBUTE_REASONING = re.compile(
    r"\b(?:because|due\s+to|based\s+on)\s+"
    r"(?:(?:of\s+)?(?:their|the\s+customer'?s)\s+)?"
    r"(?:race|religion|ethnicity|gender|nationality)\b",
    re.IGNORECASE,
)


def report_text(report: CaseReport) -> str:
    parts = [report.summary]

    parts.extend(finding.claim for finding in report.findings)

    for match in report.typology_matches:
        parts.append(match.explanation)

    return "\n".join(parts)


def validate_policy(report: CaseReport) -> PolicyResult:
    violations: list[str] = []

    text = report_text(report)

    if not report.findings and not report.typology_matches:
        violations.append(
            "Report must contain at least one cited finding or typology match."
        )

    if (
        report.risk_rating == RiskRating.HIGH
        and report.recommended_action == RecommendedAction.CLOSE_NO_ACTION
    ):
        violations.append("HIGH risk cannot recommend CLOSE_NO_ACTION.")

    if (
        report.confidence < 0.5
        and report.recommended_action == RecommendedAction.CLOSE_NO_ACTION
    ):
        violations.append("Low-confidence report cannot recommend closure.")

    if any(pattern.search(text) for pattern in GUILT_ASSERTIONS):
        violations.append("Report contains an unsupported criminal-guilt assertion.")

    if PROHIBITED_ENFORCEMENT.search(text):
        violations.append("Report contains prohibited account-enforcement language.")

    if PROTECTED_ATTRIBUTE_REASONING.search(text):
        violations.append("Report appears to rely on a protected attribute.")

    return PolicyResult(
        passed=not violations,
        violations=violations,
    )
