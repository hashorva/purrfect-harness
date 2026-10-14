#!/usr/bin/env python3
"""Seat smoke scaffold: plan one tiny scratch-clone task per frozen worker seat.

`fleet-doctor.sh --smoke --dry-run` clones the live HEAD into a scratch directory,
commits a fixture there with exactly one active mission (a smoke mission carrying a
copy of the source fleet), and prints the exact spawn-worker argv for each non-brain
seat. It launches nothing; launching is implemented in T-008.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

# This module is run through fleet_doctor.py and imported by tests.  Make the
# sibling policy modules importable in each case.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from dispatch_policy import mission_path
from execution_receipt import snapshot
from fleet_state import canonical, read_json, validate_fleet
from harness_registry import canonical_provider, load_registry

FIXTURE_DIR = "docs/missions/00000000-seat-smoke"
ACTIVE_STATUSES = {"in-progress", "awaiting-gate"}
BRAIN_NOTE = "not launched; proven by the latest completed in-scope brain receipt"
GIT_AUTHOR = ["-c", "user.name=seat smoke", "-c", "user.email=smoke@localhost.invalid"]


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


def discard(dest, created, clone):
    # Remove only what this run created: the clone, and its parent when we made it.
    target = dest if created else clone
    if target.exists():
        shutil.rmtree(target)


def run(argv):
    parser = argparse.ArgumentParser(prog="fleet-doctor.sh --smoke")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mission")
    parser.add_argument("--seat", action="append", default=[])
    parser.add_argument("--dest")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run:
        fail("launch is implemented in T-008", code=2)

    root = live_root()
    if git(["status", "--porcelain"], root).strip():
        fail("live tree must be clean before a seat smoke")
    before = snapshot(root)

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
        base = build_fixture(
            clone, source_rel, source_fleet, hashlib.sha256(source_raw).hexdigest(), smoke_seats,
        )
        plan = {}
        for seat in smoke_seats:
            task = f"{FIXTURE_DIR}/tasks/{task_id_for(seat)}.md"
            plan[seat] = {"task": task, "argv": smoke_argv(seat, seats[seat], task)}
        after = snapshot(root)
        if after != before:
            fail("live tree changed during seat smoke")
        result = {
            "base_commit": base,
            "clone": str(clone),
            "kept": bool(args.keep),
            "mission": source_rel,
            "seats": plan,
            "skipped": {name: BRAIN_NOTE for name in seats if name.startswith("brain")},
        }
        print(json.dumps(result, sort_keys=True))
        return 0
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
