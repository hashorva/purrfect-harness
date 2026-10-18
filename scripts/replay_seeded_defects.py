#!/usr/bin/env python3
"""Replay the F001 step 7 seeded defect cases and judge reviewer answers."""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import observe_output
import validate_verdict
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
