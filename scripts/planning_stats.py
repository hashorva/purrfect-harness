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
