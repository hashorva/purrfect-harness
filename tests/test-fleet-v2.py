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
            "codex.economy": {"family": "luna", "effort": "medium", "speed": "unknown", "doors": ["codex"], "approved_resolution": {"provider": "codex", "model": "gpt-5.6-luna", "effort": "medium", "speed": "unknown"}},
            "cursor.economy": {"family": "composer", "effort": "medium", "speed": "standard", "doors": ["cursor-composer"], "approved_resolution": {"provider": "cursor", "model": "composer-2.5", "effort": "medium", "speed": "standard"}},
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
    provider = "cursor" if doors[0].startswith("cursor") else "claude" if doors[0].startswith("claude") else "codex"
    model = {"luna": "gpt-5.6-luna", "terra": "gpt-5.6-terra", "composer": "composer-2.5", "grok": "grok-4.7-high", "opus": "opus"}.get(family, "fixture-model")
    return {"family": family, "effort": effort, "speed": speed, "doors": doors,
            "approved_resolution": {"provider": provider, "model": model, "effort": effort, "speed": speed}}


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
    # a healthy first door with no model of the family falls through to the next door
    no_family_on_first = inventory({"claude": ["opus"], "codex": ["gpt-5.6-luna", "gpt-5.7-luna"]})
    expect(pick(["claude-alt", "codex"], inventory_doc=no_family_on_first), "codex", "gpt-5.7-luna")
    # a -fast model is never chosen with fast false, even when it is the newest
    expect(pick(["cursor-grok"], family="grok", effort="high", speed="standard"), "cursor-grok", "grok-4.7-high")
    expect(pick(["cursor-grok"], family="grok", effort="high", speed="fast", fast=True), "cursor-grok", "grok-4.8-high-fast")
    # mission fast:true does not let a standard seat pick -fast names from inventory
    grok_both = inventory({"agent": ["grok-4.8-high-fast", "grok-4.8-high"]})
    expect(pick(["cursor-grok"], family="grok", effort="high", speed="standard", fast=True, inventory_doc=grok_both), "cursor-grok", "grok-4.8-high")
    grok_fast_only = inventory({"agent": ["grok-4.8-high-fast"]})
    standard_under_fast = pick(["cursor-grok"], family="grok", effort="high", speed="standard", fast=True, inventory_doc=grok_fast_only)
    assert (standard_under_fast["model"], standard_under_fast["source"]) == (None, "unavailable"), standard_under_fast
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

    fast_off = good_v2()
    fast_off["seats"]["cursor.economy"] = seat("composer", ["cursor-composer"], speed="fast")
    fast_off_path = d / "resolve-fast-off.json"
    write(fast_off_path, fast_off)
    expect_error(
        run_cli("resolve-v2", "--fleet", fast_off_path, "--seat", "cursor.economy", "--inventory", inventory_path),
        "fleet.seats.cursor.economy speed fast requires fleet.policy.fast",
    )
    bad_family = good_v2()
    bad_family["seats"]["codex.economy"] = seat("composer", ["codex"])
    bad_family_path = d / "resolve-bad-family.json"
    write(bad_family_path, bad_family)
    expect_error(
        run_cli("resolve-v2", "--fleet", bad_family_path, "--seat", "codex.economy", "--inventory", inventory_path),
        "fleet.seats.codex.economy family 'composer' unsupported for its doors",
    )
    ref_inv = inventory({"codex": ["gpt-5.7-luna"]})
    try:
        fleet_state.resolve_v2(fast_off, "cursor.economy", registry, ref_inv)
        raise AssertionError("resolve_v2 should refuse fast seat when policy.fast is false")
    except fleet_state.PolicyError as exc:
        assert str(exc) == "fleet.seats.cursor.economy speed fast requires fleet.policy.fast"
    try:
        fleet_state.resolve_v2(bad_family, "codex.economy", registry, ref_inv)
        raise AssertionError("resolve_v2 should refuse unsupported family")
    except fleet_state.PolicyError as exc:
        assert str(exc) == "fleet.seats.codex.economy family 'composer' unsupported for its doors"

    s1_fleet = fleet_with({"test.grok": seat("grok", ["cursor-grok"], effort="high", speed="standard")}, fast=True)
    s1_fleet_path = d / "resolve-s1-fleet.json"
    s1_inv_path = d / "resolve-s1-inventory.json"
    write(s1_fleet_path, s1_fleet)
    write(s1_inv_path, grok_both)
    s1_ok = run_cli("resolve-v2", "--fleet", s1_fleet_path, "--seat", "test.grok", "--inventory", s1_inv_path)
    assert s1_ok.returncode == 0 and json.loads(s1_ok.stdout)["model"] == "grok-4.8-high", (s1_ok.returncode, s1_ok.stdout, s1_ok.stderr)
    write(s1_inv_path, grok_fast_only)
    s1_gone = run_cli("resolve-v2", "--fleet", s1_fleet_path, "--seat", "test.grok", "--inventory", s1_inv_path)
    assert s1_gone.returncode == 1 and json.loads(s1_gone.stdout)["source"] == "unavailable", (s1_gone.returncode, s1_gone.stdout)


def schema_node(schema, node):
    """Follow local $ref links so the key check reads the declared shape, not the pointer."""
    while "$ref" in node:
        assert node["$ref"].startswith("#/$defs/"), node
        node = schema["$defs"][node["$ref"].split("/")[-1]]
    return node


def assert_keys_agree(schema, node, value, label):
    """Dependency-free agreement: every key the code writes is declared, and every required key is written."""
    node = schema_node(schema, node)
    declared = set(node["properties"])
    written = set(value)
    assert written <= declared, (label, "written but undeclared", sorted(written - declared))
    assert set(node.get("required", [])) <= written, (label, "required but not written", sorted(set(node.get("required", [])) - written))


def check_v2_schema_agreement(frozen):
    """The v2 schema must declare every key that freeze-v2 writes, at every nesting level it covers."""
    schema = json.loads(SCHEMA.read_text())
    fleet_node = schema["$defs"]["fleetV2"]
    assert_keys_agree(schema, fleet_node, frozen, "fleet")
    for name in ("mission", "inventory", "approval", "policy"):
        assert_keys_agree(schema, fleet_node["properties"][name], frozen[name], name)
    seat_node = schema_node(schema, fleet_node["properties"]["seats"]["additionalProperties"])
    for name, seat in frozen["seats"].items():
        assert_keys_agree(schema, seat_node, seat, "seat " + name)
        assert_keys_agree(schema, seat_node["properties"]["approved_resolution"], seat["approved_resolution"], "approved_resolution " + name)


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

        resolve_inventory = d / "resolve-inventory.json"
        write(resolve_inventory, inventory({"codex": ["gpt-5.7-luna"]}))
        resolve = run_cli("resolve", "--fleet", good, "--seat", "codex.economy",
                          "--inventory", resolve_inventory, "--root", d)
        assert resolve.returncode == 0 and json.loads(resolve.stdout)["model"] == "gpt-5.7-luna", (resolve.returncode, resolve.stdout, resolve.stderr)

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

        # `resolve` is the launcher entry point: drift is appended once on a
        # changed live resolution, then remains quiet for the same binding.
        drift_fleet = fleet_with({"codex.economy": seat("luna", ["codex"])})
        drift_fleet_path = d / "docs/missions/fixture/fleet.json"
        (d / ".tasks/drift/fixture.jsonl").unlink(missing_ok=True)
        drift_fleet_path.parent.mkdir(parents=True)
        write(drift_fleet_path, drift_fleet)
        drift_inventory_path = d / ".tasks/fleet-inventory.json"
        drift_inventory_path.parent.mkdir(parents=True, exist_ok=True)
        live_inventory = inventory({"codex": ["gpt-6-luna"]})
        drift_inventory_path.write_text(fleet_state.canonical(live_inventory))
        resolve_args = ("resolve", "--fleet", drift_fleet_path, "--seat", "codex.economy",
                        "--mission-path", "docs/missions/fixture", "--inventory", drift_inventory_path, "--root", d)
        for _ in range(3):
            result = run_cli(*resolve_args)
            assert result.returncode == 0, (result.returncode, result.stderr)
            assert json.loads(result.stdout)["model"] == "gpt-6-luna"
        drift_log = d / ".tasks/drift/fixture.jsonl"
        events = [json.loads(line) for line in drift_log.read_text().splitlines()]
        assert len(events) == 1 and events[0]["from"]["model"] == "gpt-5.6-luna" and events[0]["to"]["model"] == "gpt-6-luna", events
        assert set(events[0]) == {"at", "mission", "seat", "from", "to", "inventory_sha256"}

        blocked_root = d / "blocked"
        blocked_fleet_path = blocked_root / "docs/missions/fixture/fleet.json"
        blocked_fleet_path.parent.mkdir(parents=True)
        write(blocked_fleet_path, drift_fleet)
        blocked_inventory = blocked_root / ".tasks/fleet-inventory.json"
        blocked_inventory.parent.mkdir(parents=True)
        blocked_inventory.write_text(fleet_state.canonical(live_inventory))
        blocked_dir = blocked_root / ".tasks/drift"
        blocked_dir.mkdir()
        blocked_dir.chmod(0o500)
        blocked = run_cli("resolve", "--fleet", blocked_fleet_path, "--seat", "codex.economy",
                          "--mission-path", "docs/missions/fixture", "--inventory", blocked_inventory, "--root", blocked_root)
        assert blocked.returncode != 0 and "ERROR: drift event could not be written" in blocked.stderr, (blocked.returncode, blocked.stderr)
        assert not list((blocked_root / ".tasks").glob("specs/*"))
        blocked_dir.chmod(0o700)

        v1_root = d / "v1-root"
        v1_root.mkdir()
        v1_doc = json.loads(MISSION_FLEET.read_text())
        v1_doc["mission"]["path"] = "docs/missions/fixture"
        v1_path = v1_root / "fleet.json"
        write(v1_path, v1_doc)
        v1_resolve = run_cli("resolve", "--fleet", v1_path, "--seat", "codex.economy",
                             "--mission-path", "docs/missions/fixture", "--root", v1_root)
        assert v1_resolve.returncode == 0, v1_resolve.stderr
        assert not (v1_root / ".tasks/drift/fixture.jsonl").exists()

        freeze_root = d / "freeze-root"
        freeze_mission = freeze_root / "docs/missions/frozen"
        freeze_mission.mkdir(parents=True)
        freeze_inventory_path = d / "freeze-inventory.json"
        freeze_inventory = inventory({"codex": ["gpt-5.6-luna", "gpt-5.7-luna"]})
        write(freeze_inventory_path, freeze_inventory)
        bindings_path = d / "freeze-bindings.json"
        write(bindings_path, {"codex.economy": {"family": "luna", "effort": "medium", "speed": "unknown", "doors": ["codex"]}})
        policy_path = d / "freeze-policy.json"
        write(policy_path, {"billing_classes": ["included"], "fast": False, "no_zdr": "allow"})
        frozen = run_cli("freeze-v2", "--mission-dir", freeze_mission, "--inventory", freeze_inventory_path,
                         "--bindings", bindings_path, "--policy", policy_path, "--approved-by", "test",
                         "--approved-at", NOW)
        assert frozen.returncode == 0, frozen.stderr
        frozen_doc = json.loads(frozen.stdout)
        assert frozen_doc["seats"]["codex.economy"]["approved_resolution"] == {
            "provider": "codex", "model": "gpt-5.7-luna", "effort": "medium", "speed": "unknown"}
        assert run_cli("validate-fleet", freeze_mission / "fleet.json").returncode == 0
        check_v2_schema_agreement(frozen_doc)

    print("fleet v2 validation tests passed")


if __name__ == "__main__":
    main()
