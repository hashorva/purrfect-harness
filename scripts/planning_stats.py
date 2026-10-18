#!/usr/bin/env python3
"""Summarize planning-run token counts by seat and model."""
import json
import sys
from collections import defaultdict
from pathlib import Path

class PlanningStatsError(Exception):
    """Invalid planning run data."""

def median(values):
    """Return the integer median, rounding even-sized medians down."""
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2
def _obs(field):
    value = field.get("value") if isinstance(field, dict) and field.get("source") == "observed" else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
def _named_id(row):
    if row.get("schema_version") == 2 and "run_id" in row and "tokens_input" in row:
        return str(row["run_id"])
    if row.get("type") == "architect-run":
        return str(row["run_id"]) if row.get("run_id") else (f"plan:{row['plan']}" if isinstance(row.get("plan"), str) and row["plan"] else None)
    return None
def batch_summary(batch_path, data_path):
    shape = "batch: must be an object with a name and a list of run ids"
    try:
        raw = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanningStatsError(shape) from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw.get("name") or not isinstance(raw.get("run_ids"), list) or not all(isinstance(r, str) and r for r in raw["run_ids"]):
        raise PlanningStatsError(shape)
    name, run_ids = raw["name"], raw["run_ids"]
    if len(run_ids) < 10:
        raise PlanningStatsError(f"batch {name}: {len(run_ids)} runs; a batch needs at least 10")
    parents, plus, calls, done, miss_sub, miss_calls, seen = [], [], [], 0, False, False, set()
    by_id, canonical = defaultdict(set), {}
    with Path(data_path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PlanningStatsError(f"line {number}: not JSON") from exc
            if not isinstance(row, dict):
                continue
            named = _named_id(row)
            if named is None:
                continue
            identity = json.dumps(row, sort_keys=True)
            if identity in by_id[named]:
                continue
            by_id[named].add(identity)
            canonical.setdefault(named, row)
    for run_id in run_ids:
        if run_id in seen:
            raise PlanningStatsError(f"batch {name}: duplicate run id {run_id}")
        seen.add(run_id)
        if run_id not in canonical:
            raise PlanningStatsError(f"run {run_id}: not found")
        if len(by_id[run_id]) > 1:
            raise PlanningStatsError(f"run {run_id}: {len(by_id[run_id])} different rows")
        row = canonical[run_id]
        if row.get("schema_version") == 2 and "tokens_input" in row:
            parts = [_obs(row.get(k)) for k in ("tokens_input", "tokens_output", "tokens_cache")]
            parent = sum(parts) if all(p is not None for p in parts) and sum(parts) > 0 else None
            block = row["subagents"] if isinstance(row.get("subagents"), dict) else {}
            sub_calls, sub_tokens = _obs(block.get("calls")), _obs(block.get("tokens"))
            is_done = row.get("outcome") == "completed"
            if row.get("outcome") != "completed":
                raise PlanningStatsError(f"run {run_id}: no completed receipt ({row.get('outcome')})")
        else:
            keys = ("input_tokens", "output_tokens", "cache_read_tokens")
            parent = None
            if all(k in row for k in keys):
                counts = []
                for key in keys:
                    value = row[key]
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                        raise PlanningStatsError(f"run {run_id}: {key} must be a non-negative integer")
                    counts.append(value)
                parent = sum(counts) if any(counts) else None
            stats = row["subagent_stats"] if isinstance(row.get("subagent_stats"), dict) else {}
            spawned = stats.get("spawned")
            if isinstance(spawned, bool) or not isinstance(spawned, int) or spawned < 0:
                sub_calls, sub_tokens = None, None
            elif spawned == 0:
                sub_calls, sub_tokens = 0, 0
            else:
                sub_calls, sub_tokens = spawned, None
            is_done = row.get("outcome") == "done"
        if row.get("failure_class") == "environment":
            raise PlanningStatsError(f"run {run_id}: failure class environment")
        if parent is None:
            raise PlanningStatsError(f"run {run_id}: unmeasured tokens")
        parents.append(parent)
        if sub_tokens is None:
            miss_sub = True
        else:
            plus.append(parent + sub_tokens)
        if sub_calls is None:
            miss_calls = True
        else:
            calls.append(sub_calls)
        done += int(is_done)
    return {"batch": name, "runs": len(run_ids), "median_parent_total": median(parents), "median_parent_plus_subagent_total": None if miss_sub else median(plus), "median_subagent_calls": None if miss_calls else median(calls), "done": done}
def summarize(path):
    groups = defaultdict(list)
    all_values = []
    seen = set()
    duplicates = unmeasured = 0
    keys = ("input_tokens", "output_tokens", "cache_read_tokens")
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PlanningStatsError(f"line {number}: not JSON") from exc
            if not isinstance(row, dict) or row.get("type") != "architect-run":
                continue
            identity = json.dumps(row, sort_keys=True)
            if identity in seen:
                duplicates += 1
                continue
            seen.add(identity)
            if any(key not in row for key in keys):
                unmeasured += 1
                continue
            counts = []
            for key in keys:
                value = row[key]
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise PlanningStatsError(
                        f"line {number}: {key} must be a non-negative integer"
                    )
                counts.append(value)
            if not any(counts):
                unmeasured += 1
                continue
            total = sum(counts)
            group = (str(row.get("seat", "unknown")), str(row.get("model", "unknown")))
            groups[group].append(total)
            all_values.append(total)
    return {
        "groups": [
            {"seat": seat, "model": model, "runs": len(values), "median_total": median(values)}
            for (seat, model), values in sorted(groups.items())
        ],
        "all": {"runs": len(all_values), "median_total": median(all_values)},
        "duplicates": duplicates,
        "unmeasured": unmeasured,
    }

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "batch":
        if len(argv) != 3:
            print("planning_stats: expected batch <batch.json> <data.jsonl>", file=sys.stderr)
            return 2
        try:
            result = batch_summary(argv[1], argv[2])
        except (PlanningStatsError, OSError, UnicodeDecodeError) as exc:
            print(f"planning_stats: {exc}", file=sys.stderr)
            return 2
        fmt = lambda value: "unknown" if value is None else str(value)
        for row in (("batch", result["batch"]), ("runs", str(result["runs"])), ("median_parent_total", str(result["median_parent_total"])), ("median_parent_plus_subagent_total", fmt(result["median_parent_plus_subagent_total"])), ("median_subagent_calls", fmt(result["median_subagent_calls"])), ("done_rate", f"{result['done']}/{result['runs']}")):
            print("\t".join(row))
        return 0
    if len(argv) != 1:
        print("planning_stats: expected one file path", file=sys.stderr)
        return 2
    try:
        result = summarize(argv[0])
    except (PlanningStatsError, OSError, UnicodeDecodeError) as exc:
        print(f"planning_stats: {exc}", file=sys.stderr)
        return 2
    rows = [["seat", "model", "runs", "median_total"]]
    rows.extend(
        [group["seat"], group["model"], str(group["runs"]), str(group["median_total"])]
        for group in result["groups"]
    )
    total = result["all"]
    rows.append(["all", "all", str(total["runs"]), str(total["median_total"] or "unknown")])
    rows.extend([["duplicates", str(result["duplicates"])], ["unmeasured", str(result["unmeasured"]) ]])
    for row in rows:
        print("\t".join(row))
    return 0

if __name__ == "__main__":
    sys.exit(main())
