#!/usr/bin/env python3
"""Supervise one authorized provider process and always emit terminal evidence."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime

from execute_provider import provider_contract
from execution_receipt import ReceiptError, all_unknown, canonical_bytes, capture_before, now, write_receipt
from observe_output import observe
from execution_spec import artifact_directory, SpecError, load_persisted, spec_sha256


RECEIPT_FAILURE_EXIT = 125


def unknown_number():
    return {"value": None, "source": "unknown"}


def unknown_text():
    return {"value": None, "source": "unknown"}


def observed_number(value):
    return {"value": value, "source": "observed"}


def observed_text(value):
    return {"value": value, "source": "observed"}


def ledger_cli_name(provider):
    return "cursor" if provider == "agent" else provider


def check_command_label(argv, index, commands):
    """Derive a short privacy-safe check name from a verification argv list."""
    if not isinstance(argv, list) or not argv:
        return f"check#{index + 1}"
    first = argv[0]
    base = Path(first).name if first.endswith((".sh", ".py")) or "/" in first else first
    occurrence = 1
    for prior_index, prior in enumerate(commands[:index]):
        if prior and prior[0] == first:
            occurrence += 1
    return f"{base}#{occurrence}"


def registry_pool_and_billing(repo, provider, speed):
    path = Path(repo) / "harness-registry.json"
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unknown", "unknown"
    doors = registry.get("doors") or {}
    cli = ledger_cli_name(provider)
    if cli == "cursor":
        door_name = "cursor-grok" if speed == "fast" else "cursor-composer"
    else:
        door_name = cli
    door = doors.get(door_name)
    if not isinstance(door, dict):
        return "unknown", "unknown"
    return door.get("pool") or "unknown", door.get("billing_class") or "unknown"


def wall_time_seconds(started_at, finished_at):
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    return max(0.0, (finished - started).total_seconds())


def build_ledger_row(spec, receipt, *, tier):
    observation = receipt["observation"]
    usage = observation["usage"]
    pool, billing_class = registry_pool_and_billing(spec["repo"], spec["provider"], spec["speed"])
    mission = Path(spec["mission"]).name
    feature = receipt["feature"] if receipt.get("feature") else "unknown"
    door = tier if tier else "unknown"
    model = spec["model"]
    return {
        "schema_version": 1,
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
        "pool": pool,
        "billing_class": billing_class,
        "requested_model": observed_text(model),
        "resolved_model": observed_text(model),
        "observed_model": {
            "value": observation["observed_model"]["value"],
            "source": observation["observed_model"]["source"],
        },
        "effort": observed_text(spec["effort"]),
        "fast_state": {
            "value": observation["fast_state"]["value"],
            "source": observation["fast_state"]["source"],
        },
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
        "cost": {"value": None, "source": "unknown", "currency": "USD"},
        "quota_share": unknown_number(),
        "checks": [],
        "diff_size": {
            "files": observed_number(len(receipt["changed_paths"])),
            "lines": unknown_number(),
        },
        "scope_result": receipt["scope"]["result"],
        "anti_gaming_flags": [],
        "failure_class": None,
        "escalation_reason": None,
        "outcome": receipt["outcome"],
    }


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


def write_ledger_row(spec, receipt, *, tier, log):
    try:
        from ledger import LedgerError, validate_row
    except ImportError:
        warn_ledger(log, "ledger: module unavailable")
        return
    try:
        row = build_ledger_row(spec, receipt, tier=tier)
        validate_row(row)
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
    log_offset = 0
    try:
        log_offset = log.stat().st_size
    except OSError:
        log_offset = 0
    try:
        try:
            with log.open("ab", buffering=0) as output:
                process = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    env={**os.environ, **env_overrides},
                    start_new_session=True,
                )
                deadline = None if args.timeout == 0 else time.monotonic() + args.timeout
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

    finished_at = now()
    try:
        with log.open("rb") as handle:
            handle.seek(log_offset)
            raw_output = handle.read()
        observe_provider = "cursor" if spec["provider"] == "agent" else spec["provider"]
        observation = observe(observe_provider, raw_output)
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
    try:
        receipt_doc = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        warn_ledger(log, "ledger: receipt unreadable")
    else:
        write_ledger_row(spec, receipt_doc, tier=args.tier, log=log)
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
    parser.add_argument("--task")
    parser.add_argument("--tier")
    args = parser.parse_args()
    if args.timeout < 0:
        print("ERROR: timeout cannot be negative", file=sys.stderr)
        return 2
    try:
        return run(args)
    except (ReceiptError, SpecError, RuntimeError, ValueError) as exc:
        print(f"ERROR: terminal execution evidence failed: {exc}", file=sys.stderr)
        return RECEIPT_FAILURE_EXIT


if __name__ == "__main__":
    sys.exit(main())
