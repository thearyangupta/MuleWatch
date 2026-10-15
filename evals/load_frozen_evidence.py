import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / "snapshot"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_frozen_evidence():
    manifest = read_json(SNAPSHOT / "manifest.json")
    expected_hashes = manifest["files_sha256"]

    print("===== FROZEN EVIDENCE INTEGRITY =====")

    for relative_path, expected_hash in expected_hashes.items():
        path = ROOT / relative_path

        if not path.is_file():
            raise FileNotFoundError(f"Required frozen file missing: {relative_path}")

        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()

        if actual_hash != expected_hash:
            raise ValueError(
                f"Checksum mismatch: {relative_path}\n"
                f"Expected: {expected_hash}\n"
                f"Actual:   {actual_hash}"
            )

        print(f"PASS: {relative_path}")

    database = read_json(SNAPSHOT / "database_evidence.json")
    constructed = read_json(SNAPSHOT / "constructed_scenarios.json")

    database_cases = database["cases"]
    scenarios = constructed["scenarios"]

    if len(database_cases) != manifest["database_alert_count"]:
        raise ValueError("Database case count mismatch")

    if len(scenarios) != manifest["constructed_count"]:
        raise ValueError("Constructed case count mismatch")

    scenario_ids = [item["id"] for item in scenarios]

    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("Duplicate constructed scenario IDs")

    print("\nDatabase cases:", len(database_cases))
    print("Constructed scenarios:", len(scenarios))
    print("Total cases:", len(database_cases) + len(scenarios))
    print("PASS: Frozen evidence integrity verified")

    return database, constructed


if __name__ == "__main__":
    load_frozen_evidence()
