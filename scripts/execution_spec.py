#!/usr/bin/env python3
"""Immutable, canonical ExecutionSpec construction and persistence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

FIELDS = frozenset(("schema_version", "run_id", "mission", "work_unit", "role", "feature",
                    "provider", "model", "effort", "speed", "repo", "base_commit",
                    "attempt", "prompt"))
ROLES = frozenset(("brain", "worker"))
PROVIDERS = frozenset(("codex", "claude", "agent", "agy"))
COMMIT = re.compile(r"^[0-9a-fA-F]{40,64}$")


class SpecError(ValueError):
    """The supplied execution authorization is not safe to persist or launch."""


def canonical_bytes(spec):
    """Return the one canonical on-disk representation used for hashing."""
    return (json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def spec_sha256(spec_bytes):
    return hashlib.sha256(spec_bytes).hexdigest()


def _nonempty(spec, name):
    value = spec.get(name)
    if not isinstance(value, str) or not value or value.strip() != value:
        raise SpecError(f"{name} must be a non-empty trimmed string")
    return value


def _repo(value):
    if (not isinstance(value, str) or not value or value.strip() != value or
            "\r" in value or "\n" in value):
        raise SpecError("repo must be a non-empty trimmed absolute path")
    path = Path(value)
    if not path.is_absolute() or not path.is_dir() or path != path.resolve():
        raise SpecError("repo must be an existing canonical absolute directory")
    try:
        top = subprocess.check_output(["git", "-C", str(path), "rev-parse", "--show-toplevel"], text=True).strip()
    except subprocess.CalledProcessError as exc:
        raise SpecError("repo must be a Git worktree") from exc
    if Path(top).resolve() != path:
        raise SpecError("repo must be the Git worktree root")
    return path


def validate(spec):
    """Validate exactly the Phase 1 schema and return a normalized copy."""
    if not isinstance(spec, dict) or set(spec) != FIELDS:
        missing = sorted(FIELDS - set(spec)) if isinstance(spec, dict) else sorted(FIELDS)
        extra = sorted(set(spec) - FIELDS) if isinstance(spec, dict) else []
        raise SpecError("spec fields must exactly match schema" +
                        (f"; missing={','.join(missing)}" if missing else "") +
                        (f"; extra={','.join(extra)}" if extra else ""))
    if spec["schema_version"] != 1:
        raise SpecError("schema_version must equal 1")
    try:
        parsed_uuid = uuid.UUID(spec["run_id"])
    except (ValueError, AttributeError, TypeError) as exc:
        raise SpecError("run_id must be a UUID") from exc
    if (parsed_uuid.int == 0 or parsed_uuid.variant != uuid.RFC_4122 or
            parsed_uuid.version not in range(1, 9) or
            str(parsed_uuid) != spec["run_id"]):
        raise SpecError("run_id must be a canonical UUID")
    for name in ("mission", "work_unit", "role", "provider", "model", "effort", "speed", "base_commit", "prompt"):
        _nonempty(spec, name)
    if spec["role"] not in ROLES:
        raise SpecError("role must be brain or worker")
    if spec["provider"] not in PROVIDERS:
        raise SpecError("provider must be codex, claude, agent, or agy")
    feature = spec["feature"]
    if spec["role"] == "worker":
        if not isinstance(feature, str) or not feature or feature.strip() != feature:
            raise SpecError("worker feature must be a non-empty trimmed string")
    elif feature is not None:
        raise SpecError("brain feature must be JSON null")
    if isinstance(spec["attempt"], bool) or not isinstance(spec["attempt"], int) or spec["attempt"] < 1:
        raise SpecError("attempt must be a positive integer")
    repo = _repo(spec["repo"])
    if not COMMIT.fullmatch(spec["base_commit"]):
        raise SpecError("base_commit must be a full Git object ID")
    try:
        resolved = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "--verify", f"{spec['base_commit']}^{{commit}}"], text=True
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise SpecError("base_commit must name a commit in repo") from exc
    if resolved.lower() != spec["base_commit"].lower():
        raise SpecError("base_commit must be a resolved commit ID")
    return dict(spec)


def _fsync_directory(directory):
    """Durably record a directory entry update on platforms that support it."""
    directory_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def persist(spec, before_publish=None):
    """Atomically create the UUID-keyed spec file; never replace an existing ID."""
    validated = validate(spec)
    data = canonical_bytes(validated)
    destination = Path(validated["repo"]) / ".tasks" / "specs" / f"{validated['run_id']}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{validated['run_id']}.", suffix=".tmp", dir=destination.parent)
        temp_path = Path(temp_name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), 0o400)
        if before_publish is not None:
            before_publish()
        try:
            os.link(temp_path, destination)
        except FileExistsError as exc:
            raise SpecError(f"run_id already exists: {validated['run_id']}") from exc
        _fsync_directory(destination.parent)
        temp_path.unlink()
        temp_path = None
        _fsync_directory(destination.parent)
    finally:
        if temp_path is not None:
            # A failure before link publication must not leave a final spec behind.
            # The staging name is safe to remove because it is never an authorization.
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
    return destination, spec_sha256(data)


def load_persisted(path):
    """Load a canonical, correctly named persisted spec for the provider adapter."""
    path = Path(path)
    try:
        data = path.read_bytes()
        parsed = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpecError(f"cannot read persisted spec: {exc}") from exc
    validated = validate(parsed)
    expected = Path(validated["repo"]) / ".tasks" / "specs" / f"{validated['run_id']}.json"
    if path.resolve() != expected:
        raise SpecError("persisted spec path does not match its repo and run_id")
    if data != canonical_bytes(validated):
        raise SpecError("persisted spec is not canonical bytes")
    return validated, data


def _read_input(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecError(f"cannot read spec input: {exc}") from exc


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "persist"):
        command = sub.add_parser(name)
        command.add_argument("--input", required=True, help="JSON authorization input")
    args = parser.parse_args()
    try:
        spec = _read_input(args.input)
        if args.command == "validate":
            validated = validate(spec)
            data = canonical_bytes(validated)
            print(json.dumps({"sha256": spec_sha256(data), "spec": validated}, sort_keys=True, separators=(",", ":")))
        else:
            path, digest = persist(spec)
            print(json.dumps({"path": str(path), "sha256": digest}, sort_keys=True, separators=(",", ":")))
    except SpecError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
