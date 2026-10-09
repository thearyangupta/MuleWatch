from agent.report import CaseReport


class CitationVerificationError(ValueError):
    """A report cites evidence that was not retrieved."""


def verify_report(
    report: CaseReport,
    evidence: list[dict],
) -> None:
    """Verify all evidence IDs and retrieved typology chunk IDs."""

    evidence_by_id = {
        item["evidence_id"]: item for item in evidence if item.get("evidence_id")
    }

    for finding in report.findings:
        for evidence_id in finding.evidence_ids:
            if evidence_id not in evidence_by_id:
                raise CitationVerificationError(f"Unknown evidence ID: {evidence_id}")

            item = evidence_by_id[evidence_id]

            if item.get("data", {}).get("ok") is False:
                raise CitationVerificationError(f"Failed evidence cited: {evidence_id}")

    for match in report.typology_matches:
        item = evidence_by_id.get(match.evidence_id)

        if item is None:
            raise CitationVerificationError(
                f"Unknown typology evidence: {match.evidence_id}"
            )

        if item.get("source") != "search_typologies":
            raise CitationVerificationError(
                f"Evidence is not a typology search: {match.evidence_id}"
            )

        if not item.get("data", {}).get("ok"):
            raise CitationVerificationError(
                f"Unsuccessful typology search: {match.evidence_id}"
            )

        valid_chunks = {
            str(chunk["chunk_id"])
            for chunk in item.get("data", {}).get("chunks", [])
            if chunk.get("chunk_id") is not None
        }

        for chunk_id in match.chunk_ids:
            if chunk_id not in valid_chunks:
                raise CitationVerificationError(f"Unknown typology chunk: {chunk_id}")
