#!/usr/bin/env python3
"""Fleet v2 document validation and v1 compatibility."""
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLEET_STATE = ROOT / "scripts" / "fleet_state.py"
SCHEMA = ROOT / "schemas" / "mission-fleet.schema.json"
MISSION_FLEET = ROOT / "docs/missions/20261014-2a-foundation/fleet.json"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(FLEET_STATE), *map(str, args)], text=True,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def expect_error(proc, message):
    expected = f"ERROR: {message}"
    if proc.returncode == 0 or expected not in proc.stderr:
        raise AssertionError(f"expected {expected!r}, got rc={proc.returncode}, stderr={proc.stderr!r}")
    if "Traceback" in proc.stderr:
        raise AssertionError(f"unexpected traceback: {proc.stderr}")


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def good_v2():
    return {
        "schema_version": 2,
        "mission": {"path": "docs/missions/fixture"},
        "inventory": {"sha256": "3e8ced085f969e5108a223d7572a4c1b23076c1c942f3bcaab44b2373caa961b", "probed_at": "2026-10-14T15:00:44Z"},
        "approval": {"status": "approved", "approved_by": "test", "approved_at": "2026-10-14T15:25:56Z"},
        "policy": {"billing_classes": ["included"], "fast": False, "no_zdr": "allow"},
        "seats": {
            "codex.economy": {"family": "luna", "effort": "medium", "speed": "unknown", "doors": ["codex"]},
            "cursor.economy": {"family": "composer", "effort": "medium", "speed": "standard", "doors": ["cursor-composer"]},
        },
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        good = d / "good-v2.json"
        write(good, good_v2())
        assert run_cli("validate-fleet", good).returncode == 0
        assert run_cli("validate-fleet", MISSION_FLEET).returncode == 0

        def invalid(label, mutate, message):
            value = copy.deepcopy(good_v2())
            mutate(value)
            path = d / f"{label}.json"
            write(path, value)
            expect_error(run_cli("validate-fleet", path), message)

        invalid("unknown-door", lambda x: x["seats"]["codex.economy"].update(doors=["not-a-door"]), "fleet.seats.codex.economy unknown door 'not-a-door'")
        invalid("empty-doors", lambda x: x["seats"]["codex.economy"].update(doors=[]), "fleet.seats.codex.economy.doors must be a non-empty array")
        invalid("duplicate-doors", lambda x: x["seats"]["codex.economy"].update(doors=["codex", "codex"]), "fleet.seats.codex.economy.doors must be distinct")
        invalid("bad-billing", lambda x: x["policy"].update(billing_classes=["included", "credit"]), "fleet.policy.billing_classes invalid")
        invalid("empty-billing", lambda x: x["policy"].update(billing_classes=[]), "fleet.policy.billing_classes must be a non-empty array")
        invalid("duplicate-billing", lambda x: x["policy"].update(billing_classes=["included", "included"]), "fleet.policy.billing_classes must be distinct")
        invalid("bad-fast", lambda x: x["policy"].update(fast="yes"), "fleet.policy.fast must be boolean")
        invalid("bad-no-zdr", lambda x: x["policy"].update(no_zdr="maybe"), "fleet.policy.no_zdr invalid")
        invalid("extra-policy", lambda x: x["policy"].update(extra=True), "fleet.policy has missing or extra fields")
        invalid("extra-seat", lambda x: x["seats"]["codex.economy"].update(provider="codex"), "fleet.seats.codex.economy has missing or extra fields")
        invalid("empty-seats", lambda x: x.update(seats={}), "fleet requires seats")
        invalid("draft-approval", lambda x: x["approval"].update(status="draft"), "fleet is not approved")
        invalid("bad-effort", lambda x: x["seats"]["codex.economy"].update(effort="max"), "fleet.seats.codex.economy effort unsupported for door 'codex'")
        invalid("bad-speed", lambda x: x["seats"]["codex.economy"].update(speed="fast"), "fleet.seats.codex.economy speed unsupported for door 'codex'")
        invalid("version-three", lambda x: x.update(schema_version=3), "fleet schema_version must be 1 or 2")
        invalid("version-string", lambda x: x.update(schema_version="2"), "fleet schema_version must be 1 or 2")
        invalid("version-missing", lambda x: x.pop("schema_version"), "fleet schema_version must be 1 or 2")
        invalid("nontext-billing", lambda x: x["policy"].update(billing_classes=[["included"]]), "fleet.policy.billing_classes entries must be non-empty text")
        invalid("nontext-door", lambda x: x["seats"]["codex.economy"].update(doors=[["codex"]]), "fleet.seats.codex.economy.doors entries must be non-empty text")

        non_object = d / "non-object.json"
        non_object.write_text("[]\n")
        expect_error(run_cli("validate-fleet", non_object), "fleet must be an object")

        resolve = run_cli("resolve", "--fleet", good, "--seat", "codex.economy")
        expect_error(resolve, "fleet v2 is not resolvable yet")

        spec = importlib.util.find_spec("jsonschema")
        if spec is None:
            print("SKIP schema/code agreement: jsonschema is not installed")
        else:
            import jsonschema
            validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text()))
            for document in (good_v2(),):
                path = d / "schema-check.json"
                write(path, document)
                code_ok = run_cli("validate-fleet", path).returncode == 0
                schema_ok = validator.is_valid(document)
                assert code_ok == schema_ok, (code_ok, schema_ok, document)

    print("fleet v2 validation tests passed")


if __name__ == "__main__":
    main()
