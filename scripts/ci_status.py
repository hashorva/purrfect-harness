#!/usr/bin/env python3
"""Decide CI pass/fail for a commit from gh run list JSON (live or saved)."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
GH_JSON = "databaseId,name,workflowName,status,conclusion,headSha"


def _load_runs(sha, runs_json):
    if runs_json is not None:
        path = Path(runs_json)
        if not path.is_file():
            sys.exit(2)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            sys.exit(2)
    else:
        try:
            proc = subprocess.run(
                [
                    "gh",
                    "run",
                    "list",
                    "--commit",
                    sha,
                    "--json",
                    GH_JSON,
                    "--limit",
                    "50",
                ],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            sys.exit(2)
        if proc.returncode != 0:
            sys.exit(2)
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            sys.exit(2)
    if not isinstance(data, list):
        sys.exit(2)
    return data


def _ok(run):
    return run.get("status") == "completed" and run.get("conclusion") == "success"


def _conclusion(run):
    c = run.get("conclusion")
    return c if c else "none"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--runs-json")
    args = parser.parse_args()
    sha = args.commit
    if not SHA_RE.fullmatch(sha):
        sys.exit(2)

    runs = _load_runs(sha, args.runs_json)
    matching = [r for r in runs if r.get("headSha") == sha]
    failing_names = [r.get("name", "") for r in matching if not _ok(r)]

    short = sha[:12]
    lines = []
    if matching and all(_ok(r) for r in matching):
        result = "pass"
        lines.append(f"CI PASS: {len(matching)} runs for {short}")
        code = 0
    else:
        result = "fail"
        code = 1
        if not matching:
            lines.append(f"CI FAIL: no runs for {short}")
        else:
            for run in matching:
                if not _ok(run):
                    lines.append(f"CI FAIL: {run.get('name', '')} {run.get('status', '')}/{_conclusion(run)}")
    lines.append(json.dumps({"commit": sha, "result": result, "failing": failing_names}))
    print("\n".join(lines))
    sys.exit(code)


if __name__ == "__main__":
    main()
