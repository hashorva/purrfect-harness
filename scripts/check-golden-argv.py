#!/usr/bin/env python3
"""Recorded golden argv fixtures never change: an argv change adds contract N+1 (T-018)."""
import argparse, hashlib, json, os, re, subprocess, sys
from pathlib import Path
FIXTURES, NAME, EDITABLE = "tests/fixtures/golden-argv", re.compile(r"([a-z]+)-v([1-9][0-9]*)\.json"), {"MANIFEST.json", "README.md"}
def fixture_names(directory):
    return sorted(p.name for p in Path(directory).glob("*.json") if p.name != "MANIFEST.json")
def manifest_bytes(directory):
    files = {}
    for name in fixture_names(directory):
        match = NAME.fullmatch(name)
        files[name] = {"contract": int(match.group(2)) if match else None,
                       "sha256": hashlib.sha256((Path(directory) / name).read_bytes()).hexdigest()}
    return (json.dumps({"files": files, "schema": 1}, sort_keys=True, separators=(",", ":")) + "\n").encode()
def manifest_errors(directory):
    directory = Path(directory)
    try:
        recorded = json.loads((directory / "MANIFEST.json").read_text())["files"]
    except (OSError, ValueError, KeyError, TypeError):
        return ["MANIFEST.json: missing or unreadable"]
    expected = json.loads(manifest_bytes(directory))["files"]
    errors = []
    for name in sorted(set(recorded) | set(expected)):
        match = NAME.fullmatch(name)
        if not match:
            errors.append(f"{name}: not a <provider>-v<N>.json fixture name")
        elif recorded.get(name) != expected.get(name):
            errors.append(f"{name}: sha256 or contract differs from MANIFEST.json")
        elif json.loads((directory / name).read_text()).get("contract") != int(match.group(2)):
            errors.append(f"{name}: contract field differs from its file name")
    return errors
def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout
def history_errors(base):
    merge_base = git("merge-base", base, "HEAD").strip()
    recorded = [NAME.fullmatch(Path(p).name) for p in git("ls-tree", "--name-only", merge_base, "--", FIXTURES + "/").splitlines()]
    newest = max((int(m.group(2)) for m in recorded if m), default=0)
    errors = []
    for line in git("diff", "--name-status", "--no-renames", merge_base, "HEAD", "--", FIXTURES + "/").splitlines():
        status, path = line.split("\t", 1)
        name, match = Path(path).name, NAME.fullmatch(Path(path).name)
        if name in EDITABLE and status in ("A", "M"):
            continue
        if status == "A" and match and int(match.group(2)) > newest:
            continue
        errors.append(f"{name}: {status} is not allowed; recorded fixtures are immutable, add contract {newest + 1} instead")
    return errors
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    args = parser.parse_args()
    errors = manifest_errors(FIXTURES)
    base = args.base
    if base is None and subprocess.run(["git", "rev-parse", "--verify", "--quiet", "origin/main^{commit}"], capture_output=True).returncode == 0:
        base = "origin/main"
    if base is None:
        if os.environ.get("CI") == "true":
            print("golden-argv: CI needs origin/main (fetch-depth: 0) for the history check", file=sys.stderr)
            return 2
        print("golden-argv: history check skipped (no origin/main in this local clone)")
    else:
        try:
            errors += history_errors(base)
        except subprocess.CalledProcessError:
            print(f"golden-argv: cannot compare HEAD with {base}", file=sys.stderr)
            return 2
    for error in errors:
        print(f"golden-argv: {error}", file=sys.stderr)
    if not errors:
        print("golden-argv: OK")
    return 1 if errors else 0
if __name__ == "__main__": sys.exit(main())
