"""Validate frozen Week 5 Day 1 evidence and unreviewed golden-set draft."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
payload = json.loads((ROOT / "golden_set.yaml").read_text(encoding="utf-8"))
cases = payload["cases"]
assert len(cases) == 35, f"Expected 35 cases, got {len(cases)}"
assert len({c["case_id"] for c in cases}) == 35, "Duplicate case ID"
allowed = {"CLOSE_NO_ACTION", "ENHANCED_MONITORING", "ESCALATE_TO_INVESTIGATOR"}
for c in cases:
    assert c["source"] in {"database", "constructed"}
    assert set(c["acceptable_actions"]) <= allowed
    assert c["risk_band"] in (None, "LOW", "MEDIUM", "HIGH")
    assert c["label_status"] in {"PENDING_HUMAN_REVIEW", "REVIEWED"}
    if c["scored"]:
        assert (
            c["label_status"] == "REVIEWED"
            and c["acceptable_actions"]
            and c["risk_band"]
            and c["reviewer"]
        )
        assert c["required_evidence"] and c["review_notes"].strip()
manifest = json.loads((ROOT / "snapshot/manifest.json").read_text(encoding="utf-8"))
for name, expected in manifest["files_sha256"].items():
    actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    assert actual == expected, f"Snapshot modified: {name}"
assert sum(c["source"] == "database" for c in cases) == 30
assert sum(c["source"] == "constructed" for c in cases) == 5
print("PASS: 35 distinct cases, schema checks, snapshot checksums")
print("Reviewed/scored:", sum(c["scored"] for c in cases), "/", len(cases))
print(
    "NOTE: No human labels yet. Snapshot is an offline evidence "
    "fixture, not a PostgreSQL restore."
)
