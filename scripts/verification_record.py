#!/usr/bin/env python3
"""Immutable, run-bound verification records and feature acceptance policy."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from execution_receipt import ReceiptError, canonical_bytes, load_receipt, snapshot
from execution_spec import SpecError, load_persisted, spec_sha256

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
HEX = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
RFC3339 = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
GIT_FIELDS = {"head", "status_porcelain_v1_z_sha256", "status_entry_count", "dirty_paths"}
RECORD_FIELDS = {"schema_version", "run_id", "mission", "feature", "work_unit", "attempt",
                 "execution_spec", "execution_receipt", "task", "receipt_git_after",
                 "verification_git_before", "verification_git_after", "commands", "result"}


class VerificationError(ValueError):
    pass


def fail(message):
    raise VerificationError(message)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return canonical_bytes(value)


def root_path():
    root = Path.cwd().resolve()
    if subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True).returncode:
        fail("current directory must be a Git worktree root")
    return root


def mission_path(root, supplied):
    mission = (Path(supplied) if Path(supplied).is_absolute() else root / supplied).resolve()
    missions = (root / "docs/missions").resolve()
    if not mission.is_dir() or mission.parent != missions:
        fail(f"mission must be one direct directory under {missions}")
    return mission


def atomic_create(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        fd, name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno()); os.fchmod(handle.fileno(), 0o400)
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise VerificationError(f"VerificationRecord already exists for run_id {path.stem}") from exc
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
        os.chmod(path, 0o400)
    finally:
        if temporary is not None:
            try: temporary.unlink()
            except FileNotFoundError: pass


def atomic_replace(path, data):
    mode = path.stat().st_mode & 0o777
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        try: temporary.unlink()
        except FileNotFoundError: pass


def task_at_base(root, receipt):
    task = receipt["task"]
    expected = f"{receipt['mission']}/tasks/{receipt['work_unit']}.md"
    if task != expected:
        fail("receipt task does not exactly match mission work unit")
    got = subprocess.run(["git", "-C", str(root), "show", f"{receipt['git_before']['head']}:{task}"], capture_output=True)
    if got.returncode:
        fail("task is absent from the receipt base commit")
    raw = got.stdout
    try: text = raw.decode("utf-8")
    except UnicodeDecodeError as exc: raise VerificationError("committed task is not UTF-8") from exc
    front = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if not front:
        fail("committed task has no strict front matter")
    values = dict(re.findall(r"^([a-z_]+): ([^\n]+)$", front.group(1), re.M))
    if values.get("task_id") != receipt["work_unit"] or values.get("feature") != receipt["feature"]:
        fail("committed task identity does not match receipt")
    sections = list(re.finditer(r"^## Verification commands[ \t]*\n", text, re.M))
    if len(sections) != 1:
        fail("committed task has no Verification commands section")
    body = text[sections[0].end():]
    # A single customary blank line is allowed, but anything other than consecutive
    # code-span bullets ends this section (and a malformed bullet fails closed).
    if body.startswith("\n"):
        body = body[1:]
    commands = []
    for line in body.splitlines():
        if not line:
            break
        if line.startswith("## "):
            break
        if not line.startswith("- `") or not line.endswith("`") or line.count("`") != 2:
            fail("verification command must be one Markdown JSON code span bullet")
        try: argv = json.loads(line[3:-1])
        except json.JSONDecodeError as exc: raise VerificationError("verification command is not JSON") from exc
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
            fail("verification command must be a non-empty JSON argv of strings")
        commands.append(argv)
    if not commands: fail("committed task authorizes no verification commands")
    return task, raw, commands


def bind(root, mission, run_id):
    if not UUID.fullmatch(run_id): fail("run_id must be a canonical RFC UUID")
    receipt_path = root / ".tasks/receipts" / f"{run_id}.json"
    try: receipt = load_receipt(receipt_path)
    except (ReceiptError, SpecError) as exc: raise VerificationError(str(exc)) from exc
    mission_rel = mission.relative_to(root).as_posix()
    if receipt["mission"] != mission_rel or receipt["run_id"] != run_id or receipt["role"] != "worker":
        fail("receipt does not identify this mission worker run")
    if receipt["outcome"] != "completed" or receipt["exit_code"] != 0 or receipt["scope"]["result"] != "pass" or receipt["workspace_changed"] is not True:
        fail("receipt is not completed, changed, in-scope worker evidence")
    spec_path = Path(receipt["execution_spec_path"])
    try: _, spec_raw = load_persisted(spec_path)
    except SpecError as exc: raise VerificationError(str(exc)) from exc
    if spec_sha256(spec_raw) != receipt["execution_spec_sha256"]: fail("spec hash binding failed")
    task, task_raw, commands = task_at_base(root, receipt)
    return receipt, receipt_path, spec_path, spec_raw, task, task_raw, commands


def verify(root, mission, run_id):
    destination = mission / "verification" / f"{run_id}.json"
    if destination.exists(): fail("VerificationRecord already exists for this run")
    receipt, receipt_path, spec_path, spec_raw, task, task_raw, commands = bind(root, mission, run_id)
    before = snapshot(root)
    if before != receipt["git_after"]: fail("current Git snapshot does not equal receipt git_after before checks")
    outcomes = []
    passed = True
    for argv in commands:
        started = now()
        try:
            completed = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL, capture_output=True)
            exit_code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        except OSError as exc:
            exit_code, stdout, stderr = 127, b"", str(exc).encode("utf-8", "replace")
        finished = now()
        outcomes.append({"argv": argv, "started_at": started, "finished_at": finished,
                         "exit_code": exit_code, "stdout_sha256": digest(stdout),
                         "stderr_sha256": digest(stderr)})
        passed = passed and exit_code == 0
    after = snapshot(root)
    if after != receipt["git_after"]: passed = False
    record = {"schema_version": 1, "run_id": run_id, "mission": receipt["mission"], "feature": receipt["feature"],
              "work_unit": receipt["work_unit"], "attempt": receipt["attempt"],
              "execution_spec": {"path": str(spec_path), "sha256": digest(spec_raw)},
              "execution_receipt": {"path": receipt_path.relative_to(root).as_posix(), "sha256": digest(receipt_path.read_bytes())},
              "task": {"path": task, "sha256": digest(task_raw), "git_commit": receipt["git_before"]["head"]},
              "receipt_git_after": receipt["git_after"], "verification_git_before": before,
              "verification_git_after": after, "commands": outcomes, "result": "pass" if passed else "fail"}
    validate_record(record)
    atomic_create(destination, canonical(record))
    return record, destination


def validate_record(record):
    if not isinstance(record, dict) or set(record) != RECORD_FIELDS or record.get("schema_version") != 1: fail("VerificationRecord has invalid fields")
    if not UUID.fullmatch(record["run_id"]) or record["result"] not in {"pass", "fail"}: fail("VerificationRecord has invalid identity or result")
    for field in ("mission", "feature", "work_unit"):
        if not isinstance(record[field], str) or not record[field]: fail("VerificationRecord has invalid identity")
    if isinstance(record["attempt"], bool) or not isinstance(record["attempt"], int) or record["attempt"] < 1: fail("VerificationRecord attempt is invalid")
    for item in (record["execution_spec"], record["execution_receipt"], record["task"]):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not HEX.fullmatch(item.get("sha256", "")): fail("VerificationRecord link is invalid")
    if set(record["execution_spec"]) != {"path", "sha256"} or not Path(record["execution_spec"]["path"]).is_absolute(): fail("VerificationRecord spec link is invalid")
    if set(record["execution_receipt"]) != {"path", "sha256"} or not re.fullmatch(r"\.tasks/receipts/[0-9a-f-]+\.json", record["execution_receipt"]["path"]): fail("VerificationRecord receipt link is invalid")
    if set(record["task"]) != {"path", "sha256", "git_commit"} or not COMMIT.fullmatch(record["task"]["git_commit"]): fail("VerificationRecord task link is invalid")
    for name in ("receipt_git_after", "verification_git_before", "verification_git_after"):
        state = record[name]
        if not isinstance(state, dict) or set(state) != GIT_FIELDS or not COMMIT.fullmatch(state.get("head", "")) or not HEX.fullmatch(state.get("status_porcelain_v1_z_sha256", "")) or isinstance(state.get("status_entry_count"), bool) or not isinstance(state.get("status_entry_count"), int) or state["status_entry_count"] < 0 or not isinstance(state.get("dirty_paths"), list) or not all(isinstance(p, str) and p and not p.startswith("/") and ".." not in p.split("/") for p in state["dirty_paths"]): fail("VerificationRecord Git snapshot is invalid")
    if not isinstance(record["commands"], list) or not record["commands"]: fail("VerificationRecord commands are invalid")
    for command in record["commands"]:
        if set(command) != {"argv", "started_at", "finished_at", "exit_code", "stdout_sha256", "stderr_sha256"} or not isinstance(command["argv"], list) or not command["argv"] or not all(isinstance(v, str) and v for v in command["argv"]): fail("VerificationRecord command is invalid")
        if not isinstance(command["exit_code"], int) or isinstance(command["exit_code"], bool) or not RFC3339.fullmatch(command["started_at"]) or not RFC3339.fullmatch(command["finished_at"]) or not HEX.fullmatch(command["stdout_sha256"]) or not HEX.fullmatch(command["stderr_sha256"]): fail("VerificationRecord command evidence is invalid")
    return record


def load_record(path):
    if not path.is_file() or path.is_symlink(): fail("VerificationRecord is missing or not regular")
    try: raw = path.read_bytes(); record = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc: raise VerificationError(f"cannot read VerificationRecord: {exc}") from exc
    if raw != canonical(record): fail("VerificationRecord is not canonical JSON")
    return validate_record(record), raw


def revalidate_record(root, mission, record):
    """Rebind every record assertion to the exact current receipt/spec/base task."""
    receipt, receipt_path, spec_path, spec_raw, task, task_raw, commands = bind(root, mission, record["run_id"])
    expected = {
        "mission": receipt["mission"], "run_id": receipt["run_id"], "feature": receipt["feature"],
        "work_unit": receipt["work_unit"], "attempt": receipt["attempt"],
        "execution_spec": {"path": str(spec_path), "sha256": digest(spec_raw)},
        "execution_receipt": {"path": receipt_path.relative_to(root).as_posix(), "sha256": digest(receipt_path.read_bytes())},
        "task": {"path": task, "sha256": digest(task_raw), "git_commit": receipt["git_before"]["head"]},
        "receipt_git_after": receipt["git_after"],
    }
    for key, value in expected.items():
        if record.get(key) != value: fail(f"VerificationRecord {key} does not match exact execution evidence")
    if record["verification_git_before"] != receipt["git_after"] or record["verification_git_after"] != receipt["git_after"]:
        fail("VerificationRecord verification snapshots do not equal receipt git_after")
    if [item["argv"] for item in record["commands"]] != commands:
        fail("VerificationRecord commands do not match committed task authorization")
    command_ok = all(item["exit_code"] == 0 for item in record["commands"])
    if (record["result"] == "pass") != command_ok:
        fail("VerificationRecord result contradicts command outcomes")
    return receipt


def accept(root, mission, run_id, expected_hash, accepted_by):
    if not HEX.fullmatch(expected_hash) or not isinstance(accepted_by, str) or not accepted_by.strip() or accepted_by.strip() != accepted_by: fail("verification hash or accepted_by is invalid")
    lock_dir = root / ".tasks/locks"
    if os.environ.get("PURRFECT_DISPATCH_LOCK_PATH") or (lock_dir.is_dir() and list(lock_dir.glob("*.lock"))):
        fail("acceptance refuses while a dispatch workspace lock exists")
    record_path = mission / "verification" / f"{run_id}.json"
    record, raw = load_record(record_path)
    if digest(raw) != expected_hash or record["result"] != "pass": fail("verification record hash does not name a passing record")
    revalidate_record(root, mission, record)
    feature_path = mission / "features.json"
    try: doc = json.loads(feature_path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc: raise VerificationError(f"cannot read features.json: {exc}") from exc
    matches = [f for f in doc.get("features", []) if isinstance(f, dict) and f.get("id") == record["feature"]]
    if len(matches) != 1 or matches[0].get("passes") is not False or any(k in matches[0] for k in ("accepted_run_id", "accepted_verification_sha256", "accepted_at", "accepted_by")): fail("feature is not in an acceptable prior state")
    feature = matches[0]; feature.update({"passes": True, "accepted_run_id": run_id, "accepted_verification_sha256": expected_hash, "accepted_at": now(), "accepted_by": accepted_by})
    atomic_replace(feature_path, json.dumps(doc, indent=2, ensure_ascii=False) .encode("utf-8") + b"\n")


def audit(root, mission, require_workers=False):
    feature_path = mission / "features.json"
    try: features = json.loads(feature_path.read_text())["features"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc: raise VerificationError(f"cannot read features.json: {exc}") from exc
    failures = []
    mission_rel = mission.relative_to(root).as_posix()
    brains = []
    receipt_dir = root / ".tasks/receipts"
    if receipt_dir.is_dir():
        for path in receipt_dir.glob("*.json"):
            if not UUID.fullmatch(path.stem):
                continue
            try:
                candidate = load_receipt(path)
            except ReceiptError as exc:
                failures.append(f"invalid execution receipt {path.name}: {exc}")
                continue
            if candidate["mission"] == mission_rel and candidate["role"] == "brain":
                brains.append(candidate)
    if not any(item["outcome"] == "completed" and item["exit_code"] == 0 and item["scope"]["result"] == "pass" for item in brains):
        failures.append(f"no completed, in-scope brain ExecutionReceipt for exact mission {mission_rel}")
    for feature in features:
        if not isinstance(feature, dict): failures.append("feature is not an object"); continue
        if feature.get("passes") is True and feature.get("bootstrap") is not True:
            required = ("accepted_run_id", "accepted_verification_sha256", "accepted_at", "accepted_by")
            if any(k not in feature for k in required): failures.append(f"feature {feature.get('id')}: missing acceptance evidence"); continue
            try:
                record, raw = load_record(mission / "verification" / f"{feature['accepted_run_id']}.json")
                if digest(raw) != feature["accepted_verification_sha256"] or record["result"] != "pass" or record["feature"] != feature["id"]: raise VerificationError("record does not match accepted feature")
                revalidate_record(root, mission, record)
            except (VerificationError, KeyError) as exc: failures.append(f"feature {feature.get('id')}: {exc}")
    if require_workers and not any(isinstance(f, dict) and f.get("passes") is True and f.get("bootstrap") is not True for f in features): failures.append("--require-workers needs an accepted verified worker feature")
    if failures: raise VerificationError("; ".join(failures))


def main():
    parser = argparse.ArgumentParser(); subs = parser.add_subparsers(dest="command", required=True)
    verify_p = subs.add_parser("verify"); verify_p.add_argument("--run-id", required=True); verify_p.add_argument("mission")
    accept_p = subs.add_parser("accept"); accept_p.add_argument("--run-id", required=True); accept_p.add_argument("--verification-sha256", required=True); accept_p.add_argument("--accepted-by", required=True); accept_p.add_argument("mission")
    audit_p = subs.add_parser("audit"); audit_p.add_argument("--require-workers", action="store_true"); audit_p.add_argument("mission")
    args = parser.parse_args()
    try:
        root = root_path(); mission = mission_path(root, args.mission)
        if args.command == "verify":
            record, path = verify(root, mission, args.run_id); print(f"VERIFY {record['result'].upper()}: {path.relative_to(root)}"); return 0 if record["result"] == "pass" else 1
        if args.command == "accept": accept(root, mission, args.run_id, args.verification_sha256, args.accepted_by); print("ACCEPT OK"); return 0
        audit(root, mission, args.require_workers); print(f"VERIFY OK: {mission.relative_to(root)}"); return 0
    except VerificationError as exc: print(f"VERIFY FAIL: {exc}", file=sys.stderr); return 1


if __name__ == "__main__": sys.exit(main())
