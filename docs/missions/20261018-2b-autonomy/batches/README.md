# F001 batches

Batch JSON: `name` and `run_ids` (10 clean `claude.brain-planning` runs). `f001-after.json` also has `review_runs` (claude review ids in the same window); before may omit it.

Front Desk writes `f001-after.json` from the first 10 clean planning runs after T-005, using `python3 scripts/brain_prompt.py planning <mission> --provider claude`.

    python3 scripts/planning_stats.py compare docs/missions/20261018-2b-autonomy/batches/f001-before.json docs/missions/20261018-2b-autonomy/batches/f001-after.json docs/missions/ledger.jsonl docs/missions/20261014-2a-foundation/routing-data.jsonl

Exit 0 pass, 1 per failing condition, 2 on bad input. Local-only (like 2A F001 step 5).
