#!/usr/bin/env python3
"""Read-only Claude transcript usage report for Front Desk and harness runs."""
import argparse, json, os, re, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
POLL = (re.compile(r"\bsleep\b"), re.compile(r"\btail\s+-\w*[fF]"), re.compile(r"\bwatch\s"),
        re.compile(r"\.tasks/|git status|\bps\b|\bpgrep\b|\btail\b|\bjobs\b"))


def parse_time(text):
    if text is None:
        return None
    try:
        t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def parse_bound(text):
    t = parse_time(text)
    if t is None:
        print(f"usage_report: invalid time: {text}", file=sys.stderr)
        raise SystemExit(2)
    return t.replace(hour=0, minute=0, second=0, microsecond=0) if "T" not in text and len(text) <= 10 else t


def in_window(ts, since, until):
    return ts is not None and (since is None or ts >= since) and (until is None or ts < until)


def uget(usage, key):
    v = usage.get(key) if isinstance(usage, dict) else None
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def load_context(tasks_dir, repo):
    repo_r = os.path.realpath(repo)
    run_ids = set()
    for path in sorted((tasks_dir / "receipts").glob("*.json")) if (tasks_dir / "receipts").is_dir() else []:
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("run_id"), str):
                run_ids.add(d["run_id"])
        except (OSError, ValueError, RecursionError):
            pass
    harness = set()
    for rid in run_ids:
        log = tasks_dir / "logs" / f"{rid}.log"
        if not log.is_file():
            continue
        try:
            for line in log.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if row.get("type") == "system" and row.get("subtype") == "init" and isinstance(row.get("session_id"), str):
                    harness.add(row["session_id"])
        except OSError:
            pass
    return repo_r, run_ids, harness


def klass(sid, lines, repo_r, harness, run_ids):
    if sid in harness:
        return "harness"
    for line in lines:
        if line.get("type") == "user":
            msg = line.get("message")
            if any(r in (json.dumps(msg, ensure_ascii=False) if msg is not None else "") for r in run_ids):
                return "harness"
    for line in lines:
        cwd = line.get("cwd")
        if isinstance(cwd, str):
            cr = os.path.realpath(cwd)
            if cr == repo_r or cr.startswith(repo_r + os.sep):
                return "front_desk"
    return "other"


def polling(block, seen_bash, sid):
    name = block.get("name")
    if not isinstance(name, str):
        return False
    if name in ("Monitor", "BashOutput", "TaskOutput"):
        return True
    if name != "Bash":
        return False
    cmd = block.get("input", {}).get("command") if isinstance(block.get("input"), dict) else None
    if not isinstance(cmd, str):
        return False
    cmd = cmd.strip()
    if any(r.search(cmd) for r in POLL[:3]):
        return True
    key = (sid, cmd)
    if key in seen_bash and POLL[3].search(cmd):
        return True
    seen_bash.add(key)
    return False


def load_rows(projects_dir):
    rows = []
    if not projects_dir.is_dir():
        return rows
    for path in sorted(projects_dir.rglob("*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if isinstance(row, dict) and isinstance(row.get("sessionId"), str):
                rows.append(row)
    return rows


def build_report(rows, tasks_dir, repo, since, until):
    repo_r, run_ids, harness = load_context(tasks_dir, repo)
    by_sid = defaultdict(list)
    for row in rows:
        by_sid[row["sessionId"]].append(row)
    classes = {sid: klass(sid, ls, repo_r, harness, run_ids) for sid, ls in by_sid.items()}
    agg = defaultdict(lambda: {f: 0 for f in FIELDS} | {"total": 0, "messages": 0})
    seen_msg, seen_poll, seen_bash, fd_turns, fd_poll = set(), set(), set(), 0, 0
    for row in rows:
        ts = parse_time(row.get("timestamp"))
        if not in_window(ts, since, until) or row.get("type") != "assistant":
            continue
        msg = row.get("message")
        if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
            continue
        sid, mid = row["sessionId"], msg.get("id")
        key = (sid, mid) if isinstance(mid, str) else (sid, id(row))
        if key in seen_msg:
            continue
        seen_msg.add(key)
        usage, model = msg["usage"], msg.get("model") if isinstance(msg.get("model"), str) else "unknown"
        b = agg[(classes[sid], model)]
        for f in FIELDS:
            b[f] += uget(usage, f)
        b["total"] += sum(uget(usage, f) for f in FIELDS)
        b["messages"] += 1
        if classes[sid] == "front_desk" and not row.get("isSidechain"):
            fd_turns += 1
    for row in rows:
        if not in_window(parse_time(row.get("timestamp")), since, until):
            continue
        sid = row["sessionId"]
        if row.get("type") != "assistant" or classes[sid] != "front_desk":
            continue
        msg = row.get("message")
        if not isinstance(msg, dict):
            continue
        for block in msg.get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            bid = block.get("id")
            if not isinstance(bid, str) or (sid, bid) in seen_poll:
                continue
            if polling(block, seen_bash, sid):
                seen_poll.add((sid, bid))
                fd_poll += 1
    accepted = set()
    ev_path = tasks_dir / "events.jsonl"
    if ev_path.is_file():
        try:
            for line in ev_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if ev.get("event") == "review" and ev.get("verdict") == "PASS" and in_window(parse_time(ev.get("at")), since, until):
                    if isinstance(ev.get("task"), str):
                        accepted.add(ev["task"])
        except OSError:
            pass
    fd_total = sum(v["total"] for (c, _), v in agg.items() if c == "front_desk")
    n = len(accepted)
    return ([{"class": k[0], "model": k[1], **v} for k, v in sorted(agg.items())],
            {"turns": fd_turns, "polling_calls": fd_poll, "accepted_tasks": n,
             "tokens_per_accepted_task": fd_total // n if n else None})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--projects", type=Path, default=Path.home() / ".claude/projects")
    p.add_argument("--tasks-dir", type=Path, default=Path(".tasks"))
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--since")
    p.add_argument("--until")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    since = parse_bound(a.since) if a.since else None
    until = parse_bound(a.until) if a.until else None
    rows, fd = build_report(load_rows(a.projects), a.tasks_dir, a.repo, since, until)
    if a.json:
        print(json.dumps({"since": a.since, "until": a.until, "rows": rows, "front_desk": fd}, indent=2, sort_keys=True))
        return
    print("| class | model | input | output | cache write | cache read | total | messages |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print("| {class} | {model} | {input_tokens} | {output_tokens} | {cache_creation_input_tokens} | "
              "{cache_read_input_tokens} | {total} | {messages} |".format(**r))
    print()
    tpa = fd["tokens_per_accepted_task"]
    print(f"Front Desk: {fd['turns']} turns, {fd['polling_calls']} polling calls, {fd['accepted_tasks']} accepted tasks, "
          f"{tpa if tpa is not None else 'n/a'} tokens per accepted task")


if __name__ == "__main__":
    main()
