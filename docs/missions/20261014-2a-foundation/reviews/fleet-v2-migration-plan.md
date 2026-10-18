# Fleet v1 -> v2 migration plan: 2A brain on agy Opus

Architect (Opus brain run 7fba6dca-fbcf-456d-82ab-c36086aedc69), 2026-10-16. Planning only: no diff reviewed, no real provider CLI run. Every result below comes from scratch clones with fake CLIs.

## Answer

Not data-only. The data migration works, but three things must come first:

1. **T-062 (code, GUARD, Opus review)**: two test files use the live mission fleet as their v1 fixture, and `probe_seat.py` and `seat_smoke.py` read only v1 seat fields. The first `cursor.premium` dispatch would also write a false drift row (`agent` -> `cursor`, same model). Without T-062 the full suite goes red on the migration commit, and `probe-seat.sh` and `fleet-doctor.sh --smoke` stop working.
2. **A fresh inventory**: today's `.tasks/fleet-inventory.json` (sha256 `3e8ced08…`, probed 2026-10-14T15:00:44Z, the one the v1 fleet froze) is **invalid under today's registry**. Its seat `agy.premium` has family `pro`; T-060 made it `argon`, so `validate-inventory` exits 1. Every v2 resolve validates the inventory, so every v2 dispatch would fail. `fleet-inventory.sh` also refuses to re-probe while that file exists, because it validates the prior file first. v1 dispatch is unaffected because v1 never reads the inventory.
3. **Then data**: `freeze-v2`, one brain drift row, one commit.

Order: T-062 accepted -> fresh inventory -> freeze-v2 -> drift row -> commit -> first agy brain run.

## How the fleet is read today

| Reader | What it does | v2 effect |
| --- | --- | --- |
| `dispatch_policy.py:93` `approved_fleet` (validate-worker, validate-brain review) | Requires canonical JSON, `validate_fleet` (v1 or v2), and checks the mission path. | Works. |
| `spawn-worker.sh:197` `fleet_state.py resolve` with `--provider/--effort/--speed`, `--inventory .tasks/fleet-inventory.json`, `--root` | v1: seat lookup; the inventory is ignored. v2: `resolve_v2` (validates fleet and inventory; first usable door; newest family model; never fast unless policy) then `drift()`. | Same spec and argv for all 8 worker seats (dry run). The provider assertion maps `agent` to `cursor`. |
| `spawn-brain.sh` review: `resolve --seat brain` | Uses the returned provider, model, effort and speed. | `provider=agy model=claude-opus-5-5-high effort=high`; agy contract 8 argv (dry run). |
| `probe_seat.py:99` `_seat` | Reads `seat.provider` and `seat.model`. | Breaks ("unknown or invalid frozen seat", exit 2). Fixed by T-062. |
| `seat_smoke.py` (`smoke_argv`, `is_fast`, `smoke_seat`) | Reads v1 fields; does not copy the inventory into its clone. | Breaks (25 test errors). Fixed by T-062. |
| `tests/test-fleet-v2.py:335`, `tests/test-seat-smoke.py:103` | Use the live fleet as the v1 fixture. | Fail. Fixed by T-062 (frozen copy under `tests/fixtures/fleet/`). `tests/test-registry.py:326` copies the live fleet but is unaffected. |
| Verifier, spec, receipt, record, ledger (`verification_record.py`, `verify-mission.sh`, `execution_spec.py`, `execution_receipt.py`, `ledger.py`) | Never read `fleet.json`. No fleet hash anywhere. The only inventory hash is in drift rows. | Nothing recorded breaks (below). |

**Runs already recorded:** specs, receipts and VerificationRecords hold no fleet or inventory hash (grep: 0 references in the verifier path). `verify-mission.sh --run-id` re-runs a task's checks in a clean worktree at the receipt's commit, so it sees the v1 fleet of that commit. Old tasks whose checks run `validate-fleet` on the mission fleet pass for v1 and v2. The audit (`verify-mission.sh`, `--require-workers`) read nothing from the fleet: VERIFY OK on the live tree today. Drift rows keep the old inventory sha `3e8ced…` as history; keep that file (step 2 renames it).

## Two v2 semantics you are signing up for

- **v2 does not pin a model.** At every dispatch a seat takes the newest model of its family in `.tasks/fleet-inventory.json`, through its first usable door, and the change is logged as a drift row. `approved_resolution` is the reference for drift, not a pin. A later re-probe that lists, for example, `gpt-6-terra` would move `codex.premium` at its next dispatch. Re-probe only on purpose.
- **The claude door is an automatic fallback only when the inventory says agy is unusable** (agy probe failed, or no `opus` model listed). A hang inside a turn, the old agy failure mode, does not change the inventory, and `--provider claude` is refused (`fleet provider assertion failed`, checked). For a manual fallback, use Rollback (R) below. A door selector (`--provider` chooses among the seat's doors and writes a drift row) would loosen a gate and is not planned. It is your decision; it would be T-063.

## Does the inventory list `claude-opus-5-5-high` under agy?

Yes, in today's file: agy `observed_models` holds `claude-opus-5-5-low/medium/high` (and sonnet). It lists **no** `gemini-4-argon-*` under agy; Argon appears only under cursor. So `agy.premium` would resolve as unavailable even if the file were valid, and `freeze-v2` refuses that binding. The fresh probe must show both `claude-opus-5-5-high` and `gemini-4-argon-high` under agy (step 2 stops otherwise).

## freeze-v2 arguments

`fleet_state.py freeze-v2 --mission-dir docs/missions/20261014-2a-foundation --inventory .tasks/fleet-inventory.json --bindings $E/bindings.json --policy $E/policy.json --approved-by "Zamir" --approved-at <UTC now>`

- It refuses an existing `fleet.json` (no-clobber), so remove the file first. It writes the file read-only and canonical, with `mission.path` exactly as given (run from the repo root with the relative path).
- Bindings take `family, effort, doors, speed` only. `approved_resolution` is computed by `resolve_v2` from the inventory, so it equals today's values only if the inventory resolves to them (step 5 checks this).
- `bindings.json`:

```json
{"brain":{"family":"opus","effort":"high","doors":["agy","claude"],"speed":"unknown"},
 "agy.economy":{"family":"flash","effort":"medium","doors":["agy"],"speed":"unknown"},
 "agy.premium":{"family":"argon","effort":"high","doors":["agy-argon"],"speed":"unknown"},
 "claude.economy":{"family":"haiku","effort":"medium","doors":["claude"],"speed":"unknown"},
 "claude.premium":{"family":"sonnet","effort":"medium","doors":["claude"],"speed":"unknown"},
 "codex.economy":{"family":"luna","effort":"medium","doors":["codex"],"speed":"unknown"},
 "codex.premium":{"family":"terra","effort":"medium","doors":["codex"],"speed":"unknown"},
 "cursor.economy":{"family":"composer","effort":"medium","doors":["cursor-composer"],"speed":"standard"},
 "cursor.premium":{"family":"grok","effort":"high","doors":["cursor-grok"],"speed":"standard"}}
```

- `policy.json`: `{"billing_classes":["included"],"fast":false,"no_zdr":"forbid"}`. "No credits" is `included` only. "Never fast" is `fast: false` (fast models are filtered out even when listed). `forbid` costs nothing today (no door is no-ZDR) and is the stricter choice; `allow` (the T-026 fixture value) gives the same result today.
- Expected `approved_resolution` (dry run, identical to today's v1 values; Cursor is written with its canonical name `cursor`, which is the v1 `agent`): brain agy `claude-opus-5-5-high`/high/unknown; agy.economy agy `gemini-3.8-flash-medium`/medium; agy.premium agy `gemini-4-argon-high`/high; claude.economy `haiku`/medium; claude.premium `sonnet`/medium; codex.economy `gpt-6-luna`/medium; codex.premium `gpt-5.6-terra`/medium; cursor.economy cursor `composer-2.5`/medium/standard; cursor.premium cursor `grok-4.7-high`/high/standard.

## Procedure (Front Desk)

0. Preconditions: T-062 accepted (verified and reviewed); clean tree; no worker or brain running; `bash scripts/fleet-doctor.sh` without ERROR. `E=$(mktemp -d)`; `BASE=$(git rev-parse HEAD)`; `cp -p docs/missions/20261014-2a-foundation/fleet.json $E/fleet.v1.json`.
1. Write `$E/bindings.json` and `$E/policy.json` exactly as above.
2. Inventory: `mv .tasks/fleet-inventory.json .tasks/fleet-inventory.3e8ced.json` (keep it: drift rows cite it), then `bash scripts/fleet-inventory.sh`, then `python3 scripts/fleet_state.py validate-inventory .tasks/fleet-inventory.json`. **STOP** unless agy is `success` and lists `claude-opus-5-5-high` and `gemini-4-argon-high`. Rollback for this step: `mv .tasks/fleet-inventory.json $E/` and move the old one back (v1 ignores the inventory either way).
3. `rm docs/missions/20261014-2a-foundation/fleet.json`, then the freeze-v2 command above. On any non-zero exit: `git checkout -- docs/missions/20261014-2a-foundation/fleet.json` and **STOP**.
4. `python3 scripts/fleet_state.py validate-fleet docs/missions/20261014-2a-foundation/fleet.json` must exit 0.
5. Compare `approved_resolution` with `$E/fleet.v1.json` (read v1 `agent` as `cursor`). **STOP** and restore with `git checkout` if any seat other than brain differs, for example because a newer codex or grok model appeared. That is your decision, not the Front Desk's.
6. Pre-flight without drift writes: `python3 scripts/fleet_state.py resolve-v2 --fleet docs/missions/20261014-2a-foundation/fleet.json --seat <seat> --inventory .tasks/fleet-inventory.json` for all 9 seats; each must exit 0 with the values above.
7. Brain drift row: append one line to `.tasks/drift/20261014-2a-foundation.jsonl`. The `:` separators carry no spaces. `NEW` is the fresh inventory sha256.
   `{"at":"<UTC now>","from":{"effort":"high","model":"opus","provider":"claude","speed":"unknown"},"inventory_sha256":"<NEW>","mission":"docs/missions/20261014-2a-foundation","seat":"brain","to":{"effort":"high","model":"claude-opus-5-5-high","provider":"agy","speed":"unknown"}}`
   With T-062, no other seat writes a row; the dry run shows 0 rows from 8 worker dispatches and 1 brain review.
8. Optional admission evidence for the brain seat, as for agy.economy and agy.premium: `bash scripts/probe-seat.sh brain` x3 (needs T-062; it runs agy `claude-opus-5-5-high`).
9. Commit `fleet.json` with your PROGRESS entry: `docs(mission): fleet v2; brain on agy Opus (drift event)`. `drift.jsonl` is folded at the next acceptance, as before.
10. First live brain run: `bash scripts/spawn-brain.sh docs/missions/20261014-2a-foundation review`. The log's first line must read `provider=agy model=claude-opus-5-5-high`, and the receipt must be completed. If it hangs or fails, do R.

## Rollback (R)

1. `git checkout $BASE -- docs/missions/20261014-2a-foundation/fleet.json`, then `cmp` it with `$E/fleet.v1.json`, then commit `docs(mission): fleet back to v1 (brain on claude)`. Or `git revert` the migration commit.
2. Append the reverse drift row: `from` agy `claude-opus-5-5-high`, `to` claude `opus`, same keys and inventory sha.
3. Keep the fresh inventory; v1 ignores it. Do not restore `3e8ced…` as the live file; it is invalid under today's registry.
4. Dry run: after rollback, `validate-fleet` exit 0, the brain review is back to claude `opus` (claude argv), and all 8 worker dispatches equal the pre-migration ones.

## Dry run (scratch clones of f5870cc, fake claude/codex/cursor-agent/agy, fake HOME for the codex model cache)

Script: `/private/tmp/claude-501/-Users-zamirhashorva-dev-purrfect-harness/6098bedf-2c8b-4dd1-b75d-f2e480758d0f/scratchpad/dryrun/run.sh` (with `fakes.sh`); outputs `/private/tmp/claude-501/-Users-zamirhashorva-dev-purrfect-harness/6098bedf-2c8b-4dd1-b75d-f2e480758d0f/scratchpad/out-data-only.txt` and `/private/tmp/claude-501/-Users-zamirhashorva-dev-purrfect-harness/6098bedf-2c8b-4dd1-b75d-f2e480758d0f/scratchpad/out-with-t062.txt`.

| Step | Data only (HEAD) | With T-062 reference |
| --- | --- | --- |
| freeze-v2 on today's inventory | exit 1 (`inventory.seats.agy.premium … provider/family`) | same |
| `fleet-inventory.sh` over today's file | exit 1 (same message); fresh probe after `mv` exits 0 | same |
| freeze-v2 on the fresh inventory; `validate-fleet`; JSON Schema | exit 0, exit 0, ok; 8 of 8 seats SAME, brain agy | same |
| 8 worker dispatches, v1 vs v2 (provider, model, effort, speed, argv) | 8 of 8 UNCHANGED | 8 of 8 UNCHANGED |
| brain review | `agy --dangerously-skip-permissions --print-timeout 30m --model claude-opus-5-5-high --output-format stream-json -p <PROMPT>` (contract 8) | same |
| drift rows from those 9 dispatches | 1 false row (cursor.premium `agent` -> `cursor`, grok-4.7-high) | 0 |
| `ledger.py fold` | exit 0 | exit 0 |
| `test-fleet-v2.py` / `test-seat-smoke.py` / `probe-seat --dry-run` | exit 1 / 25 errors / exit 2 | exit 0 / OK / exit 0 |
| rollback: validate, brain argv, worker dispatches | exit 0, claude opus, equal to v1 | same |
| brain fallback: agy record failed in the inventory | resolves claude `opus` and writes 1 drift row; `--provider claude` while agy is up: refused | same |

`verify-mission.sh` cannot run in a clone, because receipts carry the live repo's absolute spec path. On the live tree (read-only) it gives VERIFY OK and `--require-workers` VERIFY OK. The audit code never reads the fleet, so the fleet version cannot change its result.

## T-062

See `tasks/T-062.md` (feature F009, GUARD/Opus review, claude.premium; alternate codex.premium). Reference patch outside the repo: `/private/tmp/claude-501/-Users-zamirhashorva-dev-purrfect-harness/6098bedf-2c8b-4dd1-b75d-f2e480758d0f/scratchpad/t062/T-062-reference.patch`, sha256 `809fc3fb8e9afac76328abbc1fe99502d83f10879fabd83f269480db11b9f724` (7 files, +233/-8). Oracle: 11 of 11 mutants caught, each by the oracle's own drift, probe, smoke or fixture checks before it runs the worker's tests. Rule 6 (scratch clone, task committed at base 2fa1941, then the reference patch applied as 096962d): the task parses (9 commands), `validate-worker` admits claude and codex; at base the oracle exits 1 and the other 8 exit 0; after the edit all 9 exit 0, including `bash tests/run-tests.sh` (ALL TESTS PASSED). The reference full suite also passed separately (119 ok).

Residual (non-blocking): a seat-smoke dry-run plan carries no model, so `seat_views` using `approved_resolution` instead of `resolve_v2` is invisible to the oracle while the two are equal. The worker's launch test covers the reported model.
