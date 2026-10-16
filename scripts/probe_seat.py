#!/usr/bin/env python3
"""Run exactly one frozen fleet seat and retain privacy-safe probe evidence."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time

from execute_provider import provider_contract
from execution_spec import CURRENT_PROVIDER_CONTRACT
from observe_output import no_turn, observe


CLASSES = ("ok", "no-turn", "mcp-init-wait", "permission-wait", "input-wait", "auth", "limit", "unknown")
SEAT = re.compile(r"[a-z]+(?:\.[a-z]+)?")
STEP_ZERO = "search the CLI's GitHub issues for the exact symptom first"


def mcp_names(text):
    """Return only MCP server names; never retain their URLs or configuration."""
    names = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Checking") or stripped.lower().startswith("mcp "):
            continue
        if stripped.lower().startswith("no mcp"):
            continue
        name = stripped.split(": ", 1)[0].split()[0] if stripped.split(": ", 1)[0].split() else ""
        if name:
            names.append(name)
    return names


def _event_clues(stdout):
    clues = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            clues.append(line)
            continue
        if not isinstance(event, dict):
            continue
        for key in ("result", "error", "message"):
            value = event.get(key)
            if isinstance(value, str):
                clues.append(value)
    return "\n".join(clues)


def classify(provider, exit_code, stdout, stderr):
    """Classify a completed probe without treating init metadata as user-facing text."""
    clue = "\n".join((stderr, _event_clues(stdout)))
    lower = clue.lower()
    if exit_code is None:
        if re.search(r"\bmcp\b.*(?:start|initial|connect|server)", lower):
            return "mcp-init-wait"
        if re.search(r"(?:allow|approve|permission).*(?:\[y/n\]|confirm|run)|\[y/n\]", lower):
            return "permission-wait"
        if re.search(r"(?:waiting|wait).*(?:input|stdin)|(?:input|stdin).*(?:waiting|wait)", lower):
            return "input-wait"
        return "unknown"
    if re.search(r"not logged in|authentication|auth(?:orization)? (?:required|failed)|login required", lower):
        return "auth"
    if re.search(r"usage limit|rate limit|quota|too many requests", lower):
        return "limit"
    if exit_code == 0 and no_turn(provider, stdout.encode("utf-8", errors="replace")):
        return "no-turn"
    if exit_code == 0 and "OK" in stdout:
        return "ok"
    return "unknown"


def _fleet_path(value):
    if value:
        return Path(value)
    root = Path(__file__).resolve().parent.parent
    try:
        mission = subprocess.check_output(["bash", str(root / "scripts/active-mission.sh")], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("cannot locate active mission fleet") from exc
    return root / mission / "fleet.json"


def _seat(fleet_path, name):
    if not SEAT.fullmatch(name):
        raise ValueError("seat must be a simple frozen seat name")
    try:
        data = json.loads(fleet_path.read_text())
        seat = data["seats"][name]
        provider = seat["provider"]
        model, effort, speed = seat["model"], seat["effort"], seat["speed"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("unknown or invalid frozen seat") from exc
    if provider not in {"claude", "codex", "cursor", "agent", "agy"}:
        raise ValueError("unknown or invalid frozen seat")
    return ("agent" if provider == "cursor" else provider), model, effort, speed


def _run(argv, cwd, timeout, stdout_path=None, stderr_path=None):
    stdout_chunks, stderr_chunks = [], []
    out_handle = stdout_path.open("wb") if stdout_path else subprocess.PIPE
    err_handle = stderr_path.open("wb") if stderr_path else subprocess.PIPE
    process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)

    def copy(source, sink, chunks):
        while True:
            block = source.read(4096)
            if not block:
                break
            chunks.append(block)
            if sink is not None:
                sink.write(block)
                sink.flush()

    out_sink = out_handle if stdout_path else None
    err_sink = err_handle if stderr_path else None
    readers = [threading.Thread(target=copy, args=(process.stdout, out_sink, stdout_chunks), daemon=True),
               threading.Thread(target=copy, args=(process.stderr, err_sink, stderr_chunks), daemon=True)]
    for reader in readers:
        reader.start()
    killed = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        killed = True
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    for reader in readers:
        reader.join()
    if stdout_path:
        out_handle.close()
        err_handle.close()
    return (None if killed else process.returncode,
            b"".join(stdout_chunks).decode("utf-8", errors="replace"),
            b"".join(stderr_chunks).decode("utf-8", errors="replace"))


def _tokens(provider, stdout):
    observed = observe(provider, stdout.encode("utf-8", errors="replace"))
    usage = observed["usage"]
    return usage["input"]["value"], usage["output"]["value"]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="probe-seat.py")
    parser.add_argument("seat")
    parser.add_argument("--fleet")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--out-root", default=".tasks/probes")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        provider, model, effort, speed = _seat(_fleet_path(args.fleet), args.seat)
    except ValueError as exc:
        print(f"probe-seat: {exc}", file=sys.stderr)
        return 2
    folder = Path(tempfile.gettempdir()) / f"probe-seat-{args.seat}"
    spec = {"provider": provider, "model": model, "effort": effort, "speed": speed,
            "repo": str(folder), "prompt": "Reply with OK only.", "write_scope": [],
            "role": "worker", "provider_contract_version": CURRENT_PROVIDER_CONTRACT}
    try:
        command, _ = provider_contract(spec)
    except Exception as exc:  # provider_contract gives the authoritative validation.
        print(f"probe-seat: invalid frozen seat: {exc}", file=sys.stderr)
        return 2
    cli = command[0]
    mcp_command = [cli, "mcp", "list"]
    if args.dry_run:
        print(json.dumps({"seat": args.seat, "argv": command, "folder": str(folder), "timeout_s": args.timeout,
                          "mcp_command": mcp_command, "out_dir": str(Path(args.out_root) / f"<UTC>-{args.seat}")},
                         sort_keys=True))
        return 0
    folder = Path(tempfile.mkdtemp(prefix=f"probe-seat-{args.seat}-"))
    subprocess.run(["git", "init", "-q"], cwd=folder, check=True)
    spec["repo"] = str(folder)
    command, _ = provider_contract(spec)
    mcp_command = [command[0], "mcp", "list"]
    mcp_exit, mcp_stdout, _ = _run(mcp_command, folder, 30)
    out_dir = Path(args.out_root) / f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{args.seat}"
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "command.json").write_text(json.dumps({"argv": command, "folder": str(folder)}, sort_keys=True) + "\n")
    (out_dir / "mcp.json").write_text(json.dumps({"cli": command[0], "names": mcp_names(mcp_stdout) if mcp_exit == 0 else None}, sort_keys=True) + "\n")
    started = time.monotonic()
    exit_code, stdout, stderr = _run(command, folder, args.timeout, out_dir / "stdout.txt", out_dir / "stderr.txt")
    duration = time.monotonic() - started
    with (out_dir / "events.jsonl").open("w") as events:
        for line in stdout.splitlines():
            if line.startswith("{"):
                events.write(line + "\n")
    category = classify(provider, exit_code, stdout, stderr)
    tokens_input, tokens_output = _tokens(provider, stdout)
    (out_dir / "result.json").write_text(json.dumps({"seat": args.seat, "class": category, "exit_code": exit_code,
        "duration_s": duration, "tokens_input": tokens_input, "tokens_output": tokens_output}, sort_keys=True) + "\n")
    if category != "ok":
        detail = next((line for line in stderr.splitlines() if line), "") or (stdout.splitlines()[-1] if stdout else "")
        print(f"Step 0: {STEP_ZERO}. {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
