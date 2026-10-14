#!/usr/bin/env python3
"""Seat smoke: plan, launch and classify one tiny scratch-clone task per frozen worker seat.

`fleet-doctor.sh --smoke` clones the live HEAD into a scratch directory, removes the clone's
remote, commits a fixture there with exactly one active mission (a smoke mission carrying a
copy of the source fleet), and then runs each non-brain seat's spawn-worker argv blocking in
the clone. Classification comes from the clone's receipt and Git state only. `--dry-run`
prints the planned argv and launches nothing.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

# This module is run through fleet_doctor.py and imported by tests.  Make the
# sibling policy modules importable in each case.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from dispatch_policy import mission_path
from execution_receipt import load_receipt, snapshot
from fleet_state import canonical, read_json, validate_fleet
from harness_registry import canonical_provider, load_registry

FIXTURE_DIR = "docs/missions/00000000-seat-smoke"
ACTIVE_STATUSES = {"in-progress", "awaiting-gate"}
BRAIN_NOTE = "not launched; proven by the latest completed in-scope brain receipt"
FAST_REASON = "fast mode is never smoked"
GIT_AUTHOR = ["-c", "user.name=seat smoke", "-c", "user.email=smoke@localhost.invalid"]
DEFAULT_TIMEOUT = 600
REASON_LIMIT = 300
RUN_ID = re.compile(r"spawn-worker: .*\brun_id=([0-9a-f-]{36})\b")
USABLE = {"usable", "usable-with-limit"}


class SmokeError(ValueError):
    """Refusal with the exit code the caller must return."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def fail(message, code=1):
    raise SmokeError(message, code)


def live_root():
    return Path(__file__).resolve().parents[1]


def git(args, cwd):
    result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False)
    if result.returncode:
        fail(f"git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def live_state(root):
    """Everything a seat smoke must leave untouched in the live repository: tree and refs."""
    return {"snapshot": snapshot(root), "refs": git(["for-each-ref", "--format=%(refname) %(objectname)"], root)}


def utc_now():
    return datetime.now(timezone.utc)


def goal_status(path):
    for line in path.read_text().splitlines():
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip()
    return None


def source_mission(root, supplied):
    if supplied is None:
        result = subprocess.run(
            ["bash", str(root / "scripts/active-mission.sh")],
            cwd=root, env={**os.environ, "REPO": str(root)}, capture_output=True, text=True, check=False,
        )
        if result.returncode:
            fail(result.stderr.strip() or "active-mission.sh failed")
        supplied = result.stdout.strip()
    return mission_path(root, supplied)


def prepare_dest(root, supplied):
    """Return (dest, created). A supplied dest must be outside the live tree or under .tasks/smoke/."""
    if supplied is None:
        return Path(tempfile.mkdtemp(prefix="purrfect-smoke.", dir=os.environ.get("TMPDIR") or "/tmp")), True
    dest = Path(supplied).expanduser()
    if not dest.is_absolute():
        dest = Path.cwd() / dest
    dest = dest.resolve()
    smoke_root = (root / ".tasks/smoke").resolve()
    inside_live = dest == root or root in dest.parents
    if inside_live and smoke_root not in dest.parents:
        fail("--dest must be outside the live tree or under .tasks/smoke/", code=2)
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        fail("--dest must not exist or be empty", code=2)
    created = not dest.exists()
    dest.mkdir(parents=True, exist_ok=True)
    return dest, created


def remove_active_missions(clone):
    for goal in sorted((clone / "docs/missions").glob("*/GOAL.md")):
        if goal.parent.name != "templates" and goal_status(goal) in ACTIVE_STATUSES:
            git(["rm", "-r", "-q", goal.parent.relative_to(clone).as_posix()], clone)


def task_id_for(seat):
    return "T-SMOKE-" + seat.replace(".", "-")


def task_text(seat, task_id):
    return f"""---
task_id: {task_id}
feature: SMOKE
---
# Task: seat smoke {seat}

Objective: write the line `seat smoke {seat}` to `docs/smoke/{seat}.txt` and to
`.agents/smoke/{seat}.txt` (create the directories). Run both verification commands.
Then commit as `smoke: {seat}`. If the `.agents/` write fails, record the exact error in
`{FIXTURE_DIR}/PROGRESS.md` and still commit the docs file.

## Files you MAY touch

- `docs/smoke/{seat}.txt`
- `.agents/smoke/{seat}.txt`
- `{FIXTURE_DIR}/PROGRESS.md`

## Verification commands

- `{json.dumps(["test", "-f", f"docs/smoke/{seat}.txt"])}`
- `{json.dumps(["test", "-f", f".agents/smoke/{seat}.txt"])}`
"""


def build_fixture(clone, source_rel, source_fleet, source_sha, seats):
    """Commit one smoke mission and one task per seat in the scratch clone; return the base commit."""
    remove_active_missions(clone)
    mission = clone / FIXTURE_DIR
    (mission / "tasks").mkdir(parents=True)
    (mission / "GOAL.md").write_text(
        "---\nstatus: in-progress\n---\n# Goal\n\nScratch seat smoke. No authority outside this clone.\n"
    )
    (mission / "PROGRESS.md").write_text("# Scratch seat smoke progress\n\n")
    (mission / "features.json").write_text(json.dumps({
        "goal": "Scratch seat smoke",
        "features": [{
            "id": "SMOKE", "category": "functional", "priority": 1, "bootstrap": False,
            "description": "Scratch seat smoke carrier. Never accepted; scratch clone only.",
            "steps": ["Each selected seat writes its smoke line and commits it"],
            "passes": False,
        }],
    }, indent=2) + "\n")
    approval = {**source_fleet["approval"], "approved_by":
                f"{source_fleet['approval']['approved_by']} (copied by seat smoke from "
                f"{source_rel}/fleet.json sha256 {source_sha}; scratch clone only)"}
    smoke_fleet = {**source_fleet, "mission": {"path": FIXTURE_DIR}, "approval": approval}
    validate_fleet(smoke_fleet)
    (mission / "fleet.json").write_text(canonical(smoke_fleet))
    for seat in seats:
        (mission / "tasks" / f"{task_id_for(seat)}.md").write_text(task_text(seat, task_id_for(seat)))
    git(["add", "-A"], clone)
    git([*GIT_AUTHOR, "commit", "-q", "-m", "smoke: scratch fixture"], clone)
    return git(["rev-parse", "HEAD"], clone).strip()


def smoke_argv(seat, seat_spec, task):
    tier = seat.split(".", 1)[1]
    provider = canonical_provider(load_registry(), seat_spec["provider"])
    return ["bash", "scripts/spawn-worker.sh", provider, task, "--tier", tier,
            "--feature", "SMOKE", "--attempt", "1",
            "--effort", seat_spec["effort"], "--speed", seat_spec["speed"]]


def is_fast(seat_spec):
    return seat_spec["speed"] == "fast" or seat_spec["model"].endswith("-fast")


def discard(dest, created, clone):
    # Remove only what this run created: the clone, and its parent when we made it.
    target = dest if created else clone
    if target.exists():
        shutil.rmtree(target)


def run_id_of(out_path):
    if not out_path.is_file():
        return None
    match = RUN_ID.search(out_path.read_text(errors="replace"))
    return match.group(1) if match else None


def receipt_for(clone, run_id):
    """Return (receipt, None) or (None, reason). The receipt is the only run evidence used."""
    if run_id is None:
        return None, "no receipt"
    path = clone / ".tasks/receipts" / f"{run_id}.json"
    if not path.is_file():
        return None, "no receipt"
    try:
        return load_receipt(path), None
    except ValueError as exc:
        return None, f"invalid receipt: {exc}"


def error_lines(out_path):
    """At most three transcript lines that name an error; never more of the transcript."""
    if not out_path.is_file():
        return []
    lines = [line.strip() for line in out_path.read_text(errors="replace").splitlines()
             if "ERROR" in line or "Cannot" in line]
    return lines[:3]


def classify(seat, receipt, reason, head_paths, out_path):
    """Return (status, reason) from the clone's receipt and HEAD tree only."""
    docs = f"docs/smoke/{seat}.txt"
    agents = f".agents/smoke/{seat}.txt"
    if receipt and receipt["outcome"] == "completed" and receipt["exit_code"] == 0 \
            and receipt["scope"]["result"] == "pass":
        if docs in head_paths and agents in head_paths:
            return "usable", "both smoke files in HEAD"
        if docs in head_paths:
            return "usable-with-limit", "cannot write .agents/"
    if receipt:
        reason = f"outcome={receipt['outcome']} exit_code={receipt['exit_code']}"
    detail = " | ".join([reason, *error_lines(out_path)])
    return "unusable", detail[:REASON_LIMIT]


def reset_if_dirty(clone):
    if not git(["status", "--porcelain"], clone).strip():
        return False
    git(["reset", "-q", "--hard", "HEAD"], clone)
    git(["clean", "-fdq", "-e", ".tasks"], clone)
    return True


def smoke_seat(seat, seat_spec, plan_entry, clone, dest, timeout):
    """Launch one seat blocking in the clone (unless fast) and return its summary entry."""
    entry = {"commit": None, "clone_reset": False, "effort": seat_spec["effort"], "exit_code": None,
             "model": seat_spec["model"], "outcome": None, "provider": seat_spec["provider"],
             "run_id": None, "speed": seat_spec["speed"]}
    if is_fast(seat_spec):
        return {**entry, "reason": FAST_REASON, "status": "unusable"}
    out_path = dest / f"{seat}.out"
    env = {**os.environ, "SPAWN_WORKER_TIMEOUT_SECS": str(timeout)}
    with out_path.open("w") as out:
        subprocess.run(plan_entry["argv"], cwd=clone, env=env, stdin=subprocess.DEVNULL,
                       stdout=out, stderr=subprocess.STDOUT, check=False)
    run_id = run_id_of(out_path)
    receipt, reason = receipt_for(clone, run_id)
    head_paths = set(git(["ls-tree", "-r", "--name-only", "HEAD"], clone).splitlines())
    status, reason = classify(seat, receipt, reason, head_paths, out_path)
    entry.update(run_id=run_id, status=status, reason=reason)
    if receipt:
        entry.update(outcome=receipt["outcome"], exit_code=receipt["exit_code"],
                     commit=receipt["git_after"]["head"])
    entry["clone_reset"] = reset_if_dirty(clone)
    return entry


def write_summary(root, stamp, summary):
    summary_dir = root / ".tasks/smoke"
    summary_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(summary, sort_keys=True)
    with (summary_dir / f"{stamp}.json").open("x") as handle:
        handle.write(text + "\n")
    return text


def run(argv):
    parser = argparse.ArgumentParser(prog="fleet-doctor.sh --smoke")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mission")
    parser.add_argument("--seat", action="append", default=[])
    parser.add_argument("--dest")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)
    if args.timeout < 1:
        fail("--timeout must be a positive number of seconds", code=2)
    started = utc_now()

    root = live_root()
    if git(["status", "--porcelain"], root).strip():
        fail("live tree must be clean before a seat smoke")
    before = live_state(root)

    mission, source_rel = source_mission(root, args.mission)
    source_raw = (mission / "fleet.json").read_bytes()
    source_fleet, _ = read_json(mission / "fleet.json", "fleet", require_canonical=True)
    validate_fleet(source_fleet)
    seats = source_fleet["seats"]
    smoke_seats = sorted(name for name in seats if not name.startswith("brain"))
    if args.seat:
        for name in args.seat:
            if name not in seats:
                fail(f"unknown seat: {name}", code=2)
            if name.startswith("brain"):
                fail(f"brain seat is never smoked: {name}", code=2)
        smoke_seats = sorted(set(args.seat))
    if not smoke_seats:
        fail("fleet has no non-brain seats to smoke")

    dest, created = prepare_dest(root, args.dest)
    clone = dest / "repo"
    try:
        git(["clone", "--quiet", "--no-hardlinks", str(root), str(clone)], root)
        git(["remote", "remove", "origin"], clone)
        base = build_fixture(
            clone, source_rel, source_fleet, hashlib.sha256(source_raw).hexdigest(), smoke_seats,
        )
        plan = {}
        for seat in smoke_seats:
            task = f"{FIXTURE_DIR}/tasks/{task_id_for(seat)}.md"
            plan[seat] = {"task": task, "argv": smoke_argv(seat, seats[seat], task)}
        skipped = {name: BRAIN_NOTE for name in seats if name.startswith("brain")}
        if args.dry_run:
            after = live_state(root)
            if after != before:
                fail("live tree changed during seat smoke")
            result = {
                "base_commit": base,
                "clone": str(clone),
                "kept": bool(args.keep),
                "mission": source_rel,
                "seats": plan,
                "skipped": skipped,
            }
            print(json.dumps(result, sort_keys=True))
            return 0

        seat_results = {
            seat: smoke_seat(seat, seats[seat], plan[seat], clone, dest, args.timeout)
            for seat in smoke_seats
        }
        after = live_state(root)
        if after != before:
            fail("live tree changed during seat smoke")
        launched = [entry for entry in seat_results.values() if entry["reason"] != FAST_REASON]
        passed = bool(launched) and all(entry["status"] in USABLE for entry in launched)
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        summary = {
            "base_commit": base,
            "clone": str(clone),
            "finished_at": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kept": bool(args.keep),
            "mission": source_rel,
            "seats": seat_results,
            "skipped": skipped,
            "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        print(write_summary(root, stamp, summary))
        return 0 if passed else 1
    finally:
        if not args.keep:
            discard(dest, created, clone)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        return run(argv)
    except ValueError as exc:
        print(f"ERROR smoke: {exc}", file=sys.stderr)
        return getattr(exc, "code", 1)


if __name__ == "__main__":
    raise SystemExit(main())
