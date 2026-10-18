#!/usr/bin/env python3
"""The one run-id rule shared by every harness CLI: a canonical lowercase RFC 4122 UUID, versions 1-8."""
import re
import sys
import uuid

# Shape only, for privacy scans of free text. It never decides whether a run id is valid.
UUID_SHAPE = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
MESSAGE = "run_id must be a canonical UUID"


def validate_run_id(value):
    """Return value unchanged when it is a canonical run id, else raise ValueError.

    Call it before the value reaches any path. The message never echoes the value.
    """
    if not isinstance(value, str):
        raise ValueError(MESSAGE)
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        raise ValueError(MESSAGE) from None
    if (parsed.int == 0 or parsed.variant != uuid.RFC_4122
            or parsed.version not in range(1, 9) or str(parsed) != value):
        raise ValueError(MESSAGE)
    return value


def main(argv):
    """CLI: run_id.py check <value>; exit 0 when canonical, else 2 without echoing the value."""
    if len(argv) != 2 or argv[0] != "check":
        print("Usage: run_id.py check <run-id>", file=sys.stderr)
        return 2
    try:
        validate_run_id(argv[1])
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
