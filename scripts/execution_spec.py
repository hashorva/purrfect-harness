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


FIELDS_V1 = frozenset(("schema_version", "run_id", "mission", "work_unit", "role", "feature",
                       "provider", "model", "effort", "speed", "repo", "base_commit",
                       "attempt", "prompt"))
FIELDS_V2 = FIELDS_V1 | {"write_scope"}
FIELDS_V3 = FIELDS_V2 | {"provider_contract_version"}
# Contracts 2 and 3 are retained history; contract 4 sends Cursor a plain model ID;
# contract 5 adds Codex's --add-dir <repo>/.agents when write_scope names .agents/;
# contract 6 requests machine-readable CLI output for receipt observation (F003).
# contract 7 streams Claude events and starts Claude with no MCP servers (F008).
# contract 8 streams agy events and sends agy effort only in the model name (F009).
# contract 9 unlocks Claude native tools with deny-list and protected-path guards (F010).
PROVIDER_CONTRACTS_V3 = (2, 3, 4, 5, 6, 7, 8, 9)
CURRENT_PROVIDER_CONTRACT = 9
ROLES = frozenset(("brain", "worker"))
PROVIDERS = frozenset(("codex", "claude", "agent", "agy"))
COMMIT = re.compile(r"^[0-9a-fA-F]{40,64}$")
SCOPE_GLOB = re.compile(r"^[^\x00\r\n]+$")


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


def validate_write_scope(value):
    """Validate a small repo-relative glob language used for Git-visible scope."""
    if not isinstance(value, list) or not value:
        raise SpecError("write_scope must be a non-empty array")
    normalized = []
    for pattern in value:
        if (not isinstance(pattern, str) or not pattern or pattern.strip() != pattern or
                not SCOPE_GLOB.fullmatch(pattern) or pattern.startswith("/") or "\\" in pattern):
            raise SpecError("write_scope entries must be trimmed repo-relative POSIX globs")
        parts = pattern.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise SpecError("write_scope entries must not contain empty, dot, or parent segments")
        if parts[0] in {".git", ".tasks"}:
            raise SpecError("write_scope cannot authorize .git or .tasks")
        if pattern in normalized:
            raise SpecError("write_scope entries must be unique")
        normalized.append(pattern)
    return normalized


def validate(spec):
    """Validate exactly the Phase 1 schema and return a normalized copy."""
    if not isinstance(spec, dict):
        raise SpecError("spec must be an object")
    version = spec.get("schema_version")
    fields = FIELDS_V1 if version == 1 else FIELDS_V2 if version == 2 else FIELDS_V3 if version == 3 else None
    if fields is None:
        raise SpecError("schema_version must equal 1, 2, or 3")
    if set(spec) != fields:
        missing = sorted(fields - set(spec))
        extra = sorted(set(spec) - fields)
        raise SpecError("spec fields must exactly match schema" +
                        (f"; missing={','.join(missing)}" if missing else "") +
                        (f"; extra={','.join(extra)}" if extra else ""))
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
    if version >= 2:
        validate_write_scope(spec["write_scope"])
    if version == 3 and (isinstance(spec["provider_contract_version"], bool) or
                         spec["provider_contract_version"] not in PROVIDER_CONTRACTS_V3):
        raise SpecError("provider_contract_version must equal 2, 3, 4, 5, 6, 7, 8 or 9")
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


def artifact_directory(repo, *children, create=True):
    """Return a real, in-repository .tasks directory without following symlinks."""
    root = Path(repo).resolve()
    current = root
    for component in (".tasks", *children):
        current = current / component
        if create:
            try:
                current.mkdir(exist_ok=True)
            except OSError as exc:
                raise SpecError(f"cannot create execution artifact directory {current}") from exc
        if current.is_symlink() or not current.is_dir():
            raise SpecError(f"execution artifact directory must be a real directory: {current}")
        try:
            current.resolve().relative_to(root)
        except ValueError as exc:
            raise SpecError("execution artifact directory escapes the repository") from exc
    return current


def persist(spec, before_publish=None):
    """Atomically create the UUID-keyed spec file; never replace an existing ID."""
    validated = validate(spec)
    data = canonical_bytes(validated)
    destination = artifact_directory(validated["repo"], "specs") / f"{validated['run_id']}.json"
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
    expected = artifact_directory(validated["repo"], "specs", create=False) / f"{validated['run_id']}.json"
    if path.resolve() != expected:
        raise SpecError("persisted spec path does not match its repo and run_id")
    if data != canonical_bytes(validated):
        raise SpecError("persisted spec is not canonical bytes")
    return validated, data


def construct(*, role, mission, feature, work_unit, attempt, provider, model, effort, speed,
              repo, prompt, write_scope, run_id=None):
    """Build and persist a fresh execution authorization from resolved launch inputs."""
    try:
        base_commit = subprocess.check_output(
            ["git", "-C", repo, "rev-parse", "HEAD"], text=True
        ).strip().lower()
    except subprocess.CalledProcessError as exc:
        raise SpecError("cannot resolve current Git commit") from exc
    spec = {
        "schema_version": 3,
        "run_id": run_id or str(uuid.uuid4()),
        "mission": mission,
        "work_unit": work_unit,
        "role": role,
        "feature": feature,
        "provider": provider,
        "model": model,
        "effort": effort,
        "speed": speed,
        "repo": repo,
        "base_commit": base_commit,
        "attempt": attempt,
        "prompt": prompt,
        "write_scope": write_scope,
        "provider_contract_version": CURRENT_PROVIDER_CONTRACT,
    }
    path, digest = persist(spec)
    return spec, path, digest


def receipt_link(*, run_id, path, digest, role, mission, work_unit, provider, model):
    """Fail closed unless receipt identity is backed by the exact persisted bytes."""
    if not re.fullmatch(r"[0-9a-f]{64}", digest or ""):
        raise SpecError("spec_sha256 must be a lowercase SHA-256 digest")
    spec, raw = load_persisted(path)
    if spec_sha256(raw) != digest:
        raise SpecError("execution spec SHA-256 does not match exact persisted bytes")
    required = {
        "run_id": run_id, "role": role, "mission": mission,
        "work_unit": work_unit, "provider": provider, "model": model,
    }
    for key, expected in required.items():
        if spec[key] != expected:
            raise SpecError(f"receipt {key} does not match execution spec")
    # Import only after byte/identity validation. This makes the receipt's resolved
    # configuration use exactly the same provider policy as the launch adapter.
    from execute_provider import provider_contract
    argv, env_overrides = provider_contract(spec)
    argv_bytes = (json.dumps(argv, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    return {
        "run_id": spec["run_id"],
        "execution_spec_path": str(Path(path)),
        "execution_spec_sha256": digest,
        "requested": {key: spec[key] for key in ("provider", "model", "effort", "speed")},
        "resolved": {
            "provider": spec["provider"], "model": spec["model"],
            "effort": spec["effort"], "speed": spec["speed"],
            "executable": argv[0], "argv_sha256": hashlib.sha256(argv_bytes).hexdigest(),
            "env_override_keys": sorted(env_overrides),
        },
        "observed": {"model": "unknown", "effort": "unknown", "speed": "unknown"},
    }


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
    construct_parser = sub.add_parser("construct")
    for name in ("role", "mission", "work-unit", "attempt", "provider", "model", "effort", "speed", "repo", "prompt"):
        construct_parser.add_argument(f"--{name}", required=True)
    construct_parser.add_argument("--feature")
    construct_parser.add_argument("--run-id")
    construct_parser.add_argument("--write-scope-json", required=True)
    link_parser = sub.add_parser("receipt-link")
    for name in ("run-id", "spec", "spec-sha256", "role", "mission", "work-unit", "provider", "model"):
        link_parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    try:
        if args.command == "construct":
            try:
                write_scope = json.loads(args.write_scope_json)
            except json.JSONDecodeError as exc:
                raise SpecError("write_scope_json must be valid JSON") from exc
            spec, path, digest = construct(
                role=args.role, mission=args.mission, feature=args.feature,
                work_unit=args.work_unit, attempt=int(args.attempt), provider=args.provider,
                model=args.model, effort=args.effort, speed=args.speed, repo=args.repo,
                prompt=args.prompt, write_scope=write_scope, run_id=args.run_id,
            )
            print(json.dumps({"run_id": spec["run_id"], "path": str(path), "sha256": digest},
                             sort_keys=True, separators=(",", ":")))
        elif args.command == "receipt-link":
            print(json.dumps(receipt_link(
                run_id=args.run_id, path=args.spec, digest=args.spec_sha256,
                role=args.role, mission=args.mission, work_unit=args.work_unit,
                provider=args.provider, model=args.model,
            ), sort_keys=True, separators=(",", ":")))
        else:
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
