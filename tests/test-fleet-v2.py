#!/usr/bin/env python3
"""Fleet v2 document validation and v1 compatibility."""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLEET_STATE = ROOT / "scripts" / "fleet_state.py"
MISSION_FLEET = ROOT / "docs/missions/20261014-2a-foundation/fleet.json"


def run_validate(path, ok=True):
    proc = subprocess.run(
        [sys.executable, str(FLEET_STATE), "validate-fleet", str(path)],
        text=True,
        capture_output=True,
        env={**dict(__import__("os").environ), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if ok and proc.returncode != 0:
        raise AssertionError(f"expected success for {path}: {proc.stderr}")
    if not ok and proc.returncode == 0:
        raise AssertionError(f"expected failure for {path}")
    return proc


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def good_v2():
    return {
        "schema_version": 2,
        "mission": {"path": "docs/missions/fixture"},
        "inventory": {
            "sha256": "3e8ced085f969e5108a223d7572a4c1b23076c1c942f3bcaab44b2373caa961b",
            "probed_at": "2026-10-14T15:00:44Z",
        },
        "approval": {
            "status": "approved",
            "approved_by": "test",
            "approved_at": "2026-10-14T15:25:56Z",
        },
        "policy": {
            "billing_classes": ["included"],
            "fast": False,
            "no_zdr": "allow",
        },
        "seats": {
            "codex.economy": {
                "family": "luna",
                "effort": "medium",
                "speed": "unknown",
                "doors": ["codex"],
            },
            "cursor.economy": {
                "family": "composer",
                "effort": "medium",
                "speed": "standard",
                "doors": ["cursor-composer"],
            },
        },
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        good = d / "good-v2.json"
        write(good, good_v2())
        run_validate(good)

        run_validate(MISSION_FLEET)

        base = good_v2()

        unknown = copy.deepcopy(base)
        unknown["seats"]["codex.economy"]["doors"] = ["not-a-door"]
        bad = d / "unknown-door.json"
        write(bad, unknown)
        run_validate(bad, ok=False)

        empty_doors = copy.deepcopy(base)
        empty_doors["seats"]["codex.economy"]["doors"] = []
        write(d / "empty-doors.json", empty_doors)
        run_validate(d / "empty-doors.json", ok=False)

        bad_billing = copy.deepcopy(base)
        bad_billing["policy"]["billing_classes"] = ["included", "credit"]
        write(d / "bad-billing.json", bad_billing)
        run_validate(d / "bad-billing.json", ok=False)

        bad_fast = copy.deepcopy(base)
        bad_fast["policy"]["fast"] = "yes"
        write(d / "bad-fast.json", bad_fast)
        run_validate(d / "bad-fast.json", ok=False)

        bad_effort = copy.deepcopy(base)
        bad_effort["seats"]["codex.economy"]["speed"] = "fast"
        write(d / "bad-effort.json", bad_effort)
        run_validate(d / "bad-effort.json", ok=False)

    print("fleet v2 validation tests passed")


if __name__ == "__main__":
    main()
