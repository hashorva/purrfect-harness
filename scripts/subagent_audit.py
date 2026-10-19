#!/usr/bin/env python3
"""Audit mission brain runs from saved logs and optionally mark unconfirmed routing rows."""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import observe_output
from run_id import validate_run_id
def read_rows(path):
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        lines = []
    rows = []
    for n, line in enumerate(lines, 1):
        try:
            row = json.loads(line)
        except (ValueError, RecursionError):
            print(f"subagent_audit: {path}: line {n}: not JSON", file=sys.stderr)
            raise SystemExit(2)
        rows.append((line, row))
    return rows


def audit(mission, tasks, routing, mark):
    mission = mission.rstrip("/")
    runs = {}
    for folder, record in (("specs", "spec only"), ("receipts", "receipt")):
        for path in (tasks / folder).glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                rid = validate_run_id(data.get("run_id"))
            except (OSError, ValueError, RecursionError, AttributeError):
                continue
            if (isinstance(data, dict) and data.get("role") == "brain"
                    and isinstance(data.get("mission"), str)
                    and data["mission"].rstrip("/") == mission):
                runs[rid] = {"id": rid, "work": data.get("work_unit", ""),
                             "provider": data.get("provider", ""), "record": record}
    for rid, run in runs.items():
        log = tasks / "logs" / f"{rid}.log"
        run.update(log="yes" if log.is_file() else "no", calls="unknown", tokens="unknown")
        if log.is_file():
            try:
                stats = observe_output.observe(run["provider"], log.read_bytes())["subagents"]
                for key in ("calls", "tokens"):
                    if stats[key].get("source") == "observed":
                        run[key] = stats[key]["value"]
            except (ValueError, OSError):
                pass
    rows = read_rows(routing)
    extras, unconfirmed, changed = [], [], []
    for original, row in rows:
        updated_line = original
        if isinstance(row, dict) and row.get("type") == "architect-run":
            rid = row.get("run_id")
            missing = not isinstance(rid, str) or not rid
            if missing or rid not in runs:
                extras.append({"id": "none" if missing else rid, "work": row.get("plan", ""),
                               "log": "no", "provider": str(row.get("seat", "")).split(".")[0],
                               "calls": "unknown", "tokens": "unknown",
                               "record": "no run id recorded (ad hoc)" if missing else "routing row only"})
            if "subagent_stats" in row:
                stats, run = row["subagent_stats"], runs.get(rid)
                confirmed = (run is not None and isinstance(run["calls"], int)
                             and not isinstance(run["calls"], bool) and isinstance(stats, dict)
                             and run["calls"] == stats.get("spawned"))
                if not confirmed:
                    unconfirmed.append((original, row))
                    if mark and row.get("source") != "manual":
                        updated = dict(row)
                        updated.pop("source", None)
                        updated["source"] = "manual"
                        updated_line = json.dumps(updated, separators=(",", ":")) + "\n"
        changed.append(updated_line)
    if mark and any(changed[i] != item[0] for i, item in enumerate(rows)):
        fd, name = tempfile.mkstemp(dir=routing.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.writelines(changed)
            os.replace(name, routing)
        finally:
            if os.path.exists(name): os.unlink(name)
    print(f"# Subagent audit: {mission}\n")
    print("Numbers are computed from saved run logs; unknown means no saved log or no parser.\n")
    print("| run id | work unit | log present | provider | Task/Agent calls | subagent tokens | record |")
    print("|---|---|---|---|---|---|---|")
    def cell(value): return str(value).replace("|", "\\|")
    for row in [runs[k] for k in sorted(runs)] + extras:
        print("| " + " | ".join(cell(row.get(k, "")) for k in
              ("id", "work", "log", "provider", "calls", "tokens", "record")) + " |")
    print(f"\nUnconfirmed routing rows: {len(unconfirmed)}")
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mission", required=True)
    parser.add_argument("--tasks-dir", required=True, type=Path)
    parser.add_argument("--routing", required=True, type=Path)
    parser.add_argument("--mark-manual", action="store_true")
    args = parser.parse_args()
    audit(args.mission, args.tasks_dir, args.routing, args.mark_manual)


if __name__ == "__main__":
    main()
