#!/usr/bin/env python3
"""Supervise one authorized provider process and always emit terminal evidence."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from execute_provider import provider_contract
from execution_receipt import ReceiptError, capture_before, now, write_receipt
from execution_spec import artifact_directory, SpecError, load_persisted, spec_sha256


RECEIPT_FAILURE_EXIT = 125


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
    )
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
