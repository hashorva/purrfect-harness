#!/usr/bin/env python3
"""Read-only Claude transcript and harness ledger usage report."""
import argparse
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

POLL_SLEEP = re.compile(r"\bsleep\b")
POLL_TAIL = re.compile(r"\btail\s+-\w*[fF]")
POLL_WATCH = re.compile(r"\bwatch\s")
POLL_REPEAT = re.compile(r"\.tasks/|git status|\bps\b|\bpgrep\b|\btail\b|\bjobs\b")


def parse_time(text):
    if text is None:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def parse_bound(text):
    value = parse_time(text)
    if value is None:
        print(f"usage_report: invalid time: {text}", file=__import__("sys").stderr)
        raise SystemExit(2)
    if "T" not in text and len(text) <= 10:
        value = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return value


def in_window(ts, since, until):
    if ts is None:
        return False
    if since is not None and ts < since:
        return False
    if until is not None and ts >= until:
        return False
    return True


def real(path):
    try:
        return os.path.realpath(path)
    except OSError:
        return path


def usage_int(usage, key):
    value = usage.get(key) if isinstance(usage, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def load_receipt_run_ids(tasks_dir):
    ids = set()
    receipts = tasks_dir / "receipts"
    if not receipts.is_dir():
        return ids
    for path in sorted(receipts.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            continue
        if isinstance(data, dict) and isinstance(data.get("run_id"), str):
            ids.add(data["run_id"])
    return ids


def harness_session_ids(tasks_dir, run_ids):
    sessions = set()
    logs = tasks_dir / "logs"
    if not logs.is_dir():
        return sessions
    for run_id in run_ids:
        path = logs / f"{run_id}.log"
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if (isinstance(row, dict) and row.get("type") == "system"
                        and row.get("subtype") == "init" and isinstance(row.get("session_id"), str)):
                    sessions.add(row["session_id"])
        except OSError:
            continue
    return sessions


def session_class(session_id, lines, repo_real, harness_sessions, run_ids):
    if session_id in harness_sessions:
        return "harness"
    for line in lines:
        if line.get("type") != "user":
            continue
        message = line.get("message")
        text = json.dumps(message, ensure_ascii=False) if message is not None else ""
        if any(rid in text for rid in run_ids):
            return "harness"
    for line in lines:
        cwd = line.get("cwd")
        if not isinstance(cwd, str):
            continue
        cwd_real = real(cwd)
        if cwd_real == repo_real or cwd_real.startswith(repo_real + os.sep):
            return "front_desk"
    return "other"


def is_polling(block, seen_bash, session_id):
    name = block.get("name")
    block_id = block.get("id")
    if not isinstance(name, str) or not isinstance(block_id, str):
        return False
    if name in ("Monitor", "BashOutput", "TaskOutput"):
        return True
    if name != "Bash":
        return False
    command = block.get("input", {}).get("command") if isinstance(block.get("input"), dict) else None
    if not isinstance(command, str):
        return False
    stripped = command.strip()
    if POLL_SLEEP.search(stripped) or POLL_TAIL.search(stripped) or POLL_WATCH.search(stripped):
        return True
    key = (session_id, stripped)
    if key in seen_bash and POLL_REPEAT.search(stripped):
        return True
    seen_bash.add(key)
    return False


def load_transcripts(projects_dir):
    rows = []
    if not projects_dir.is_dir():
        return rows
    for path in sorted(projects_dir.rglob("*.jsonl")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if not isinstance(row, dict) or not isinstance(row.get("sessionId"), str):
                continue
            rows.append(row)
    return rows


def build_transcript_report(rows, tasks_dir, repo, since, until):
    repo_real = real(repo)
    run_ids = load_receipt_run_ids(tasks_dir)
    harness_sessions = harness_session_ids(tasks_dir, run_ids)
    by_session = defaultdict(list)
    for row in rows:
        by_session[row["sessionId"]].append(row)
    classes = {sid: session_class(sid, lines, repo_real, harness_sessions, run_ids)
               for sid, lines in by_session.items()}

    agg = defaultdict(lambda: {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
                               "cache_read_input_tokens": 0, "total": 0, "messages": 0})
    seen_usage = set()
    seen_poll = set()
    seen_bash = set()
    fd_turns = fd_poll = 0

    for row in rows:
        ts = parse_time(row.get("timestamp"))
        if not in_window(ts, since, until):
            continue
        sid = row["sessionId"]
        klass = classes[sid]
        if row.get("type") != "assistant":
            continue
        message = row.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        mid = message.get("id")
        dedupe = (sid, mid) if isinstance(mid, str) else (sid, id(row))
        if dedupe in seen_usage:
            continue
        seen_usage.add(dedupe)
        model = message.get("model") if isinstance(message.get("model"), str) else "unknown"
        key = (klass, model)
        bucket = agg[key]
        for field in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            bucket[field] += usage_int(usage, field)
        bucket["total"] += sum(usage_int(usage, f) for f in (
            "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        bucket["messages"] += 1
        if klass == "front_desk":
            if not row.get("isSidechain"):
                fd_turns += 1
            for block in message.get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                bid = block.get("id")
                if not isinstance(bid, str) or (sid, bid) in seen_poll:
                    continue
                if is_polling(block, seen_bash, sid):
                    seen_poll.add((sid, bid))
                    fd_poll += 1

    accepted = set()
    events = tasks_dir / "events.jsonl"
    if events.is_file():
        try:
            for line in events.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if not isinstance(ev, dict) or ev.get("event") != "review" or ev.get("verdict") != "PASS":
                    continue
                at = parse_time(ev.get("at"))
                if not in_window(at, since, until):
                    continue
                task = ev.get("task")
                if isinstance(task, str):
                    accepted.add(task)
        except OSError:
            pass

    fd_total = sum(v["total"] for (klass, _), v in agg.items() if klass == "front_desk")
    accepted_n = len(accepted)
    out_rows = [{"class": k[0], "model": k[1], **v} for k, v in sorted(agg.items())]
    front_desk = {
        "turns": fd_turns,
        "polling_calls": fd_poll,
        "accepted_tasks": accepted_n,
        "tokens_per_accepted_task": fd_total // accepted_n if accepted_n else None,
    }
    return out_rows, front_desk


def token_observed(field):
    return isinstance(field, dict) and field.get("source") == "observed" and isinstance(field.get("value"), int) and not isinstance(field.get("value"), bool)


def token_value(field):
    if token_observed(field):
        return field["value"]
    return 0


def row_in_ledger_window(row, tasks_dir, since, until):
    if since is None and until is None:
        return True
    run_id = row.get("run_id")
    if not isinstance(run_id, str):
        return False
    path = tasks_dir / "receipts" / f"{run_id}.json"
    if not path.is_file():
        return False
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return False
    started = parse_time(receipt.get("started_at")) if isinstance(receipt, dict) else None
    return in_window(started, since, until)


def harness_groups(ledger_dir, tasks_dir, since, until):
    names = ("by_role", "by_step", "by_seat", "by_prompt_version")
    buckets = {name: defaultdict(lambda: {"runs": 0, "total": 0, "without_cache": 0, "unknown_runs": 0})
               for name in names}
    if not ledger_dir.is_dir():
        return {name: [] for name in names}
    for path in sorted(ledger_dir.glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            continue
        if not isinstance(row, dict) or not row_in_ledger_window(row, tasks_dir, since, until):
            continue
        role = row.get("role_tag") if isinstance(row.get("role_tag"), str) else "untagged"
        step = row.get("task") if isinstance(row.get("task"), str) else "unknown"
        cli = row.get("cli") if isinstance(row.get("cli"), str) else "unknown"
        tier = row.get("tier")
        seat = f"{cli}.{tier}" if tier is not None else cli
        prompt = row.get("prompt_version") if isinstance(row.get("prompt_version"), str) else "unknown"
        unknown = not token_observed(row.get("tokens_total"))
        total = token_value(row.get("tokens_total"))
        without = token_value(row.get("tokens_without_cache"))
        for name, key in (("by_role", role), ("by_step", step), ("by_seat", seat), ("by_prompt_version", prompt)):
            entry = buckets[name][key]
            entry["runs"] += 1
            entry["total"] += total
            entry["without_cache"] += without
            if unknown:
                entry["unknown_runs"] += 1
    out = {}
    for name in names:
        items = [{"key": key, **vals} for key, vals in buckets[name].items()]
        items.sort(key=lambda item: (-item["total"], item["key"]))
        out[name] = items
    return out


def print_table(rows, front_desk, harness):
    print("| class | model | input | output | cache write | cache read | total | messages |")
    print("|---|---|---|---|---|---|---|---|")
    for row in rows:
        print("| {class} | {model} | {input_tokens} | {output_tokens} | {cache_creation_input_tokens} | "
              "{cache_read_input_tokens} | {total} | {messages} |".format(**row))
    print()
    tpa = front_desk["tokens_per_accepted_task"]
    tpa_s = str(tpa) if tpa is not None else "n/a"
    print(f"Front Desk: {front_desk['turns']} turns, {front_desk['polling_calls']} polling calls, "
          f"{front_desk['accepted_tasks']} accepted tasks, {tpa_s} tokens per accepted task")
    headers = {
        "by_role": "role",
        "by_step": "step",
        "by_seat": "seat",
        "by_prompt_version": "prompt version",
    }
    for group, label in headers.items():
        print()
        print(f"| {label} | runs | total | without cache | unknown |")
        print("|---|---|---|---|---|")
        for item in harness[group]:
            print(f"| {item['key']} | {item['runs']} | {item['total']} | {item['without_cache']} | {item['unknown_runs']} |")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--projects", type=Path, default=Path.home() / ".claude/projects")
    parser.add_argument("--tasks-dir", type=Path, default=Path(".tasks"))
    parser.add_argument("--ledger-dir", type=Path, default=None)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    since = parse_bound(args.since) if args.since else None
    until = parse_bound(args.until) if args.until else None
    ledger_dir = args.ledger_dir if args.ledger_dir is not None else args.tasks_dir / "ledger"
    rows, front_desk = build_transcript_report(load_transcripts(args.projects), args.tasks_dir, args.repo, since, until)
    harness = harness_groups(ledger_dir, args.tasks_dir, since, until)
    data = {
        "since": args.since,
        "until": args.until,
        "rows": rows,
        "front_desk": front_desk,
        "harness": harness,
    }
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print_table(rows, front_desk, harness)


if __name__ == "__main__":
    main()
