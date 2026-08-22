#!/usr/bin/env python3
"""Fail-closed Phase 1 dispatch policy and exclusive workspace lock."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from fleet_state import CAPABILITIES, read_json, validate_fleet
from execution_spec import artifact_directory, SpecError, validate_write_scope


class PolicyError(ValueError):
    """The requested dispatch is not authorized by the current mission state."""


def fail(message):
    raise PolicyError(message)


def git_root(value):
    path = Path(value)
    if not path.is_absolute() or not path.is_dir() or path != path.resolve():
        fail("workspace must be an existing canonical absolute directory")
    try:
        top = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise PolicyError("workspace must be a Git worktree") from exc
    if Path(top).resolve() != path:
        fail("workspace must be the Git worktree root")
    return path


def mission_path(root, supplied):
    path = Path(supplied)
    absolute = path if path.is_absolute() else root / path
    try:
        absolute = absolute.resolve(strict=True)
    except OSError as exc:
        raise PolicyError("mission directory does not exist") from exc
    missions_root = (root / "docs/missions").resolve()
    if absolute.parent != missions_root or not absolute.is_dir():
        fail("mission must be one direct directory under docs/missions")
    return absolute, absolute.relative_to(root).as_posix()


def front_matter(path, label):
    if not path.is_file() or path.is_symlink():
        fail(f"{label} must be a regular file")
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeError) as exc:
        raise PolicyError(f"cannot read {label}") from exc
    if not lines or lines[0] != "---":
        fail(f"{label} requires front matter")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise PolicyError(f"{label} front matter is not closed") from exc
    values = {}
    for line in lines[1:closing]:
        if not line.strip():
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(\S(?:.*\S)?)", line)
        if match is None:
            fail(f"{label} front matter contains an invalid or empty field")
        key, value = match.groups()
        if key in values:
            fail(f"{label} front matter repeats {key}")
        values[key] = value
    return values


def mission_status(mission):
    values = front_matter(mission / "GOAL.md", "GOAL.md")
    status = values.get("status")
    allowed = {"draft", "approved", "in-progress", "awaiting-gate", "done"}
    if status not in allowed:
        fail("GOAL.md status is missing or invalid")
    return status


def approved_fleet(mission, mission_relative, supplied):
    expected = mission / "fleet.json"
    path = Path(supplied)
    if path.resolve(strict=False) != expected.resolve(strict=False):
        fail("dispatch must use the mission's fleet.json")
    try:
        document, _ = read_json(path, "fleet", require_canonical=True)
        validate_fleet(document)
    except (OSError, ValueError) as exc:
        raise PolicyError(str(exc)) from exc
    if document["mission"]["path"] != mission_relative:
        fail("fleet mission path assertion failed")
    return document


def feature_record(mission, feature):
    path = mission / "features.json"
    try:
        document = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PolicyError("features.json is missing or malformed") from exc
    records = document.get("features") if isinstance(document, dict) else None
    if not isinstance(records, list):
        fail("features.json requires a features list")
    matches = [item for item in records if isinstance(item, dict) and item.get("id") == feature]
    if len(matches) != 1:
        fail("worker feature must identify exactly one mission feature")
    if matches[0].get("passes") is not False:
        fail("worker feature must still be pending")
    return matches[0]


def worker_write_scope(task):
    try:
        lines = task.read_text().splitlines()
    except (OSError, UnicodeError) as exc:
        raise PolicyError("cannot read worker task write scope") from exc
    headings = [index for index, line in enumerate(lines) if line == "## Files you MAY touch"]
    if len(headings) != 1:
        fail("worker task requires exactly one Files you MAY touch section")
    start = headings[0] + 1
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
    patterns = []
    for line in lines[start:end]:
        if not line.strip():
            continue
        match = re.fullmatch(r"- `([^`]+)`(?: \([^\r\n]*\))?", line)
        if match is None:
            fail("Files you MAY touch must contain only backtick-quoted path bullets")
        patterns.append(match.group(1))
    try:
        return validate_write_scope(patterns)
    except SpecError as exc:
        raise PolicyError(str(exc)) from exc


def clean_workspace(root):
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        fail("cannot inspect workspace cleanliness")
    if result.stdout:
        fail("workspace must be clean before dispatch")


def validate_capability(provider, effort, speed):
    capabilities = CAPABILITIES.get(provider)
    if capabilities is None:
        fail("provider is not supported")
    if effort not in capabilities["efforts"]:
        fail("provider does not support the requested effort")
    if speed not in capabilities["speeds"]:
        fail("provider does not support the requested speed")


def validate_worker(args):
    root = git_root(args.root)
    workspace = git_root(args.workspace)
    if workspace != root:
        fail("cross-repository execution is disabled in Phase 1")
    mission, mission_relative = mission_path(root, args.mission)
    if mission_status(mission) != "in-progress":
        fail("worker/implement requires an in-progress mission")
    approved_fleet(mission, mission_relative, args.fleet)
    task = Path(args.task)
    task = task if task.is_absolute() else root / task
    try:
        task = task.resolve(strict=True)
    except OSError as exc:
        raise PolicyError("worker task does not exist") from exc
    if task.parent != mission / "tasks" or task.suffix != ".md":
        fail("worker task must be a direct file under the mission tasks directory")
    if task.stem != args.work_unit:
        fail("worker work-unit must equal the task filename")
    values = front_matter(task, "worker task")
    if values.get("task_id") != args.work_unit:
        fail("worker task_id must equal the requested work-unit")
    if not args.feature or values.get("feature") != args.feature:
        fail("worker task feature must equal --feature")
    feature_record(mission, args.feature)
    write_scope = worker_write_scope(task)
    clean_workspace(root)
    return write_scope


def validate_brain(args):
    root = git_root(args.root)
    workspace = git_root(args.workspace)
    if workspace != root:
        fail("cross-repository execution is disabled in Phase 1")
    mission, mission_relative = mission_path(root, args.mission)
    status = mission_status(mission)
    if args.action in {"mission-init", "gate0"}:
        if status != "draft":
            fail(f"brain/{args.action} requires a draft mission")
    elif args.action == "review":
        if status not in {"in-progress", "awaiting-gate"}:
            fail("brain/review requires an in-progress or awaiting-gate mission")
        approved_fleet(mission, mission_relative, args.fleet)
    else:
        fail("unknown brain dispatch action")
    clean_workspace(root)
    if args.action == "review":
        return [f"{mission_relative}/PROGRESS.md"]
    return [f"{mission_relative}/**"]


def lock_location(root, workspace):
    digest = hashlib.sha256(os.fsencode(str(workspace))).hexdigest()
    return root / ".tasks/locks" / f"workspace-{digest}.lock"


def acquire_lock(args):
    root = git_root(args.root)
    workspace = git_root(args.workspace)
    if workspace != root:
        fail("cross-repository execution is disabled in Phase 1")
    try:
        lock_directory = artifact_directory(root, "locks")
    except SpecError as exc:
        raise PolicyError(str(exc)) from exc
    path = lock_directory / lock_location(root, workspace).name
    try:
        path.mkdir()
    except FileExistsError as exc:
        raise PolicyError(f"workspace is already locked: {path}") from exc
    token = str(uuid.uuid4())
    owner = {
        "schema_version": 1,
        "token": token,
        "workspace": str(workspace),
        "pid": os.getppid(),
    }
    try:
        with (path / "owner.json").open("x") as handle:
            json.dump(owner, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.rmdir()
        except OSError:
            pass
        raise
    print(json.dumps({"path": str(path), "token": token}, sort_keys=True, separators=(",", ":")))


def release_lock(args):
    root = git_root(args.root)
    workspace = git_root(args.workspace)
    try:
        lock_directory = artifact_directory(root, "locks", create=False)
    except SpecError as exc:
        raise PolicyError(str(exc)) from exc
    expected = lock_directory / lock_location(root, workspace).name
    path = Path(args.lock)
    if not path.is_absolute() or path != expected or path.is_symlink() or not path.is_dir():
        fail("workspace lock path assertion failed")
    owner_path = path / "owner.json"
    try:
        owner = json.loads(owner_path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PolicyError("workspace lock owner is missing or malformed") from exc
    expected_keys = {"schema_version", "token", "workspace", "pid"}
    if not isinstance(owner, dict) or set(owner) != expected_keys:
        fail("workspace lock owner has invalid fields")
    if owner["schema_version"] != 1 or owner["token"] != args.token or owner["workspace"] != str(workspace):
        fail("workspace lock ownership assertion failed")
    owner_path.unlink()
    path.rmdir()


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    worker = commands.add_parser("validate-worker")
    brain = commands.add_parser("validate-brain")
    capability = commands.add_parser("validate-capability")
    acquire = commands.add_parser("acquire-lock")
    release = commands.add_parser("release-lock")
    for command in (worker, brain, acquire, release):
        command.add_argument("--root", required=True)
        command.add_argument("--workspace", required=True)
    worker.add_argument("--mission", required=True)
    worker.add_argument("--fleet", required=True)
    worker.add_argument("--task", required=True)
    worker.add_argument("--feature", required=True)
    worker.add_argument("--work-unit", required=True)
    brain.add_argument("--mission", required=True)
    brain.add_argument("--fleet", required=True)
    brain.add_argument("--action", required=True)
    capability.add_argument("--provider", required=True)
    capability.add_argument("--effort", required=True)
    capability.add_argument("--speed", required=True)
    release.add_argument("--lock", required=True)
    release.add_argument("--token", required=True)
    args = parser.parse_args()
    try:
        if args.command == "validate-worker":
            write_scope = validate_worker(args)
            print(json.dumps({"write_scope": write_scope}, sort_keys=True, separators=(",", ":")))
        elif args.command == "validate-brain":
            write_scope = validate_brain(args)
            print(json.dumps({"write_scope": write_scope}, sort_keys=True, separators=(",", ":")))
        elif args.command == "validate-capability":
            validate_capability(args.provider, args.effort, args.speed)
        elif args.command == "acquire-lock":
            acquire_lock(args)
        else:
            release_lock(args)
    except PolicyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
