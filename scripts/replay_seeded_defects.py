#!/usr/bin/env python3
"""Replay the F001 step 7 seeded defect cases and judge reviewer answers."""
import argparse, json, re, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import brain_prompt, observe_output, probe_seat, validate_verdict
from execute_provider import provider_contract
from execution_spec import CURRENT_PROVIDER_CONTRACT
SEAT_NAME = re.compile(r"[a-z]+(?:[._][a-z]+)?")
class ReplayError(Exception):
    pass
MISSION_2A = "docs/missions/20261014-2a-foundation"
REQUIRED_2A = "tests/fixtures/replay-seeded-defects/2a-seeded-calibration.jsonl"
CASES = (
    {"id": "A", "task": "T-043", "commit": "53fb0f5817aa94c8845e9811d29123afdff85dbb",
     "file": "scripts/verification_record.py", "planted": "marker pattern without re.M",
     "old": r're.compile(rb"^SKIP(?:PED)?\b", re.M)', "new": r're.compile(rb"^SKIP(?:PED)?\b")',
     "keywords": ("re.M", "MULTILINE")},
    {"id": "B", "task": "T-042", "commit": "0e3cebacc3123496f524202bd0cf14783012e69e",
     "file": "scripts/execution_runner.py", "planted": "git read without --no-replace-objects",
     "old": '["git", "--no-replace-objects", "-C", str(repo),', "new": '["git", "-C", str(repo),',
     "keywords": ("replace-objects", "replace objects")},
    {"id": "C", "task": "T-044", "commit": "eb7e8c7e61274c1eab37bff3571e485d9854e17d",
     "file": "scripts/ledger.py", "planted": "~name/ alternative removed from the sensitive-path rule",
     "old": r"|~[\w.-]*/|", "new": "|~/|", "keywords": ("~",)},
)
FAMILY_2A = {"grok-4.7-high": "grok", "gemini-4-argon-high (agy)": "argon"}
def required(path):
    found = {family: set() for family in FAMILY_2A.values()}
    cases = {case["id"]: case for case in CASES}
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
        except (ValueError, RecursionError) as exc: raise ReplayError(f"line {number}: not JSON") from exc
        if not isinstance(row, dict) or row.get("type") != "seeded-calibration":
            continue
        reviewer = row.get("reviewer")
        if reviewer not in FAMILY_2A:
            raise ReplayError(f"line {number}: unknown 2A reviewer")
        case_id = row.get("case")
        case = cases.get(case_id)
        if (case is None or row.get("task") != case["task"] or not isinstance(row.get("commit"), str)
                or len(row["commit"]) < 7 or not case["commit"].startswith(row["commit"])):
            raise ReplayError(f"line {number}: row does not match case {case_id}")
        if type(row.get("caught")) is not bool:
            raise ReplayError(f"line {number}: caught must be a bool")
        if row["caught"]:
            found[FAMILY_2A[reviewer]].add(case_id)
    return {family: sorted(ids) for family, ids in found.items()}
def plant(source, case, dest):
    dest = Path(dest)
    def git(args, subcommand):
        result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], stdin=subprocess.DEVNULL, capture_output=True)
        if result.returncode:
            raise ReplayError(f"case {case['id']}: git {subcommand} failed")
    git(["clone", "-q", "--no-checkout", str(source), str(dest)], "clone")
    git(["-C", str(dest), "checkout", "-q", "--detach", case["commit"]], "checkout")
    git(["-C", str(dest), "remote", "remove", "origin"], "remote remove")
    path = dest / case["file"]
    content = path.read_text(encoding="utf-8")
    count = content.count(case["old"])
    if count != 1:
        raise ReplayError(f"case {case['id']}: old text found {count} times")
    path.write_text(content.replace(case["old"], case["new"]), encoding="utf-8")
    git(["-C", str(dest), "-c", "user.name=replay", "-c", "user.email=replay@invalid", "-c", "commit.gpgsign=false", "commit", "-q", "--amend", "--no-edit", "-a"], "commit")
    return dest
def caught(provider, raw, case):
    answer = observe_output.final_answer(provider, raw)
    if not isinstance(answer, str):
        return False
    try:
        verdict = validate_verdict.extract_last_json_object(answer)
        if validate_verdict.validate(verdict, validate_verdict.read_json(Path(__file__).resolve().parent.parent / "schemas/review-verdict.schema.json")): return False
    except (ValueError, RecursionError, OSError): return False
    return (verdict.get("verdict") == "FAIL" and any(
        finding.get("severity") == "blocking"
        and Path(case["file"]).name in finding.get("text", "")
        and any(keyword in finding.get("text", "") for keyword in case["keywords"])
        for finding in verdict.get("findings", [])
    ))
def seat_binding(fleet_path, name, inventory):
    if not SEAT_NAME.fullmatch(name):
        raise ReplayError(f"invalid seat name {name}")
    try:
        data = json.loads(Path(fleet_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ReplayError(f"invalid fleet file: {exc}") from exc
    seats = data.get("seats")
    if not isinstance(seats, dict) or name not in seats:
        raise ReplayError(f"unknown seat {name}")
    seat, family = seats[name], seats[name].get("family")
    if not isinstance(family, str) or not family:
        raise ReplayError(f"seat {name} has no family")
    if data.get("schema_version") == 2:
        try:
            provider, model, effort, speed = probe_seat._seat_v2(data, name, Path(inventory))
        except ValueError as exc:
            raise ReplayError(str(exc)) from exc
    else:
        provider = seat.get("provider")
        if provider not in {"claude", "codex", "cursor", "agent", "agy"}:
            raise ReplayError(f"unknown seat {name}")
        provider, model, effort, speed = ("agent" if provider == "cursor" else provider,
                                          seat.get("model"), seat.get("effort"), seat.get("speed"))
    probe = {"provider": provider, "model": model, "effort": effort, "speed": speed, "repo": "/replay",
             "prompt": "x", "write_scope": [], "provider_contract_version": CURRENT_PROVIDER_CONTRACT}
    try:
        provider_contract(probe)
    except ValueError as exc:
        raise ReplayError(str(exc)) from exc
    return provider, model, effort, speed, family
def review_prompt(case, provider):
    task = case["task"]
    tail = (f"HEAD is the worker commit for {task} ({MISSION_2A}/tasks/{task}.md); the change under review is HEAD against HEAD~1. The verdict is one JSON object that matches schemas/review-verdict.schema.json, with each blocking finding given as file:line with a failing input.")
    return brain_prompt.render("review", MISSION_2A, provider) + "\n## Review request\n" + tail
def main(argv=None):
    parser = argparse.ArgumentParser(prog="replay_seeded_defects.py")
    parser.add_argument("--fleet", required=True)
    parser.add_argument("--seat", action="append", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--source", default=None)
    parser.add_argument("--routing-data", default=None)
    parser.add_argument("--inventory", default=str(probe_seat.DEFAULT_INVENTORY))
    parser.add_argument("--timeout", type=float, default=1800)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    if args.timeout <= 0:
        print("replay_seeded_defects: timeout must be > 0", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parent.parent
    source = Path(args.source) if args.source else root
    routing = Path(args.routing_data) if args.routing_data else root / REQUIRED_2A
    try:
        req = required(routing)
        bindings = [seat_binding(args.fleet, name, args.inventory) for name in args.seat]
    except (ReplayError, ValueError) as exc:
        print(f"replay_seeded_defects: {exc}", file=sys.stderr)
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tab = "\t".join
    print(tab(("seat", "family", "case", "required", "caught")))
    failed, seat_families = False, set()
    for name, (provider, model, effort, speed, family) in zip(args.seat, bindings):
        seat_families.add(family)
        need = set(req.get(family, []))
        for case in CASES:
            with tempfile.TemporaryDirectory() as temp:
                clone = plant(source, case, temp)
                spec = {"provider": provider, "model": model, "effort": effort, "speed": speed, "repo": str(clone),
                        "prompt": review_prompt(case, provider), "write_scope": [],
                        "provider_contract_version": CURRENT_PROVIDER_CONTRACT}
                stdout = probe_seat._run(provider_contract(spec)[0], clone, args.timeout)[1]
            (out_dir / f"{name}-{case['id']}.out").write_text(stdout, encoding="utf-8")
            reqd, got = case["id"] in need, caught(provider, stdout.encode(), case)
            print(tab((name, family, case["id"], "yes" if reqd else "no", "yes" if got else "no")))
            failed |= reqd and not got
    for family in sorted(req):
        if req[family] and family not in seat_families:
            print(f"missing\t{family}")
            failed = True
    print(tab(("result", "pass" if not failed else "fail")))
    return 1 if failed else 0
if __name__ == "__main__":
    sys.exit(main())
