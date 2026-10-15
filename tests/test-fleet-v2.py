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

sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
import fleet_state  # noqa: E402
from harness_registry import load_registry  # noqa: E402

NOW = "2026-10-14T15:00:44Z"


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


def door(provider, billing="included", no_zdr=False):
    return {"provider": provider, "billing_class": billing, "pool": "fixture", "no_zdr": no_zdr, "priority": 9}


def fixture_registry():
    # The real doors are all included and allow ZDR; fixture doors cover the other policy paths.
    registry = copy.deepcopy(load_registry())
    registry["doors"].update({
        "credits-codex": door("codex", "credits"),
        "api-codex": door("codex", "api"),
        "nozdr-codex": door("codex", no_zdr=True),
        "claude-alt": door("claude"),
    })
    return registry


def inventory(models=None, failed=()):
    """A valid inventory; `models` maps an inventory key to its observed names (claude: aliases)."""
    models = models or {}
    providers = {}
    for key in fleet_state.PROVIDERS:
        base = {"probed_at": NOW, "capabilities": fleet_state.CAPABILITIES[key]}
        if key in failed:
            providers[key] = {**base, "status": "failure", "path": f"/bin/{key}", "error": "fixture failure"}
        elif key == "claude":
            providers[key] = {**base, "status": "success", "path": "/bin/claude", "aliases": models.get(key, ["opus"]), "observed_models": []}
        else:
            providers[key] = {**base, "status": "success", "path": f"/bin/{key}", "aliases": [], "observed_models": models.get(key, ["fixture-1.0-low"])}
    doc = {"schema_version": 1, "probed_at": NOW, "providers": providers, "last_good": {}, "seats": fleet_state.make_seats(providers, {})}
    fleet_state.validate_inventory(doc)
    return doc


def fleet_with(seats, fast=False, billing=("included",), no_zdr="allow"):
    doc = good_v2()
    doc["policy"] = {"billing_classes": list(billing), "fast": fast, "no_zdr": no_zdr}
    doc["seats"] = seats
    return doc


def seat(family, doors, effort="medium", speed="unknown"):
    return {"family": family, "effort": effort, "speed": speed, "doors": doors}


def resolver_checks(d):
    registry = fixture_registry()
    inv = inventory({"codex": ["gpt-5.6-luna", "gpt-5.7-luna"], "agent": ["grok-4.8-high-fast", "grok-4.7-high"], "claude": ["luna-fixture-2.0"]})

    def pick(doors, family="luna", effort="medium", speed="unknown", inventory_doc=inv, **policy):
        return fleet_state.resolve_v2(fleet_with({"s": seat(family, doors, effort, speed)}, **policy), "s", registry, inventory_doc)

    def expect(result, door_name, model, source="observed"):
        got = (result["door"], result["model"], result["source"])
        assert got == (door_name, model, source), (got, result)

    expect(pick(["codex", "api-codex"]), "codex", "gpt-5.7-luna")
    # credits and api doors are skipped unless the policy lists their billing class
    expect(pick(["credits-codex", "codex"]), "codex", "gpt-5.7-luna")
    expect(pick(["credits-codex", "codex"], billing=("included", "credits")), "credits-codex", "gpt-5.7-luna")
    expect(pick(["api-codex", "codex"]), "codex", "gpt-5.7-luna")
    expect(pick(["api-codex", "codex"], billing=("included", "api")), "api-codex", "gpt-5.7-luna")
    # no_zdr doors are skipped only when the policy forbids them
    expect(pick(["nozdr-codex", "codex"], no_zdr="forbid"), "codex", "gpt-5.7-luna")
    expect(pick(["nozdr-codex", "codex"]), "nozdr-codex", "gpt-5.7-luna")
    # an unhealthy first door falls through to the next included door
    expect(pick(["claude-alt", "codex"]), "claude-alt", "luna-fixture-2.0", source="alias")
    unhealthy = inventory({"codex": ["gpt-5.6-luna", "gpt-5.7-luna"], "claude": ["luna-fixture-2.0"]}, failed=("claude",))
    expect(pick(["claude-alt", "codex"], inventory_doc=unhealthy), "codex", "gpt-5.7-luna")
    # a -fast model is never chosen with fast false, even when it is the newest
    expect(pick(["cursor-grok"], family="grok", effort="high", speed="standard"), "cursor-grok", "grok-4.7-high")
    expect(pick(["cursor-grok"], family="grok", effort="high", speed="fast", fast=True), "cursor-grok", "grok-4.8-high-fast")
    # an inventory of only encoded names yields the plain base, re-encoded with the seat effort
    encoded = inventory({"agent": ["grok-4.7-low", "grok-4.6-high"]})
    expect(pick(["cursor-grok"], family="grok", effort="medium", speed="standard", inventory_doc=encoded), "cursor-grok", "grok-4.7-medium")
    # an absent family stays unavailable, never a guessed id
    absent = pick(["codex"], family="terra")
    assert (absent["model"], absent["door"], absent["source"]) == (None, None, "unavailable"), absent

    # CLI at the real entry point, with the real registry
    fleet_doc = good_v2()
    fleet_doc["seats"]["codex.premium"] = seat("terra", ["codex"])
    fleet_path = d / "resolver-fleet.json"
    inventory_path = d / "resolver-inventory.json"
    write(fleet_path, fleet_doc)
    write(inventory_path, inventory({"codex": ["gpt-5.7-luna"]}))
    ok = run_cli("resolve-v2", "--fleet", fleet_path, "--seat", "codex.economy", "--inventory", inventory_path)
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout)["model"] == "gpt-5.7-luna", ok.stdout
    gone = run_cli("resolve-v2", "--fleet", fleet_path, "--seat", "codex.premium", "--inventory", inventory_path)
    assert gone.returncode == 1 and json.loads(gone.stdout)["source"] == "unavailable", (gone.returncode, gone.stdout)
    expect_error(run_cli("resolve-v2", "--fleet", fleet_path, "--seat", "missing", "--inventory", inventory_path), "fleet seat not found")


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
        invalid("fast-seat-policy-off", lambda x: x["seats"]["cursor.economy"].update(speed="fast"), "fleet.seats.cursor.economy speed fast requires fleet.policy.fast")
        invalid("family-unsupported", lambda x: x["seats"]["codex.economy"].update(family="composer"), "fleet.seats.codex.economy family 'composer' unsupported for its doors")

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

        resolver_checks(d)

    print("fleet v2 validation tests passed")


if __name__ == "__main__":
    main()
