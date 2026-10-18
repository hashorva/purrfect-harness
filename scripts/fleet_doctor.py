#!/usr/bin/env python3
"""Check that each registry provider resolves to the expected logged-in CLI."""
import re
import os
import subprocess
import sys
from pathlib import Path

from harness_registry import load_registry


def path_hits(binary, path_value):
    hits = []
    for entry in path_value.split(":"):
        directory = Path(entry or ".")
        candidate = directory / binary
        if candidate.is_file() and os.access(candidate, os.X_OK):
            hits.append((str(candidate), str(candidate.resolve())))
    return hits


def run_command(command, executable, timeout=30):
    argv = [executable, *command[1:]]
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)


def diagnose(registry, path_value):
    findings = []
    has_error = False
    for name, provider in registry["providers"].items():
        hits = path_hits(provider["binary"], path_value)
        if not hits:
            findings.append(("WARN", name, f"{provider['binary']} is not installed"))
            continue
        unique_targets = {real for _, real in hits}
        if len(unique_targets) > 1:
            findings.append(("ERROR", name, "multiple different binaries found on PATH"))
            has_error = True
            continue
        if len(hits) > 1:
            findings.append(("WARN", name, "duplicate PATH hits resolve to the same binary"))
        try:
            identity = run_command(provider["identity_check"], hits[0][0])
        except subprocess.TimeoutExpired:
            findings.append(("WARN", name, "identity check timed out after 30 seconds"))
            continue
        except OSError:
            findings.append(("ERROR", name, "identity check could not run"))
            has_error = True
            continue
        first_line = identity.stdout.splitlines()[0] if identity.stdout.splitlines() else ""
        if identity.returncode != 0 or re.fullmatch(provider["identity_pattern"], first_line) is None:
            findings.append(("ERROR", name, "binary identity does not match registry"))
            has_error = True
            continue
        try:
            login = run_command(provider["login_check"], hits[0][0])
        except subprocess.TimeoutExpired:
            findings.append(("WARN", name, "login check timed out after 30 seconds"))
            continue
        except OSError:
            findings.append(("ERROR", name, "login check could not run"))
            has_error = True
            continue
        if login.returncode:
            findings.append(("ERROR", name, "not logged in"))
            has_error = True
        else:
            findings.append(("OK", name, "identity matches and login check passed"))
    return findings, has_error


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--smoke"]:
        from seat_smoke import main as smoke_main
        return smoke_main(argv[1:])
    try:
        findings, has_error = diagnose(load_registry(), os.environ.get("PATH", ""))
    except Exception as exc:
        print(f"ERROR fleet-doctor: {exc}")
        return 1
    for level, provider, message in findings:
        print(f"{level} {provider}: {message}")
    return 1 if has_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
