#!/usr/bin/env python3
"""Supervise one authorized provider process and always emit terminal evidence."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime

from execute_provider import provider_contract
from execution_receipt import (ReceiptError, all_unknown, canonical_bytes, capture_before, now,
                               write_receipt)
from observe_output import no_turn, observe, observe_self_reported, resolve_model_identity, token_figures
from execution_spec import artifact_directory, SpecError, load_persisted, spec_sha256

# Imported before any provider runs, so a worker's later edit to scripts/ledger.py
# is never executed by this run. A module that fails to import only skips the ledger step.
try:
    from ledger import LedgerError, check_privacy, valid_model_id, validate_row
except Exception:
    LedgerError = None
    check_privacy = None
    valid_model_id = None
    validate_row = None


RECEIPT_FAILURE_EXIT = 125
NO_TURN_EXIT = 122
STALL_EXIT = 123


def unknown_number():
    return {"value": None, "source": "unknown"}


def append_event(repo, log, event):
    """Append one event line; event logging must never affect run outcome."""
    try:
        path = artifact_directory(repo) / "events.jsonl"
        line = (json.dumps({"at": now(), **event}, separators=(",", ":")) + "\n").encode("utf-8")
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except (OSError, SpecError):
        try:
            with Path(log).open("a", encoding="utf-8") as handle:
                handle.write("WARN: event not written\n")
        except OSError:
            pass


def unknown_text():
    return {"value": None, "source": "unknown"}


def safe_model_flag(entry, source):
    if (not isinstance(entry, dict) or set(entry) != {"value", "source"}
            or entry.get("source") != source or valid_model_id is None):
        return unknown_text()
    value = valid_model_id(entry.get("value"))
    return {"value": value, "source": source} if isinstance(value, str) and value else unknown_text()


def safe_text_flag(entry, source):
    if (not isinstance(entry, dict) or entry.get("source") != source
            or not isinstance(entry.get("value"), str) or not entry["value"].strip()
            or check_privacy is None):
        return unknown_text()
    try:
        check_privacy("field", entry["value"])
    except Exception:
        return unknown_text()
    return {"value": entry["value"], "source": source}


def observed_number(value):
    return {"value": value, "source": "observed"}


def observed_text(value):
    return {"value": value, "source": "observed"}


def ledger_cli_name(provider):
    return "cursor" if provider == "agent" else provider


def check_command_label(argv, index, commands):
    """Derive a short privacy-safe check name from a verification argv list."""
    if not isinstance(argv, list) or not argv:
        return f"check:{index + 1}"
    first = argv[0]
    base = Path(first).name if first.endswith((".sh", ".py")) or "/" in first else first
    occurrence = 1
    for prior_index, prior in enumerate(commands[:index]):
        if prior and prior[0] == first:
            occurrence += 1
    return f"{base}:{occurrence}"


def configured_text(value):
    if not isinstance(value, str) or not value.strip() or value == "unknown":
        return unknown_text()
    return {"value": value, "source": "configured"}


def base_registry_doors(repo, base_commit):
    if not isinstance(base_commit, str) or not base_commit or base_commit.startswith("-"):
        return {}
    try:
        result = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(repo), "cat-file", "blob", f"{base_commit}:harness-registry.json"],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    try:
        registry = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(registry, dict) or not isinstance(registry.get("doors"), dict):
        return {}
    return registry["doors"]


def prompt_version(repo, base_commit, role):
    path = {"brain": "scripts/brain_prompt.py", "worker": "scripts/spawn-worker.sh"}.get(role)
    if path is None or not isinstance(base_commit, str) or not base_commit or base_commit.startswith("-"):
        return None
    try:
        result = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(repo), "rev-parse", f"{base_commit}:{path}"],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    blob = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40,64}", blob):
        return None
    return f"{path}:{blob[:12]}"


def registry_door_pool_and_billing(doors, provider, resolved_model):
    cli = ledger_cli_name(provider)
    if cli == "cursor":
        family = resolved_model.split("-", 1)[0] if isinstance(resolved_model, str) else ""
        door_name = f"cursor-{family}"
    else:
        # A model token can name a door of the same CLI with its own pool (agy
        # `gemini-4-argon-high` -> `agy-argon`); otherwise the CLI's own door.
        door_name = cli
        tokens = re.split(r"[-_.]", resolved_model.lower()) if isinstance(resolved_model, str) else []
        for token in tokens:
            candidate = doors.get(f"{cli}-{token}")
            if isinstance(candidate, dict) and candidate.get("provider") == cli:
                door_name = f"{cli}-{token}"
                break
    door = doors.get(door_name)
    if not isinstance(door, dict):
        return "unknown", "unknown", "unknown"
    return door_name, door.get("pool") or "unknown", door.get("billing_class") or "unknown"


def wall_time_seconds(started_at, finished_at):
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    return max(0.0, (finished - started).total_seconds())


def _ledger_subagents(observation):
    unknown_flag = {"value": None, "source": "unknown"}
    block = observation.get("subagents") or {}
    calls = block.get("calls", unknown_flag)
    tokens = block.get("tokens", unknown_flag)
    return {
        "calls": {"value": calls.get("value"), "source": calls.get("source", "unknown")},
        "tokens": {"value": tokens.get("value"), "source": tokens.get("source", "unknown")},
    }


def build_ledger_row(spec, receipt, *, tier, self_reported_model=None):
    observation = receipt["observation"]
    usage = observation["usage"]
    resolved_configuration = receipt.get("resolved_configuration") or {}
    requested_configuration = receipt.get("requested_configuration") or {}
    resolved_model = resolved_configuration.get("model")
    requested_model_flag = configured_text(requested_configuration.get("model"))
    observed_model_flag = safe_model_flag(observation.get("observed_model"), "observed")
    reported = self_reported_model if self_reported_model is not None else receipt.get("self_reported_model")
    self_reported_model_flag = safe_model_flag(reported, "self_reported")
    fast_state_flag = safe_text_flag(observation.get("fast_state"), "observed")
    identity = resolve_model_identity(requested_model_flag, observed_model_flag, self_reported_model_flag)
    doors = base_registry_doors(spec["repo"], spec["base_commit"])
    resolved_model_flag = configured_text(resolved_model)
    door_model = resolved_model_flag["value"] or requested_model_flag["value"]
    door, pool, billing_class = registry_door_pool_and_billing(doors, spec["provider"], door_model)
    mission = Path(spec["mission"]).name
    feature = receipt["feature"] if receipt.get("feature") else "unknown"
    tokens = observation.get("tokens")
    row = {
        "schema_version": 2,
        "mission": mission,
        "feature": feature,
        "task": spec["work_unit"],
        "run_id": spec["run_id"],
        "parent_run": None,
        "group_id": None,
        "attempt": spec["attempt"],
        "repair_round": 0,
        "cli": ledger_cli_name(spec["provider"]),
        "cli_version": unknown_text(),
        "door": door,
        "tier": tier if tier in ("economy", "premium") else None,
        "pool": pool,
        "billing_class": billing_class,
        "requested_model": requested_model_flag,
        "resolved_model": resolved_model_flag,
        "observed_model": observed_model_flag,
        "self_reported_model": self_reported_model_flag,
        "effort": configured_text(requested_configuration.get("effort")),
        "fast_state": fast_state_flag,
        "task_class_tags": [],
        "allow_list_size": observed_number(len(spec["write_scope"])),
        "task_text_tokens": unknown_number(),
        "ste_flag": False,
        "active_lesson_ids": [],
        "experiment_id": None,
        "wall_time_s": observed_number(wall_time_seconds(receipt["started_at"], receipt["finished_at"])),
        "turns": unknown_number(),
        "tool_calls": unknown_number(),
        "tokens_input": {
            "value": usage["input"]["value"],
            "source": usage["input"]["source"],
        },
        "tokens_output": {
            "value": usage["output"]["value"],
            "source": usage["output"]["source"],
        },
        "tokens_cache": {
            "value": usage["cache"]["value"],
            "source": usage["cache"]["source"],
        },
        "tokens_reasoning": {
            "value": usage["reasoning"]["value"],
            "source": usage["reasoning"]["source"],
        },
        "subagents": _ledger_subagents(observation),
        "cost": {"value": None, "source": "unknown", "currency": "USD"},
        "quota_share": unknown_number(),
        "checks": [],
        "diff_size": {
            "files": observed_number(len(receipt["changed_paths"])),
            "lines": unknown_number(),
        },
        "scope_result": receipt["scope"]["result"],
        "anti_gaming_flags": list(identity["flags"]),
        "failure_class": None,
        "escalation_reason": None,
        "outcome": receipt["outcome"],
    }
    for field, source in (("tokens_total", "total"), ("tokens_without_cache", "without_cache"),
                          ("tokens_cache_write", "cache_write")):
        flag = tokens.get(source, unknown_number()) if isinstance(tokens, dict) else unknown_number()
        row[field] = {"value": flag.get("value"), "source": flag.get("source", "unknown")}
    if "role_tag" in receipt:
        row["role_tag"] = receipt["role_tag"]
    row["prompt_version"] = prompt_version(spec["repo"], spec["base_commit"], spec["role"])
    return row


def _atomic_create_ledger(path, data):
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
            raise OSError(f"ledger row already exists for run_id {path.stem}") from exc
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


def warn_ledger(log, message):
    try:
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"WARN: ledger row not written: {message}\n")
    except OSError:
        pass


def write_ledger_row(spec, receipt, *, tier, log, self_reported_model=None):
    if validate_row is None:
        warn_ledger(log, "ledger: module unavailable")
        return
    try:
        row = build_ledger_row(spec, receipt, tier=tier, self_reported_model=self_reported_model)
        # Door names also come from the base commit, so a worker-edited registry cannot reject the row.
        validate_row(row, door_names=frozenset(base_registry_doors(spec["repo"], spec["base_commit"])))
        destination = artifact_directory(spec["repo"], "ledger") / f"{spec['run_id']}.json"
        _atomic_create_ledger(destination, canonical_bytes(row))
    except LedgerError as error:
        warn_ledger(log, f"{error.field}: {error.reason}")
    except OSError:
        warn_ledger(log, "ledger: write failed")
    except Exception:
        warn_ledger(log, "ledger: row build failed")


def terminate_tree(process):
    if process is None:
        return

    def group_exists():
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def wait_for_group(timeout):
        deadline = time.monotonic() + timeout
        while group_exists():
            # poll() reaps the direct provider once it has exited, but its
            # descendants can still own the process group.
            process.poll()
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)
        process.wait()
        return True

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        # A missing process group is already clean; still reap a direct
        # provider if it has not been collected yet.
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("provider process tree could not be reaped") from exc
        return
    if wait_for_group(1):
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if not wait_for_group(1):
        raise RuntimeError("provider process tree could not be reaped")


def run(args):
    spec, raw = load_persisted(args.spec)
    if spec_sha256(raw) != args.spec_sha256:
        raise SpecError("persisted spec SHA-256 does not match authorization")
    if spec["schema_version"] not in {2, 3}:
        raise SpecError("execution runner requires ExecutionSpec v2 or v3")
    argv, env_overrides = provider_contract(spec)
    log = Path(args.log)
    expected_log = Path(spec["repo"]) / ".tasks/logs" / f"{spec['run_id']}.log"
    if not log.is_absolute():
        log = Path(spec["repo"]) / log
    if log.resolve(strict=False) != expected_log.resolve(strict=False):
        raise SpecError("runner log path must match run_id")
    artifact_directory(spec["repo"], "logs")
    if not log.exists():
        log.touch()

    started_at = now()
    before = capture_before(args.spec, args.spec_sha256)
    event = {"run_id": spec["run_id"], "role": spec["role"], "seat": args.seat,
             "work_unit": spec["work_unit"]}
    append_event(spec["repo"], log, {"event": "run_start", **event})
    events_path = Path(spec["repo"]) / ".tasks" / "events.jsonl"
    process = None
    received_signal = None

    def handle_signal(signum, _frame):
        nonlocal received_signal
        received_signal = signum
        terminate_tree(process)

    previous = {}
    for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.signal(signum, handle_signal)

    outcome = "launch_failed"
    exit_code = 127
    stall_note = None
    log_offset = 0
    try:
        log_offset = log.stat().st_size
    except OSError:
        log_offset = 0
    observe_provider = "cursor" if spec["provider"] == "agent" else spec["provider"]
    try:
        try:
            with log.open("ab", buffering=0) as output:
                process = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    env={**os.environ, **env_overrides, "PURRFECT_RUN_ID": spec["run_id"],
                         "PURRFECT_EVENTS": str(events_path)},
                    start_new_session=True,
                )
                deadline = None if args.timeout == 0 else time.monotonic() + args.timeout
                last_size = os.fstat(output.fileno()).st_size
                last_growth = time.monotonic()
                seen_output = False
                while True:
                    if received_signal is not None:
                        terminate_tree(process)
                        outcome = "interrupted"
                        exit_code = 128 + received_signal
                        break
                    remaining = None if deadline is None else deadline - time.monotonic()
                    if remaining is not None and remaining <= 0:
                        terminate_tree(process)
                        outcome = "timed_out"
                        exit_code = 124
                        break
                    size = os.fstat(output.fileno()).st_size
                    if size > last_size:
                        last_size = size
                        last_growth = time.monotonic()
                        seen_output = True
                    stall_limit = args.idle_seconds if seen_output else args.stall_seconds
                    if stall_limit and time.monotonic() - last_growth >= stall_limit:
                        terminate_tree(process)
                        outcome = "stalled"
                        exit_code = STALL_EXIT
                        since = "after its last output" if seen_output else "since launch"
                        stall_note = f"STALL: no provider output for {stall_limit:g} s {since}; run stopped\n"
                        break
                    try:
                        provider_exit = process.wait(timeout=0.1 if remaining is None else min(0.1, remaining))
                    except subprocess.TimeoutExpired:
                        continue
                    if received_signal is not None:
                        outcome = "interrupted"
                        exit_code = 128 + received_signal
                        break
                    exit_code = provider_exit if provider_exit >= 0 else 128 + abs(provider_exit)
                    outcome = "completed" if exit_code == 0 else "failed"
                    break
        except OSError as exc:
            with log.open("a", encoding="utf-8") as output:
                output.write(f"ERROR: provider launch failed: {exc}\n")
            outcome = "launch_failed"
            exit_code = 127
    finally:
        terminate_tree(process)
        for signum, handler in previous.items():
            signal.signal(signum, handler)

    if stall_note is not None:
        try:
            with log.open("a", encoding="utf-8") as handle:
                handle.write(stall_note)
        except OSError:
            pass

    finished_at = now()
    self_reported_model = unknown_text()
    try:
        with log.open("rb") as handle:
            handle.seek(log_offset)
            raw_output = handle.read()
        observation = observe(observe_provider, raw_output)
        observation["tokens"] = token_figures(observe_provider, raw_output)
        try:
            self_reported_model = observe_self_reported(observe_provider, raw_output)
        except Exception:
            self_reported_model = unknown_text()
        if outcome == "completed" and no_turn(observe_provider, raw_output):
            outcome = "failed"
            exit_code = NO_TURN_EXIT
            with log.open("a", encoding="utf-8") as handle:
                handle.write("NO-TURN: provider output shows 0 turns; completed run recorded as failed\n")
    except Exception:
        try:
            with log.open("a", encoding="utf-8") as handle:
                handle.write("WARN: observation unavailable\n")
        except OSError:
            pass
        observation = all_unknown()
    receipt = write_receipt(
        spec_path=args.spec,
        digest=args.spec_sha256,
        before=before,
        started_at=started_at,
        finished_at=finished_at,
        outcome=outcome,
        exit_code=exit_code,
        log_path=str(log),
        task=args.task,
        tier=args.tier,
        observation=observation,
    )
    append_event(spec["repo"], log, {"event": "run_exit", **event, "exit_code": exit_code,
                 "outcome": outcome, "receipt": f".tasks/receipts/{receipt.name}"})
    try:
        receipt_doc = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        warn_ledger(log, "ledger: receipt unreadable")
    else:
        write_ledger_row(spec, receipt_doc, tier=args.tier, log=log, self_reported_model=self_reported_model)
    try:
        display = receipt.relative_to(Path.cwd())
    except ValueError:
        display = receipt
    print(f"receipt={display}")
    return exit_code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--spec-sha256", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--timeout", type=float, default=2400)
    parser.add_argument("--stall-seconds", type=float, default=90)
    parser.add_argument("--idle-seconds", type=float, default=900)
    parser.add_argument("--task")
    parser.add_argument("--tier")
    parser.add_argument("--seat", default="unknown")
    args = parser.parse_args()
    if not all(math.isfinite(value) for value in (args.timeout, args.stall_seconds, args.idle_seconds)):
        print("ERROR: timeout, stall and idle seconds must be finite numbers", file=sys.stderr)
        return 2
    if args.timeout < 0:
        print("ERROR: timeout cannot be negative", file=sys.stderr)
        return 2
    if args.stall_seconds < 0 or args.idle_seconds < 0:
        print("ERROR: stall and idle seconds cannot be negative", file=sys.stderr)
        return 2
    try:
        return run(args)
    except (ReceiptError, SpecError, RuntimeError, ValueError) as exc:
        print(f"ERROR: terminal execution evidence failed: {exc}", file=sys.stderr)
        return RECEIPT_FAILURE_EXIT


if __name__ == "__main__":
    sys.exit(main())
