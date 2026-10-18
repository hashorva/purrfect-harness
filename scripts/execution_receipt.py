#!/usr/bin/env python3
"""Strict UUID-keyed ExecutionReceipt construction and validation."""
import sys
# Keep workspace files from shadowing Python's standard library when this CLI
# runs from a repository whose scripts/ contains a guarded stdlib-named file.
import os as _os
sys.path.insert(0, _os.path.dirname(_os.__file__))
import argparse
from datetime import datetime, timezone
import fnmatch
import hashlib
import importlib.machinery
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from execution_spec import artifact_directory, SpecError, load_persisted, receipt_link, spec_sha256
from observe_output import all_unknown


OUTCOMES = {"completed", "failed", "timed_out", "stalled", "interrupted", "launch_failed"}
CLAUDE_PROTECTED_FILES = ("settings.json", "settings.local.json", "CLAUDE.md", ".mcp.json")
CLAUDE_PROTECTED_DIRS = ("commands", "agents", "hooks", "skills")
HOME_PROTECTED_FILES = (
    ".zshrc", ".zshenv", ".zprofile", ".bash_profile", ".bashrc", ".gitconfig",
    ".config/git/config", ".config/git/ignore", ".config/git/attributes",
    ".gitignore", ".gitignore_global",
)
STDLIB_SHADOW_MODULES = frozenset(getattr(sys, "stdlib_module_names", ())) | {
    "argparse", "collections", "copy", "datetime", "enum", "fnmatch", "functools",
    "glob", "hashlib", "importlib", "io", "itertools", "json", "math", "os",
    "pathlib", "re", "shutil", "signal", "stat", "subprocess", "sys", "tempfile",
    "time", "unittest",
}
COMPILED_SUFFIXES = tuple(sorted(
    (set(importlib.machinery.all_suffixes()) - set(importlib.machinery.SOURCE_SUFFIXES))
    | {".pyc", ".pyo", ".pyd", ".so", ".dylib"}))
_PROTECTED_BASELINES = {}
COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
RFC3339 = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
SOURCES = {"observed", "estimated", "unknown"}
USAGE_FIELDS = ("input", "output", "cache", "reasoning")
OBSERVATION_FIELDS = ("observed_model", "usage", "fast_state")
OBSERVATION_OPTIONAL_FIELDS = ("subagents",)
SUBAGENT_FIELDS = ("calls", "tokens")
FIELDS_V1 = {
    "schema_version", "run_id", "mission", "feature", "work_unit", "attempt", "role",
    "provider", "model", "repo", "task", "tier", "started_at", "finished_at",
    "outcome", "exit_code", "log_path", "execution_spec_path", "execution_spec_sha256",
    "requested_configuration", "resolved_configuration", "observed_configuration",
    "git_before", "git_after", "commits", "changed_paths", "workspace_changed", "scope",
}
FIELDS = FIELDS_V1 | {"observation"}
GIT_FIELDS = {"head", "status_porcelain_v1_z_sha256", "status_entry_count", "dirty_paths"}


class ReceiptError(ValueError):
    """Execution evidence is missing, contradictory, or unsafe to trust."""


def fail(message):
    raise ReceiptError(message)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def git_bytes(repo, *args, check=True):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if check and result.returncode != 0:
        fail(f"Git evidence command failed: {' '.join(args)}")
    return result


def nul_paths(raw, label):
    try:
        values = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    except UnicodeDecodeError as exc:
        raise ReceiptError(f"{label} contains a non-UTF-8 path") from exc
    normalized = []
    for value in values:
        clean = value[:-1] if len(value) > 1 and value.endswith("/") else value
        if (not clean or clean.startswith("/") or
                any(part in {"", ".", ".."} for part in clean.split("/"))):
            fail(f"{label} contains a path outside the workspace")
        normalized.append(clean)
    return normalized


def _is_gitignore_path(path):
    return path == ".gitignore" or path.endswith("/.gitignore")


def _is_stdlib_shadow(path):
    parts = path.split("/")
    under = parts[0] in {"scripts", "tests"}
    if under:
        parts = parts[1:]
    if not parts or not parts[0]:
        return False
    name = parts[-1]
    if (under or len(parts) == 1) and any(
            name.endswith(suffix) and name[:-len(suffix)] in STDLIB_SHADOW_MODULES
            for suffix in importlib.machinery.all_suffixes()):
        return True
    return len(parts) > 1 and parts[0] in STDLIB_SHADOW_MODULES


def _is_compiled_module(path):
    parts = path.split("/")
    return parts[0] != ".tasks" and ("__pycache__" in parts or parts[-1].endswith(COMPILED_SUFFIXES))


def _base_root_gitignore_lines(repo, base_commit="HEAD"):
    ref = base_commit if isinstance(base_commit, str) and base_commit and not base_commit.startswith("-") else "HEAD"
    result = git_bytes(repo, "show", f"{ref}:.gitignore", check=False)
    if result.returncode != 0:
        return []
    return [line for raw in result.stdout.decode("utf-8", "surrogateescape").splitlines()
            if (line := raw.strip()) and not line.startswith(("#", "!"))]


def _is_harness_ignored(path, ignore_lines):
    clean_path = path[:-1] if len(path) > 1 and path.endswith("/") else path
    parts = clean_path.split("/")
    if parts[0] == ".tasks":
        return True
    if (_is_gitignore_path(clean_path) or _is_stdlib_shadow(clean_path)
            or _is_compiled_module(clean_path)):
        return False
    if parts[-1] == ".DS_Store":
        return True
    for rule in ignore_lines:
        clean = rule.lstrip("/")
        if clean.endswith("/"):
            prefix = clean.rstrip("/")
            if prefix and (clean_path == prefix or clean_path.startswith(prefix + "/") or
                           ("/" not in prefix and not rule.startswith("/") and prefix in parts[:-1])):
                return True
        elif clean and fnmatch.fnmatchcase(clean_path, clean):
            return True
    return False


def dirty_paths(repo, reference="HEAD", base_commit=None):
    tracked = git_bytes(repo, "diff", "--no-renames", "--name-only", "-z", reference, "--").stdout
    untracked_raw = git_bytes(repo, "ls-files", "--others", "-z", "--").stdout
    ignore_lines = _base_root_gitignore_lines(repo, base_commit if base_commit is not None else reference)
    untracked = [path for path in nul_paths(untracked_raw, "untracked Git delta")
                 if not _is_harness_ignored(path, ignore_lines)]
    return sorted(set(nul_paths(tracked, "tracked Git delta") + untracked))


def _protected_digest(path):
    if path.is_symlink():
        link_hash = hashlib.sha256(os.readlink(path).encode("utf-8", "surrogateescape")).hexdigest()
        if path.is_file():
            body_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            payload = f"symlink:{link_hash}:file:{body_hash}"
        elif path.is_dir():
            entries = []
            for child in sorted(path.rglob("*")):
                digest = _protected_digest(child)
                if digest is not None:
                    entries.append((child.relative_to(path).as_posix(), digest))
            dir_hash = hashlib.sha256(canonical_bytes(entries)).hexdigest()
            payload = f"symlink:{link_hash}:dir:{dir_hash}"
        else:
            payload = f"symlink:{link_hash}:missing"
        return hashlib.sha256(payload.encode("ascii")).hexdigest()
    if path.is_file():
        return hashlib.sha256(b"file:" + path.read_bytes()).hexdigest()
    return None


def _protected_tree(snap, root, prefix):
    if root.is_symlink():
        snap[prefix] = _protected_digest(root)
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        digest = _protected_digest(path)
        if digest is not None:
            snap[f"{prefix}/{relative}"] = digest


def _protected_file(snap, path, label):
    digest = _protected_digest(path)
    if digest is not None:
        snap[label] = digest


def _protected_symlink_target(snap, path, label):
    if path.is_symlink():
        link_hash = hashlib.sha256(os.readlink(path).encode("utf-8", "surrogateescape")).hexdigest()
        snap[label] = hashlib.sha256(f"symlink:{link_hash}".encode("ascii")).hexdigest()


# Only MCP and hook configuration inside ~/.claude.json is protected; the file is rewritten constantly by running Claude sessions.
def _claude_json_config_bytes(raw):
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    mcp_servers = data.get("mcpServers")
    if mcp_servers is None:
        mcp_servers = {}
    hooks = data.get("hooks")
    if hooks is None:
        hooks = {}
    projects_raw = data.get("projects")
    if projects_raw is None:
        projects = {}
    elif isinstance(projects_raw, dict):
        projects = {}
        for proj_path, proj_val in sorted(projects_raw.items()):
            if not isinstance(proj_val, dict):
                continue
            proj_mcp = proj_val.get("mcpServers")
            if proj_mcp is None:
                proj_mcp = {}
            proj_hooks = proj_val.get("hooks")
            if proj_hooks is None:
                proj_hooks = {}
            if proj_mcp != {} or proj_hooks != {}:
                projects[proj_path] = {"hooks": proj_hooks, "mcpServers": proj_mcp}
    else:
        projects = projects_raw
    return canonical_bytes({"hooks": hooks, "mcpServers": mcp_servers, "projects": projects})


def _protected_claude_json(snap, path, label="~/.claude.json"):
    if not path.is_symlink() and not path.is_file():
        return
    if path.is_file():
        config_bytes = _claude_json_config_bytes(path.read_bytes())
        if config_bytes is not None:
            if path.is_symlink():
                link_hash = hashlib.sha256(os.readlink(path).encode("utf-8", "surrogateescape")).hexdigest()
                cfg_hash = hashlib.sha256(config_bytes).hexdigest()
                snap[label] = hashlib.sha256(f"symlink:{link_hash}:claude-json:{cfg_hash}".encode("ascii")).hexdigest()
                return
            snap[label] = hashlib.sha256(b"claude-json:" + config_bytes).hexdigest()
            return
    _protected_file(snap, path, label)


def protected_snapshot(repo):
    """Return a deterministic digest map for paths that must not change during a run."""
    repo = Path(repo)
    home = Path(os.environ.get("HOME") or str(Path.home()))
    snap = {}
    _protected_file(snap, repo / ".git" / "config", ".git/config")
    _protected_file(snap, repo / ".git" / "info" / "exclude", ".git/info/exclude")
    _protected_tree(snap, repo / ".git" / "hooks", ".git/hooks")
    ls_files = git_bytes(repo, "ls-files", "-v", "-z", check=False)
    if ls_files.returncode == 0:
        for item in ls_files.stdout.split(b"\0"):
            if len(item) > 2 and item[1:2] == b" ":
                flag = item[:1].decode("ascii", "replace")
                rel = item[2:].decode("utf-8", "surrogateescape")
                if flag != "H":
                    snap[f".git/index-flags/{rel}"] = f"flag:{flag}"
    for rel in HOME_PROTECTED_FILES:
        _protected_file(snap, home / rel, f"~/{rel}")
    gitignore_prune = {".git", ".tasks", "__pycache__"}
    for current, dirs, files in os.walk(repo):
        dirs[:] = sorted(name for name in dirs if name not in gitignore_prune)
        for name in files:
            if name == ".gitignore":
                path = Path(current) / name
                _protected_file(snap, path, path.relative_to(repo).as_posix())
    config = subprocess.run(
        ["git", "-C", str(repo), "config", "--includes", "--get-all", "core.excludesFile"],
        env={**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")},
        capture_output=True, check=False,
    )
    entries = []
    if config.returncode == 0 and config.stdout:
        for val in config.stdout.decode("utf-8", "surrogateescape").splitlines():
            if not val:
                continue
            target = home / val[2:] if val.startswith("~/") else Path(val) if Path(val).is_absolute() else repo / val
            entries.append([val, _protected_digest(target)])
    if entries:
        snap["core.excludesFile"] = hashlib.sha256(canonical_bytes(entries)).hexdigest()
    _protected_claude_json(snap, home / ".claude.json")
    _protected_tree(snap, home / ".ssh", "~/.ssh")
    _protected_tree(snap, home / "Library" / "LaunchAgents", "~/Library/LaunchAgents")
    claude = home / ".claude"
    if claude.is_symlink():
        _protected_symlink_target(snap, claude, "~/.claude")
    for name in CLAUDE_PROTECTED_FILES:
        _protected_file(snap, claude / name, f"~/.claude/{name}")
    for name in CLAUDE_PROTECTED_DIRS:
        _protected_tree(snap, claude / name, f"~/.claude/{name}")
    projects_root = claude / "projects"
    if projects_root.is_symlink():
        _protected_symlink_target(snap, projects_root, "~/.claude/projects")
    if projects_root.is_dir():
        for proj in sorted(projects_root.iterdir()):
            if not (proj.is_dir() or proj.is_symlink()):
                continue
            mem = proj / "memory"
            prefix = f"~/.claude/projects/{proj.name}/memory"
            if mem.is_dir() and not mem.is_symlink():
                _protected_tree(snap, mem, prefix)
            else:
                _protected_file(snap, mem, prefix)
    return snap


def _protected_snapshot_file(spec, create=False):
    return artifact_directory(spec["repo"], "specs", create=create) / f"{spec['run_id']}.protected"


def protected_violations(spec, protected_before=None, finalize=False):
    path = _protected_snapshot_file(spec, create=False)
    baseline_violation = f"<protected:.tasks/specs/{spec['run_id']}.protected>"
    if not finalize:
        try:
            if path.is_symlink() or not path.is_file():
                return [baseline_violation]
            raw = path.read_bytes()
            stored = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return [baseline_violation]
        if (not isinstance(stored, dict) or set(stored) != {"before", "violations"} or
                not isinstance(stored["before"], dict) or not isinstance(stored["violations"], list) or
                raw != canonical_bytes(stored)):
            return [baseline_violation]
        return list(stored["violations"])

    memory_before = protected_before if protected_before is not None else _PROTECTED_BASELINES.get(spec["run_id"])
    tampered = False
    if memory_before is not None:
        expected_raw = canonical_bytes({"before": memory_before})
        tampered = path.is_symlink() or not path.is_file()
        if not tampered:
            try:
                tampered = path.read_bytes() != expected_raw
            except OSError:
                tampered = True
        before_snap = memory_before
    else:
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError("invalid protected baseline")
            raw = path.read_bytes()
            stored = json.loads(raw)
            if (not isinstance(stored, dict) or set(stored) != {"before"} or
                    not isinstance(stored["before"], dict) or raw != canonical_bytes(stored)):
                raise ValueError("invalid protected baseline")
            before_snap = stored["before"]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            tampered = True
            before_snap = {}
    after_snap = protected_snapshot(spec["repo"])
    keys = sorted(set(before_snap) | set(after_snap))
    violations = [f"<protected:{key}>" for key in keys if before_snap.get(key) != after_snap.get(key)]
    if tampered:
        violations = sorted(set(violations + [baseline_violation]))
    record = canonical_bytes({"before": before_snap, "violations": violations})
    if path.is_symlink():
        path.unlink()
    if path.exists():
        path.chmod(0o600)
    path.write_bytes(record)
    path.chmod(0o400)
    return violations


def snapshot(repo, base_commit=None):
    repo = Path(repo)
    head = git_bytes(repo, "rev-parse", "HEAD").stdout.decode().strip().lower()
    status = git_bytes(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    dirty = dirty_paths(repo, "HEAD", base_commit=base_commit if base_commit is not None else head)
    return {
        "head": head,
        "status_porcelain_v1_z_sha256": hashlib.sha256(status).hexdigest(),
        "status_entry_count": max(len([item for item in status.split(b"\0") if item]), len(dirty)) if dirty else 0,
        "dirty_paths": dirty,
    }


def capture_before(spec_path, digest):
    spec, raw = load_persisted(spec_path)
    if spec_sha256(raw) != digest:
        fail("execution spec SHA-256 does not match authorization")
    if spec["schema_version"] not in {2, 3}:
        fail("execution receipts require ExecutionSpec v2 or v3")
    before = snapshot(spec["repo"])
    if before["head"] != spec["base_commit"]:
        fail("Git HEAD before launch does not match the authorized base commit")
    if before["status_entry_count"] != 0 or before["dirty_paths"] or before["status_porcelain_v1_z_sha256"] != hashlib.sha256(b"").hexdigest():
        fail("workspace must be clean at the attributable before snapshot")
    before_snap = protected_snapshot(spec["repo"])
    _PROTECTED_BASELINES[spec["run_id"]] = dict(before_snap)
    protected_path = _protected_snapshot_file(spec, create=True)
    protected_path.write_bytes(canonical_bytes({"before": before_snap}))
    protected_path.chmod(0o400)
    return before


def glob_regex(pattern):
    output = ["^"]
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                output.append(".*")
                index += 2
                continue
            output.append("[^/]*")
        elif char == "?":
            output.append("[^/]")
        else:
            output.append(re.escape(char))
        index += 1
    output.append("$")
    return re.compile("".join(output))


def in_scope(path, allowed):
    if _is_gitignore_path(path) or _is_stdlib_shadow(path) or _is_compiled_module(path):
        return False
    return any(glob_regex(pattern).fullmatch(path) for pattern in allowed)


def git_delta(spec, before, protected_before=None):
    repo = Path(spec["repo"])
    base = before["head"]
    after = snapshot(repo, base_commit=base)
    after_head = after["head"]
    ancestor = git_bytes(repo, "merge-base", "--is-ancestor", base, after_head, check=False).returncode == 0
    commits_raw = git_bytes(repo, "rev-list", "--reverse", f"{base}..{after_head}").stdout
    commits = [line for line in commits_raw.decode().splitlines() if line]
    changed = dirty_paths(repo, base, base_commit=base)
    violations = [path for path in changed if not in_scope(path, spec["write_scope"])]
    violations = sorted(set(violations + protected_violations(spec, protected_before=protected_before, finalize=True)))
    if not ancestor:
        violations = sorted(set(violations + ["<history-diverged>"]))
    return after, commits, changed, {
        "result": "pass" if not violations else "fail",
        "allowed": list(spec["write_scope"]),
        "violations": violations,
        "guarantee": "Git-visible changes in the declared workspace only",
    }


def _atomic_create(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        fd, name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
        temp = Path(name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), 0o400)
        try:
            os.link(temp, path)
        except FileExistsError as exc:
            raise ReceiptError(f"execution receipt already exists for run_id {path.stem}") from exc
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temp is not None:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass


def _timestamp(value, name):
    if not isinstance(value, str) or not RFC3339.fullmatch(value):
        fail(f"{name} must be an RFC3339 UTC timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReceiptError(f"{name} must be an RFC3339 UTC timestamp") from exc


def _log_path(spec, supplied):
    repo = Path(spec["repo"])
    path = Path(supplied)
    absolute = path if path.is_absolute() else repo / path
    expected = repo / ".tasks/logs" / f"{spec['run_id']}.log"
    if absolute.resolve(strict=False) != expected.resolve(strict=False):
        fail("log path must be UUID-keyed for the same run")
    try:
        artifact_directory(repo, "logs", create=False)
    except SpecError as exc:
        raise ReceiptError(str(exc)) from exc
    if not absolute.is_file() or absolute.is_symlink():
        fail("execution log is missing or not a regular file")
    return expected.relative_to(repo).as_posix()


def validate_observation(observation):
    if (not isinstance(observation, dict)
            or not set(OBSERVATION_FIELDS) <= set(observation)
            or set(observation) - set(OBSERVATION_FIELDS + OBSERVATION_OPTIONAL_FIELDS)):
        fail("observation block has invalid fields")
    for name in ("observed_model", "fast_state"):
        _validate_sourced_scalar(f"observation.{name}", observation[name], "text")
    usage = observation["usage"]
    if not isinstance(usage, dict) or set(usage) != set(USAGE_FIELDS):
        fail("observation.usage has invalid fields")
    for name in USAGE_FIELDS:
        _validate_sourced_scalar(f"observation.usage.{name}", usage[name], "count")
    if "subagents" in observation:
        subagents = observation["subagents"]
        if not isinstance(subagents, dict) or set(subagents) != set(SUBAGENT_FIELDS):
            fail("observation.subagents has invalid fields")
        for name in SUBAGENT_FIELDS:
            _validate_sourced_scalar(f"observation.subagents.{name}", subagents[name], "count")


def _validate_sourced_scalar(label, item, kind):
    if not isinstance(item, dict) or set(item) != {"value", "source"}:
        fail(f"{label} has invalid shape")
    source = item["source"]
    value = item["value"]
    if source not in SOURCES:
        fail(f"{label} source is invalid")
    if source == "unknown":
        if value is not None:
            fail(f"{label} must be null when source is unknown")
        return
    if value is None:
        fail(f"{label} cannot be null when source is {source}")
    if kind == "text":
        if not isinstance(value, str) or not value:
            fail(f"{label} must be non-empty text")
    elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
        fail(f"{label} must be a non-negative integer")


def build_receipt(*, spec_path, digest, before, started_at, finished_at, outcome,
                  exit_code, log_path, task=None, tier=None, observation=None, protected_before=None):
    spec, raw = load_persisted(spec_path)
    if spec_sha256(raw) != digest:
        fail("execution spec SHA-256 does not match exact persisted bytes")
    if spec["schema_version"] not in {2, 3}:
        fail("execution receipts require ExecutionSpec v2 or v3")
    linked = receipt_link(
        run_id=spec["run_id"], path=spec_path, digest=digest, role=spec["role"],
        mission=spec["mission"], work_unit=spec["work_unit"],
        provider=spec["provider"], model=spec["model"],
    )
    if outcome not in OUTCOMES:
        fail("terminal outcome is invalid")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code < 0 or exit_code > 255:
        fail("exit_code must be an integer from 0 through 255")
    if outcome == "completed" and exit_code != 0:
        fail("completed outcome requires exit_code 0")
    if outcome != "completed" and exit_code == 0:
        fail("non-completed outcome requires a nonzero exit_code")
    started = _timestamp(started_at, "started_at")
    finished = _timestamp(finished_at, "finished_at")
    if finished < started:
        fail("finished_at cannot precede started_at")
    if not isinstance(before, dict) or set(before) != GIT_FIELDS:
        fail("git_before has invalid fields")
    if before["head"] != spec["base_commit"] or before["status_entry_count"] != 0 or before["dirty_paths"]:
        fail("git_before is not the clean authorized base state")
    after, commits, changed, scope = git_delta(spec, before, protected_before=protected_before)
    workspace_changed = before["head"] != after["head"] or bool(changed)
    if observation is None:
        observation = all_unknown()
    validate_observation(observation)
    receipt = {
        "schema_version": 2,
        "run_id": spec["run_id"],
        "mission": spec["mission"],
        "feature": spec["feature"],
        "work_unit": spec["work_unit"],
        "attempt": spec["attempt"],
        "role": spec["role"],
        "provider": spec["provider"],
        "model": spec["model"],
        "repo": spec["repo"],
        "task": task,
        "tier": tier,
        "started_at": started_at,
        "finished_at": finished_at,
        "outcome": outcome,
        "exit_code": exit_code,
        "log_path": _log_path(spec, log_path),
        "execution_spec_path": str(Path(spec_path)),
        "execution_spec_sha256": digest,
        "requested_configuration": linked["requested"],
        "resolved_configuration": linked["resolved"],
        "observed_configuration": linked["observed"],
        "git_before": before,
        "git_after": after,
        "commits": commits,
        "changed_paths": changed,
        "workspace_changed": workspace_changed,
        "scope": scope,
        "observation": observation,
    }
    validate_receipt(receipt, receipt_path=None)
    return receipt


def write_receipt(**kwargs):
    receipt = build_receipt(**kwargs)
    try:
        destination = artifact_directory(receipt["repo"], "receipts") / f"{receipt['run_id']}.json"
    except SpecError as exc:
        raise ReceiptError(str(exc)) from exc
    _atomic_create(destination, canonical_bytes(receipt))
    return destination


def validate_receipt(receipt, receipt_path):
    if not isinstance(receipt, dict):
        fail("receipt must be a JSON object")
    version = receipt.get("schema_version")
    if version == 1:
        if set(receipt) != FIELDS_V1:
            fail("receipt fields must exactly match ExecutionReceipt v1")
    elif version == 2:
        if set(receipt) != FIELDS:
            fail("receipt fields must exactly match ExecutionReceipt v2")
        validate_observation(receipt["observation"])
    else:
        fail("receipt schema_version must be 1 or 2")
    spec_path = receipt.get("execution_spec_path")
    digest = receipt.get("execution_spec_sha256")
    try:
        spec, raw = load_persisted(spec_path)
    except SpecError as exc:
        raise ReceiptError(str(exc)) from exc
    if spec_sha256(raw) != digest:
        fail("receipt execution_spec_sha256 does not match exact spec bytes")
    for key in ("run_id", "mission", "feature", "work_unit", "attempt", "role", "provider", "model", "repo"):
        if receipt[key] != spec[key]:
            fail(f"receipt {key} does not match ExecutionSpec")
    expected_spec_path = Path(spec["repo"]) / ".tasks/specs" / f"{spec['run_id']}.json"
    if Path(spec_path).resolve() != expected_spec_path or receipt["execution_spec_path"] != str(expected_spec_path):
        fail("receipt execution_spec_path does not identify the exact authorization")
    if receipt["role"] == "worker":
        task = receipt["task"]
        if (not isinstance(task, str) or not task or task.strip() != task or
                Path(task).is_absolute() or ".." in Path(task).parts):
            fail("worker receipt requires a safe repository-relative task path")
        if receipt["tier"] not in {"economy", "premium"}:
            fail("worker receipt requires an economy or premium tier")
    elif receipt["task"] is not None or receipt["tier"] is not None:
        fail("brain receipt task and tier must be null")
    if receipt_path is not None:
        try:
            expected = artifact_directory(spec["repo"], "receipts", create=False) / f"{spec['run_id']}.json"
        except SpecError as exc:
            raise ReceiptError(str(exc)) from exc
        if Path(receipt_path).resolve() != expected:
            fail("receipt filename/path does not match run_id")
    _log_path(spec, receipt["log_path"])
    started = _timestamp(receipt["started_at"], "started_at")
    finished = _timestamp(receipt["finished_at"], "finished_at")
    if finished < started:
        fail("finished_at cannot precede started_at")
    if receipt["outcome"] not in OUTCOMES:
        fail("terminal outcome is invalid")
    if (isinstance(receipt["exit_code"], bool) or not isinstance(receipt["exit_code"], int) or
            receipt["exit_code"] < 0 or receipt["exit_code"] > 255):
        fail("receipt exit_code is invalid")
    if receipt["outcome"] == "completed" and receipt["exit_code"] != 0:
        fail("completed outcome requires exit_code 0")
    if receipt["outcome"] != "completed" and receipt["exit_code"] == 0:
        fail("non-completed outcome requires nonzero exit_code")
    for name in ("git_before", "git_after"):
        value = receipt[name]
        if not isinstance(value, dict) or set(value) != GIT_FIELDS:
            fail(f"{name} has invalid fields")
        if not COMMIT.fullmatch(value["head"]):
            fail(f"{name}.head must be a full commit ID")
        if not re.fullmatch(r"[0-9a-f]{64}", value["status_porcelain_v1_z_sha256"]):
            fail(f"{name} status digest is invalid")
        if isinstance(value["status_entry_count"], bool) or not isinstance(value["status_entry_count"], int) or value["status_entry_count"] < 0:
            fail(f"{name} status count is invalid")
        if not isinstance(value["dirty_paths"], list) or value["dirty_paths"] != sorted(set(value["dirty_paths"])):
            fail(f"{name} dirty_paths must be sorted and unique")
        if not all(isinstance(path, str) and path and not path.startswith("/") and
                   not any(part in {"", ".", ".."} for part in path.split("/"))
                   for path in value["dirty_paths"]):
            fail(f"{name} dirty_paths contain an invalid path")
        if (value["status_entry_count"] == 0) != (not value["dirty_paths"]):
            fail(f"{name} status count contradicts dirty paths")
    if receipt["git_before"]["head"] != spec["base_commit"] or receipt["git_before"]["status_entry_count"] != 0 or receipt["git_before"]["dirty_paths"]:
        fail("receipt before state is not the clean authorized base")
    if receipt["git_before"]["status_porcelain_v1_z_sha256"] != hashlib.sha256(b"").hexdigest():
        fail("receipt before status digest is not the clean workspace digest")
    if not isinstance(receipt["commits"], list):
        fail("receipt commits has invalid shape")
    if (not isinstance(receipt["changed_paths"], list) or
            receipt["changed_paths"] != sorted(set(receipt["changed_paths"]))):
        fail("receipt changed_paths must be sorted and unique")
    if not all(isinstance(commit, str) and COMMIT.fullmatch(commit) for commit in receipt["commits"]):
        fail("receipt commits contain an invalid object ID")
    if not all(isinstance(path, str) and path and not path.startswith("/") and
               not any(part in {"", ".", ".."} for part in path.split("/"))
               for path in receipt["changed_paths"]):
        fail("receipt changed_paths contain an invalid path")
    repo = Path(spec["repo"])
    base = receipt["git_before"]["head"]
    after_head = receipt["git_after"]["head"]
    recorded_commits = git_bytes(repo, "rev-list", "--reverse", f"{base}..{after_head}").stdout.decode().splitlines()
    if receipt["commits"] != recorded_commits:
        fail("receipt commits do not match the recorded Git range")
    committed_paths = nul_paths(
        git_bytes(repo, "diff", "--no-renames", "--name-only", "-z", base, after_head, "--").stdout,
        "recorded committed Git delta",
    )
    recorded_changed = sorted(set(committed_paths + receipt["git_after"]["dirty_paths"]))
    if receipt["changed_paths"] != recorded_changed:
        fail("receipt changed_paths do not match commits plus the recorded dirty state")
    expected_changed = base != after_head or bool(receipt["changed_paths"])
    if not isinstance(receipt["workspace_changed"], bool) or receipt["workspace_changed"] != expected_changed:
        fail("workspace_changed does not match the recorded Git delta")
    scope = receipt["scope"]
    if not isinstance(scope, dict) or set(scope) != {"result", "allowed", "violations", "guarantee"}:
        fail("receipt scope has invalid fields")
    if scope["allowed"] != spec["write_scope"] or scope["guarantee"] != "Git-visible changes in the declared workspace only":
        fail("receipt scope does not match immutable authorization")
    expected_violations = [path for path in receipt["changed_paths"] if not in_scope(path, spec["write_scope"])]
    history_diverged = git_bytes(
        repo, "merge-base", "--is-ancestor", receipt["git_before"]["head"], receipt["git_after"]["head"],
        check=False,
    ).returncode != 0
    if history_diverged:
        expected_violations = sorted(set(expected_violations + ["<history-diverged>"]))
    expected_violations = sorted(set(expected_violations + protected_violations(spec)))
    if scope["violations"] != expected_violations or scope["result"] != ("pass" if not expected_violations else "fail"):
        fail("receipt scope result contradicts changed paths")
    linked = receipt_link(
        run_id=spec["run_id"], path=spec_path, digest=digest, role=spec["role"],
        mission=spec["mission"], work_unit=spec["work_unit"], provider=spec["provider"], model=spec["model"],
    )
    for field, expected in (("requested_configuration", linked["requested"]),
                            ("resolved_configuration", linked["resolved"]),
                            ("observed_configuration", linked["observed"])):
        if receipt[field] != expected:
            fail(f"receipt {field} does not match shared adapter evidence")
    return receipt


def load_receipt(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        fail("execution receipt is missing or not a regular file")
    try:
        raw = path.read_bytes()
        receipt = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptError(f"cannot read execution receipt: {exc}") from exc
    if raw != canonical_bytes(receipt):
        fail("execution receipt is not canonical JSON")
    return validate_receipt(receipt, path)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--receipt", required=True)
    capture = commands.add_parser("capture-before")
    capture.add_argument("--spec", required=True)
    capture.add_argument("--spec-sha256", required=True)
    write = commands.add_parser("write")
    for name in ("spec", "spec-sha256", "before-json", "started-at", "finished-at", "outcome", "exit-code", "log-path"):
        write.add_argument(f"--{name}", required=True)
    write.add_argument("--task")
    write.add_argument("--tier")
    args = parser.parse_args()
    try:
        if args.command == "validate":
            receipt = load_receipt(args.receipt)
            print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        elif args.command == "capture-before":
            print(json.dumps(capture_before(args.spec, args.spec_sha256), sort_keys=True, separators=(",", ":")))
        else:
            try:
                before = json.loads(args.before_json)
                exit_code = int(args.exit_code)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ReceiptError("before-json or exit-code is malformed") from exc
            path = write_receipt(
                spec_path=args.spec, digest=args.spec_sha256, before=before,
                started_at=args.started_at, finished_at=args.finished_at,
                outcome=args.outcome, exit_code=exit_code, log_path=args.log_path,
                task=args.task, tier=args.tier,
            )
            print(path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path)
    except (ReceiptError, SpecError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
