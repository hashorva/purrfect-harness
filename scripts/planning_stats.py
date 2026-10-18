#!/usr/bin/env python3
"""Summarize planning-run token counts by seat and model, or for a named batch of runs.

Usage:
  python3 scripts/planning_stats.py <routing-data.jsonl>
  python3 scripts/planning_stats.py batch <batch.json> <data.jsonl>

Batch file: one JSON object, {"name": "<batch name>", "run_ids": ["<run id>", ...]}.
  name is a non-empty string; run_ids holds at least 10 distinct non-empty strings.
  Run ids are opaque: they are matched as written, never parsed.

Data file: UTF-8 JSONL. Two kinds of row are runs; every other row is ignored:
  ledger row: schema_version 2 with run_id and tokens_input; its id is run_id.
  routing planning row: type architect-run; its id is run_id, else plan:<plan>.
  Exact duplicate rows count once; two different rows with one id are refused.

Output: six tab-separated lines: batch, runs, median_parent_total,
  median_parent_plus_subagent_total, median_subagent_calls (unknown when any
  run's count is unknown) and done_rate <done>/<runs>. Exit 0 on success; exit 2
  with planning_stats: <reason> on stderr for a refused batch or unreadable data.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import run_id

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
_REVIEW_MSG = "after batch: review_runs must be a list of distinct canonical run ids"
def _index_data_paths(data_paths):
    by_id, canonical = defaultdict(set), {}
    for data_path in data_paths:
        with Path(data_path).open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise PlanningStatsError(f"line {number}: not JSON") from exc
                if not isinstance(row, dict) or (named := _named_id(row)) is None:
                    continue
                identity = json.dumps(row, sort_keys=True)
                if identity not in by_id[named]:
                    by_id[named].add(identity)
                    canonical.setdefault(named, row)
    return by_id, canonical
def _subagent_from_row(row, run_id):
    if row.get("schema_version") == 2 and "tokens_input" in row:
        block = row["subagents"] if isinstance(row.get("subagents"), dict) else {}
        calls_f = block.get("calls") if isinstance(block.get("calls"), dict) else {}
        tokens_f = block.get("tokens") if isinstance(block.get("tokens"), dict) else {}
        calls, tokens = _obs(calls_f), _obs(tokens_f)
        source = "observed" if calls_f.get("source") == "observed" and tokens_f.get("source") == "observed" else str(calls_f.get("source") or tokens_f.get("source") or "unknown")
        return {"calls": calls, "tokens": tokens, "source": source}
    spawned = (row.get("subagent_stats") or {}).get("spawned") if isinstance(row.get("subagent_stats"), dict) else None
    if isinstance(spawned, bool) or not isinstance(spawned, int) or spawned < 0:
        return {"calls": None, "tokens": None, "source": "unknown"}
    return {"calls": 0, "tokens": 0, "source": "observed"} if spawned == 0 else {"calls": spawned, "tokens": None, "source": "observed"}
def _batch_row_metrics(row, run_id):
    if row.get("schema_version") == 2 and "tokens_input" in row:
        parts = [_obs(row.get(k)) for k in ("tokens_input", "tokens_output", "tokens_cache")]
        parent = sum(parts) if all(p is not None for p in parts) and sum(parts) > 0 else None
        if row.get("outcome") != "completed":
            raise PlanningStatsError(f"run {run_id}: no completed receipt ({row.get('outcome')})")
        outcome = "done"
    else:
        keys = ("input_tokens", "output_tokens", "cache_read_tokens")
        parent = None
        if all(k in row for k in keys):
            counts = [row[key] for key in keys]
            if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
                bad = next(key for key in keys if isinstance(row[key], bool) or not isinstance(row[key], int) or row[key] < 0)
                raise PlanningStatsError(f"run {run_id}: {bad} must be a non-negative integer")
            parent = sum(counts) if any(counts) else None
        outcome = "done" if row.get("outcome") == "done" else str(row.get("outcome", "failed"))
    if row.get("failure_class") == "environment":
        raise PlanningStatsError(f"run {run_id}: failure class environment")
    if parent is None:
        raise PlanningStatsError(f"run {run_id}: unmeasured tokens")
    return parent, _subagent_from_row(row, run_id), outcome
def _parent_plus_median(rows):
    totals = [row["parent_total"] + row["subagent"]["tokens"] for row in rows if isinstance(row["subagent"]["tokens"], int)]
    return None if len(totals) != len(rows) else median(totals)
def compare_reports(before, after, reviews):
    fails = []
    m = median([row["parent_total"] for row in after])
    if m is not None and m >= 1_000_000:
        fails.append(f"after median parent total {m} is not under 1000000")
    b_med, a_med = _parent_plus_median(before), _parent_plus_median(after)
    if b_med is None:
        fails.append("before median parent-plus-subagent total is unknown")
    if a_med is None:
        fails.append("after median parent-plus-subagent total is unknown")
    if b_med is not None and a_med is not None and a_med >= b_med:
        fails.append(f"after median parent-plus-subagent total {a_med} is not below before {b_med}")
    for row in after + reviews:
        calls, source = row["subagent"].get("calls"), row["subagent"].get("source")
        if not (isinstance(calls, int) and calls >= 1) or source != "observed":
            fails.append(f"{row['ref']}: subagent calls {calls} source {source}; need at least 1 observed")
    before_done, after_done = sum(row["outcome"] == "done" for row in before), sum(row["outcome"] == "done" for row in after)
    if after_done * len(before) < before_done * len(after):
        fails.append(f"after done rate {after_done}/{len(after)} is below before {before_done}/{len(before)}")
    return fails
def read_review_runs(path):
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanningStatsError(_REVIEW_MSG) from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("review_runs"), list):
        raise PlanningStatsError(_REVIEW_MSG)
    seen, out = set(), []
    for item in raw["review_runs"]:
        run_id.validate_run_id(item)
        if item in seen:
            raise PlanningStatsError(_REVIEW_MSG)
        seen.add(item)
        out.append(item)
    return out
def batch_rows(batch_path, data_paths):
    shape = "batch: must be an object with a name and a list of run ids"
    try:
        raw = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanningStatsError(shape) from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw.get("name") or not isinstance(raw.get("run_ids"), list) or not all(isinstance(r, str) and r for r in raw["run_ids"]):
        raise PlanningStatsError(shape)
    name, run_ids = raw["name"], raw["run_ids"]
    if len(run_ids) != 10:
        raise PlanningStatsError(f"batch {name}: {len(run_ids)} runs; a batch needs exactly 10")
    by_id, canonical = _index_data_paths(data_paths)
    rows, seen = [], set()
    for rid in run_ids:
        if rid in seen:
            raise PlanningStatsError(f"batch {name}: duplicate run id {rid}")
        seen.add(rid)
        if rid not in canonical or len(by_id[rid]) > 1:
            raise PlanningStatsError(f"run {rid}: not found" if rid not in canonical else f"run {rid}: {len(by_id[rid])} different rows")
        parent, agent, outcome = _batch_row_metrics(canonical[rid], rid)
        rows.append({"ref": rid, "parent_total": parent, "subagent": agent, "outcome": outcome})
    return rows
def review_rows(run_ids, data_paths):
    by_id, canonical = _index_data_paths(data_paths)
    rows = []
    for rid in run_ids:
        n = 0 if rid not in canonical else len(by_id[rid])
        if n != 1:
            raise PlanningStatsError(f"review run {rid}: {n} rows")
        rows.append({"ref": rid, "subagent": _subagent_from_row(canonical[rid], rid)})
    return rows
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
    by_id, canonical = _index_data_paths([data_path])
    for run_id in run_ids:
        if run_id in seen:
            raise PlanningStatsError(f"batch {name}: duplicate run id {run_id}")
        seen.add(run_id)
        if run_id not in canonical:
            raise PlanningStatsError(f"run {run_id}: not found")
        if len(by_id[run_id]) > 1:
            raise PlanningStatsError(f"run {run_id}: {len(by_id[run_id])} different rows")
        row = canonical[run_id]
        parent, agent, outcome = _batch_row_metrics(row, run_id)
        sub_calls, sub_tokens = agent["calls"], agent["tokens"]
        is_done = outcome == "done"
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
    if argv and argv[0] == "compare":
        if len(argv) < 4:
            print("planning_stats: expected compare <before.json> <after.json> <data> [<data> ...]", file=sys.stderr)
            return 2
        data = argv[3:]
        try:
            review_ids = read_review_runs(argv[2])
            fails = compare_reports(batch_rows(argv[1], data), batch_rows(argv[2], data), review_rows(review_ids, data))
        except (PlanningStatsError, OSError, UnicodeDecodeError, ValueError) as exc:
            print(f"planning_stats: {exc}", file=sys.stderr)
            return 2
        if fails:
            for message in fails:
                print("\t".join(("compare", "fail", message)))
            return 1
        print("\t".join(("compare", "pass")))
        return 0
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
