#!/usr/bin/env python3
"""Immutable, run-bound verification records and feature acceptance policy."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile

from execution_receipt import ReceiptError, canonical_bytes, load_receipt, snapshot
from execution_spec import SpecError, load_persisted, spec_sha256
from run_id import validate_run_id


def git_command(*args):
    """Git argv for verification: gc and maintenance off, repository hooks left on.

    The shared helper also disables hooks. Drop that one pair. A post-checkout
    hook that dirties a verification worktree must still run. Fixtures copy this
    file without git_safe.py and build the same argv.
    """
    try:
        import git_safe
    except ImportError:
        git_safe = None
    if git_safe is not None:
        command = git_safe.argv(*args)
        index = command.index("core.hooksPath=/dev/null")
        del command[index - 1:index + 1]
        return command
    binary = "git"
    return [binary, "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args]


HEX = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
RFC3339 = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
GIT_FIELDS = {"head", "status_porcelain_v1_z_sha256", "status_entry_count", "dirty_paths"}
RECORD_FIELDS = {"schema_version", "run_id", "mission", "feature", "work_unit", "attempt",
                 "execution_spec", "execution_receipt", "task", "receipt_git_after",
                 "verification_git_before", "verification_git_after", "commands", "result"}
COMMAND_FIELDS = {"argv", "started_at", "finished_at", "exit_code", "stdout_sha256", "stderr_sha256"}
# Each pattern is a runner's own summary or marker anchored at column 0, so prose such as
# `identical-skipped=3`, "skips other missions" or JSON `"skipped"` never matches.
SKIP_PATTERNS = (
    ("unittest", "unittest summary reports skipped tests", re.compile(rb"^OK \(skipped=[1-9][0-9]*", re.M)),
    ("pytest", "pytest summary reports skipped tests", re.compile(rb"^=+ [^\n]*\b[1-9][0-9]* skipped\b[^\n]* =+[ \t\r]*$", re.M)),
    ("tap", "TAP line carries a skip directive", re.compile(rb"^(?:not )?ok\b[^\n#]*#[ \t]*skip\b", re.M | re.I)),
    ("marker", "output line starts with SKIP", re.compile(rb"^SKIP(?:PED)?\b", re.M)),
)
SKIP_REASONS = {name: reason for name, reason, _pattern in SKIP_PATTERNS}


class VerificationError(ValueError):
    pass


def fail(message):
    raise VerificationError(message)


def skip_kind(data):
    """Return the first runner skip pattern that matches captured bytes, else None."""
    for name, _reason, pattern in SKIP_PATTERNS:
        if pattern.search(data):
            return name
    return None


def matches(pattern, value):
    """Return false, rather than leaking TypeError, for malformed JSON values."""
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def is_run_id(value):
    """True only for a canonical run id; the rule lives in run_id.py."""
    try:
        validate_run_id(value)
    except ValueError:
        return False
    return True


def receipt_link_ok(value):
    prefix, suffix = ".tasks/receipts/", ".json"
    return (isinstance(value, str) and value.startswith(prefix) and value.endswith(suffix)
            and is_run_id(value[len(prefix):-len(suffix)]))


def require_run_id(run_id):
    """Refuse a non-canonical run id before it reaches any path, glob or existence check."""
    if not is_run_id(run_id): fail("run_id must be a canonical RFC UUID")


def safe_task_path(value):
    """Match the receipt's repository-relative task contract, plus line safety."""
    return (isinstance(value, str) and bool(value) and value.strip() == value and
            "\r" not in value and "\n" not in value and not Path(value).is_absolute() and
            ".." not in Path(value).parts)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def failure_report(index, argv, exit_code, stdout, stderr, lines=20):
    """Human-readable tail of a failed verification command (stderr then stdout)."""
    header = "VERIFY FAIL DETAIL: " + json.dumps({"command": index, "argv": argv, "exit_code": exit_code})
    stderr_lines = stderr.decode("utf-8", "replace").splitlines()
    stdout_lines = stdout.decode("utf-8", "replace").splitlines()
    tail = (stderr_lines + stdout_lines)[-lines:]
    if not tail:
        return header
    return header + "\n" + "\n".join(f"  | {line}" for line in tail)


def canonical(value):
    return canonical_bytes(value)


def root_path():
    root = Path.cwd().resolve()
    if subprocess.run(git_command("-C", str(root), "rev-parse", "--show-toplevel"), capture_output=True).returncode:
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
            # Set the final mode while this name is still private.  A chmod after
            # replace could report an error after the acceptance mutation landed.
            handle.write(data); handle.flush(); os.fchmod(handle.fileno(), mode); os.fsync(handle.fileno())
        os.replace(temporary, path)
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
    got = subprocess.run(git_command("-C", str(root), "show", f"{receipt['git_before']['head']}:{task}"), capture_output=True)
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
    if not is_run_id(run_id): fail("run_id must be a canonical RFC UUID")
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
    require_run_id(run_id)
    record_dir = mission / "verification"
    base = record_dir / f"{run_id}.json"
    destination = base
    if base.exists():
        number = 2
        while (record_dir / f"{run_id}.{number}.json").exists():
            number += 1
        destination = record_dir / f"{run_id}.{number}.json"
    receipt, receipt_path, spec_path, spec_raw, task, task_raw, commands = bind(root, mission, run_id)
    if receipt["git_after"]["status_entry_count"] != 0 or receipt["git_after"]["dirty_paths"]:
        fail("worktree verification needs a clean receipt git_after")

    subprocess.run(git_command("-C", str(root), "worktree", "prune"), check=True,
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    temporary_root = Path(tempfile.mkdtemp(prefix="purrfect-verify-"))
    worktree = temporary_root / "wt"
    added = False
    outcomes = []
    passed = True
    before = after = None
    prev_sigterm = None
    try:
        def on_sigterm(_signum, _frame):
            raise SystemExit(143)

        prev_sigterm = signal.signal(signal.SIGTERM, on_sigterm)
        subprocess.run(git_command("-C", str(root), "worktree", "add", "--detach", "--quiet",
                        str(worktree), receipt["git_after"]["head"]), check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        added = True
        before = snapshot(worktree)
        if before != receipt["git_after"]:
            fail("verification worktree snapshot does not equal receipt git_after before checks")
        command_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                       "PURRFECT_LIVE_ROOT": str(root)}
        for argv in commands:
            started = now()
            try:
                completed = subprocess.run(argv, cwd=worktree, stdin=subprocess.DEVNULL,
                                           capture_output=True, env=command_env)
                exit_code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
            except OSError as exc:
                exit_code, stdout, stderr = 127, b"", str(exc).encode("utf-8", "replace")
            finished = now()
            outcome = {"argv": argv, "started_at": started, "finished_at": finished,
                       "exit_code": exit_code, "stdout_sha256": digest(stdout),
                       "stderr_sha256": digest(stderr)}
            skipped = skip_kind(stdout) or skip_kind(stderr)
            if skipped:
                # Report the argv and the reason only; captured output is never printed or stored.
                outcome["skip_detected"] = skipped
                print(f"VERIFY SKIP: command {len(outcomes) + 1} {json.dumps(argv)[:200]} reported skipped checks ({SKIP_REASONS[skipped]})", file=sys.stderr)
            outcomes.append(outcome)
            passed = passed and exit_code == 0 and not skipped
            if exit_code != 0 and not skipped:
                sys.stderr.write(failure_report(len(outcomes), argv, exit_code, stdout, stderr) + "\n")
        after = snapshot(worktree)
        if after != receipt["git_after"]: passed = False
    finally:
        cleanup_failed = False
        if added:
            try:
                subprocess.run(git_command("-C", str(root), "worktree", "remove", "--force", str(worktree)),
                               check=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
            except (OSError, subprocess.CalledProcessError):
                cleanup_failed = True
        try:
            subprocess.run(git_command("-C", str(root), "worktree", "prune"), check=True,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (OSError, subprocess.CalledProcessError):
            cleanup_failed = True
        try:
            import shutil
            shutil.rmtree(temporary_root)
        except OSError:
            cleanup_failed = True
        if cleanup_failed:
            print(f"WARN: verification worktree cleanup failed: {worktree}", file=sys.stderr)
        if prev_sigterm is not None:
            signal.signal(signal.SIGTERM, prev_sigterm)
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
    if not is_run_id(record["run_id"]) or not isinstance(record["result"], str) or record["result"] not in {"pass", "fail"}: fail("VerificationRecord has invalid identity or result")
    for field in ("mission", "feature", "work_unit"):
        if not isinstance(record[field], str) or not record[field]: fail("VerificationRecord has invalid identity")
    if isinstance(record["attempt"], bool) or not isinstance(record["attempt"], int) or record["attempt"] < 1: fail("VerificationRecord attempt is invalid")
    for item in (record["execution_spec"], record["execution_receipt"], record["task"]):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not matches(HEX, item.get("sha256")): fail("VerificationRecord link is invalid")
    if set(record["execution_spec"]) != {"path", "sha256"} or not Path(record["execution_spec"]["path"]).is_absolute(): fail("VerificationRecord spec link is invalid")
    if set(record["execution_receipt"]) != {"path", "sha256"} or not receipt_link_ok(record["execution_receipt"]["path"]): fail("VerificationRecord receipt link is invalid")
    if set(record["task"]) != {"path", "sha256", "git_commit"} or not safe_task_path(record["task"]["path"]) or not matches(COMMIT, record["task"]["git_commit"]): fail("VerificationRecord task link is invalid")
    for name in ("receipt_git_after", "verification_git_before", "verification_git_after"):
        state = record[name]
        if not isinstance(state, dict) or set(state) != GIT_FIELDS or not matches(COMMIT, state.get("head")) or not matches(HEX, state.get("status_porcelain_v1_z_sha256")) or isinstance(state.get("status_entry_count"), bool) or not isinstance(state.get("status_entry_count"), int) or state["status_entry_count"] < 0 or not isinstance(state.get("dirty_paths"), list) or not all(isinstance(p, str) and p and not p.startswith("/") and ".." not in p.split("/") for p in state["dirty_paths"]): fail("VerificationRecord Git snapshot is invalid")
    if not isinstance(record["commands"], list) or not record["commands"]: fail("VerificationRecord commands are invalid")
    for command in record["commands"]:
        if (not isinstance(command, dict) or
                not COMMAND_FIELDS <= set(command) <= COMMAND_FIELDS | {"skip_detected"} or
                not isinstance(command["argv"], list) or not command["argv"] or
                not all(isinstance(v, str) and v for v in command["argv"])): fail("VerificationRecord command is invalid")
        if "skip_detected" in command and (not isinstance(command["skip_detected"], str) or command["skip_detected"] not in SKIP_REASONS): fail("VerificationRecord command skip is invalid")
        if not isinstance(command["exit_code"], int) or isinstance(command["exit_code"], bool) or not matches(RFC3339, command["started_at"]) or not matches(RFC3339, command["finished_at"]) or not matches(HEX, command["stdout_sha256"]) or not matches(HEX, command["stderr_sha256"]): fail("VerificationRecord command evidence is invalid")
        try:
            started = datetime.fromisoformat(command["started_at"].replace("Z", "+00:00"))
            finished = datetime.fromisoformat(command["finished_at"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise VerificationError("VerificationRecord command timestamps are invalid") from exc
        if finished < started: fail("VerificationRecord command timestamps are out of order")
    return record


def load_record(path):
    if not path.is_file() or path.is_symlink(): fail("VerificationRecord is missing or not regular")
    try: raw = path.read_bytes(); record = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc: raise VerificationError(f"cannot read VerificationRecord: {exc}") from exc
    if raw != canonical(record): fail("VerificationRecord is not canonical JSON")
    return validate_record(record), raw


def run_records(mission, run_id):
    """Return a run's numbered record paths, rejecting noncanonical suffixes."""
    require_run_id(run_id)
    record_dir = mission / "verification"
    paths = {}
    base = record_dir / f"{run_id}.json"
    if base.exists() or base.is_symlink():
        paths[1] = base
    for path in record_dir.glob(f"{run_id}.*.json"):
        suffix = path.name[len(run_id) + 1:-5]
        if not suffix.isdecimal() or suffix.startswith("0") or int(suffix) < 2:
            fail(f"VerificationRecord has invalid number: {path.name}")
        number = int(suffix)
        if number in paths:
            fail(f"VerificationRecord number is duplicated: {path.name}")
        paths[number] = path
    return paths


def record_for_hash(mission, run_id, expected_hash):
    paths = run_records(mission, run_id)
    matches_for_hash = []
    for path in paths.values():
        record, raw = load_record(path)
        if digest(raw) == expected_hash:
            matches_for_hash.append((record, raw))
    if len(matches_for_hash) != 1:
        fail("verification hash must identify exactly one record for this run")
    return matches_for_hash[0]


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
    command_ok = all(item["exit_code"] == 0 and "skip_detected" not in item for item in record["commands"])
    if (record["result"] == "pass") != command_ok:
        fail("VerificationRecord result contradicts command outcomes")
    return receipt


def accept(root, mission, run_id, expected_hash, accepted_by):
    require_run_id(run_id)
    if not matches(HEX, expected_hash) or not isinstance(accepted_by, str) or not accepted_by.strip() or accepted_by.strip() != accepted_by: fail("verification hash or accepted_by is invalid")
    lock_dir = root / ".tasks/locks"
    if os.environ.get("PURRFECT_DISPATCH_LOCK_PATH") or (lock_dir.is_dir() and list(lock_dir.glob("*.lock"))):
        fail("acceptance refuses while a dispatch workspace lock exists")
    record, _raw = record_for_hash(mission, run_id, expected_hash)
    if record["run_id"] != run_id or record["result"] != "pass": fail("verification record hash does not name a passing record")
    revalidate_record(root, mission, record)
    feature_path = mission / "features.json"
    try: doc = json.loads(feature_path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc: raise VerificationError(f"cannot read features.json: {exc}") from exc
    feature_matches = [f for f in doc.get("features", []) if isinstance(f, dict) and f.get("id") == record["feature"]]
    if len(feature_matches) != 1 or feature_matches[0].get("passes") is not False or any(k in feature_matches[0] for k in ("accepted_run_id", "accepted_verification_sha256", "accepted_at", "accepted_by")): fail("feature is not in an acceptable prior state")
    feature = feature_matches[0]; feature.update({"passes": True, "accepted_run_id": run_id, "accepted_verification_sha256": expected_hash, "accepted_at": now(), "accepted_by": accepted_by})
    atomic_replace(feature_path, json.dumps(doc, indent=2, ensure_ascii=False) .encode("utf-8") + b"\n")


def audit(root, mission, require_workers=False):
    feature_path = mission / "features.json"
    try: features = json.loads(feature_path.read_text())["features"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc: raise VerificationError(f"cannot read features.json: {exc}") from exc
    if not isinstance(features, list): fail("features.json features must be an array")
    failures = []
    mission_rel = mission.relative_to(root).as_posix()
    brains = []
    receipt_dir = root / ".tasks/receipts"
    if receipt_dir.is_dir():
        for path in receipt_dir.glob("*.json"):
            if not is_run_id(path.stem):
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
        if feature.get("bootstrap") is not True:
            required = ("accepted_run_id", "accepted_verification_sha256", "accepted_at", "accepted_by")
            has_acceptance = any(k in feature for k in required)
            if type(feature.get("passes")) is not bool:
                failures.append(f"feature {feature.get('id')}: passes must be boolean"); continue
            if feature["passes"] is False:
                if has_acceptance: failures.append(f"feature {feature.get('id')}: unaccepted feature has stale acceptance evidence")
                continue
            if any(k not in feature for k in required):
                failures.append(f"feature {feature.get('id')}: missing acceptance evidence"); continue
            if (not is_run_id(feature["accepted_run_id"]) or not matches(HEX, feature["accepted_verification_sha256"])
                    or not isinstance(feature["accepted_at"], str) or not RFC3339.fullmatch(feature["accepted_at"])
                    or not isinstance(feature["accepted_by"], str) or not feature["accepted_by"].strip()
                    or feature["accepted_by"].strip() != feature["accepted_by"]):
                failures.append(f"feature {feature.get('id')}: acceptance metadata is invalid"); continue
            try:
                datetime.fromisoformat(feature["accepted_at"].replace("Z", "+00:00"))
            except ValueError:
                failures.append(f"feature {feature.get('id')}: acceptance metadata is invalid"); continue
            try:
                run_id = feature["accepted_run_id"]
                paths = run_records(mission, run_id)
                if not paths or sorted(paths) != list(range(1, max(paths) + 1)):
                    raise VerificationError("VerificationRecord numbers are not contiguous from 1")
                record, _raw = record_for_hash(mission, run_id, feature["accepted_verification_sha256"])
                if record["run_id"] != run_id or record["result"] != "pass" or record["feature"] != feature["id"]: raise VerificationError("record does not match accepted feature")
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
    if args.command in ("verify", "accept") and not is_run_id(args.run_id):
        print("VERIFY FAIL: run_id must be a canonical RFC UUID", file=sys.stderr); return 2
    try:
        root = root_path(); mission = mission_path(root, args.mission)
        if args.command == "verify":
            record, path = verify(root, mission, args.run_id); print(f"VERIFY {record['result'].upper()}: {path.relative_to(root)}"); return 0 if record["result"] == "pass" else 1
        if args.command == "accept": accept(root, mission, args.run_id, args.verification_sha256, args.accepted_by); print("ACCEPT OK"); return 0
        audit(root, mission, args.require_workers); print(f"VERIFY OK: {mission.relative_to(root)}"); return 0
    except VerificationError as exc: print(f"VERIFY FAIL: {exc}", file=sys.stderr); return 1


if __name__ == "__main__": sys.exit(main())
