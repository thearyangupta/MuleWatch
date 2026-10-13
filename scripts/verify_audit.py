"""Verify MuleWatch's complete audit hash chain."""

import sys

from agent.audit import verify_audit_chain


def main() -> int:
    valid, message = verify_audit_chain()

    if valid:
        print(f"PASS: {message}")
        return 0

    print(f"FAIL: {message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
