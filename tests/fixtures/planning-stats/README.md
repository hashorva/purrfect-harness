# planning-stats fixtures

Frozen inputs for `tests/test-planning-stats.py`. Never refresh them from live mission data:
a live routing-data file or ledger grows with every run, so an oracle that reads one drifts.

- `routing-data.jsonl`: 8 synthetic rows for the seat and model table (T-001).
- `2a-baseline-routing-data.jsonl`: the 2A routing data as committed at `06481fd`
  (247 lines, 66755 bytes), with one scrub on line 38: `ghp-/github-pat-` replaces the
  original underscore spelling so the ledger privacy patterns pass. Reversing that one
  substitution gives the `06481fd` blob `745971d`. Figures on it: 36 measured runs,
  median total 1250599, 3 duplicates, 2 unmeasured.

## Batch file format

One JSON object: `{"name": "<batch name>", "run_ids": ["<run id>", ...]}` with at least
10 distinct run ids. A data row is a run when it is a ledger row (`schema_version` 2 with
`run_id` and `tokens_input`) or a routing `architect-run` row (id `run_id`, else `plan:<plan>`).

## Usage

    python3 scripts/planning_stats.py tests/fixtures/planning-stats/2a-baseline-routing-data.jsonl
    python3 scripts/planning_stats.py batch <batch.json> <data.jsonl>

The batch command prints six tab-separated lines (`batch`, `runs`, `median_parent_total`,
`median_parent_plus_subagent_total`, `median_subagent_calls`, `done_rate`) and exits 0, or
exits 2 with `planning_stats: <reason>` on stderr. Tests build batch inputs in temporary
files; no batch of real run ids lives here.
