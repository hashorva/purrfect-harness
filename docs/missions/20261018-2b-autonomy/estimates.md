# 2B estimates (ESTIMATED — every number here has source `estimated`)

These numbers plan Gate 0. They are not readings. After the first measured batches, the F002 meter replaces the per-run quota constants with observed before and after deltas. The gate reports compare the two.

## Inputs

- 2A outcomes (`routing-data.jsonl`, 159 run rows; the owner's brief said 158 runs and 100 done):

  | Outcome | Runs | Share |
  | --- | --- | --- |
  | done | 112 | 70% |
  | verify-passed-review-failed | 16 | 10% |
  | verify-failed | 17 | 11% |
  | scope-failed | 6 | 4% |
  | other | 8 | 5% |

  The 8 "other" runs are: failed 4, baseline-stopped 2, no-change 1, seat-limit 1.
- Worker runs per task: 1 / 0.70 ≈ 1.43, rounded up to **1.45**.
- Review runs per task: about 80% of runs reach review, plus a re-review after each fix: **1.2**.
- Planner runs per feature: at most 3 tasks per run, plus oracle repairs and splits: **ceil(1.3 × ceil(tasks / 3))**. There is also one brain run per gate: 6 gates (G1–G6).
- 2A worker mix (done runs): cursor 41%, codex 35%, claude 18%, agy 6%. About 10% of runs escalate to a premium or mid seat.
- Until F012 is accepted, there are no Claude worker runs. The claude share moves to cursor and codex, which changes the totals by less than 1 pp per pool.
- Review mix under the different-vendor rule: Sol 30%, Grok 25%, Argon 20%, Opus 25%. F000 is mostly guard code, so Opus takes about 10 of its 15 reviews.
- Planner mix: Opus 80%, Argon 10%, Sol 10%.
- Planning tokens: the 2A baseline median is 1,233,224 (Opus 1,816,741). The 2B target is under 1,000,000. The per-run budgets in the prompts are planning 1,000,000 and review 400,000.

## Per-run quota cost

Costs are in percentage points (pp) of the pool's weekly window, the unit in which the meter reports a drop in percent left.

| Pool | Run | pp of week | Basis |
| --- | --- | --- | --- |
| anthropic | Opus planning / gate | 2.5 | assumed: no limit was hit on 2026-10-18 with about 10 Opus planning runs, 4 reviews and the Front Desk |
| anthropic | Opus review | 1.0 | assumed (about 0.4 of a planning run's tokens) |
| anthropic | Haiku worker / Sonnet-Opus escalation | 0.4 / 1.5 | assumed |
| openai | Luna worker / Terra-Sol escalation | 0.8 / 1.5 | assumed at a third of the upper bound of 2.6 (38 codex.economy runs over 5 days with no limit) |
| openai | Sol review / Sol planning | 1.2 / 3.0 | assumed |
| cursor | Composer worker / Grok review or escalation | 0.5 / 0.8–1.0 | assumed; upper bound 2.2 (46 cursor.economy runs with no limit) |
| agy-argon | Argon review / Argon planning | 2.5 / 6.0 | 5–7 per planning run: two weekly 429s (resets 155 h and 161 h) after about 15–20 Argon planning runs |
| google | Flash worker | 1.0 | assumed (5 runs only) |

The Front Desk's own Claude use (Sonnet) and claude.ai chat also come out of the anthropic pool, and they are not counted below. The explorer subagent runs on Haiku inside a Claude brain run, so its cost is part of that run's anthropic cost.

## Per feature (in run order)

Column key:
- W: worker runs, including expected retries. Of W, about 70% are done, 10% review-failed, 11% verify-failed, 4% scope-failed and 5% other.
- R: review runs.
- P: planner runs.
- Quota columns: pp of one week's window for that pool, over the whole feature.

| Feature | Tasks | W | R | P | anthropic | openai | cursor | agy-argon | google |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F000 safety net | 12 | 18 | 15 | 6 | 23.5 | 9.8 | 5.4 | 8.5 | 1.1 |
| F001 delegation (measured) | 6 | 9 | 8 | 3 | 8.6 | 6.4 | 3.7 | 6.3 | 0.5 |
| F002 quota meter | 6 | 9 | 8 | 3 | 8.6 | 6.4 | 3.7 | 6.3 | 0.5 |
| F004 structured progress | 5 | 8 | 6 | 3 | 8.2 | 5.5 | 3.1 | 5.6 | 0.5 |
| F003 loop driver | 6 | 9 | 8 | 3 | 8.6 | 6.4 | 3.7 | 6.3 | 0.5 |
| F005 worker inner loop | 4 | 6 | 5 | 3 | 7.8 | 4.5 | 2.4 | 4.9 | 0.4 |
| F006 task-size signal | 2 | 3 | 3 | 2 | 4.9 | 2.4 | 1.2 | 2.8 | 0.2 |
| F007 parallel lanes | 5 | 8 | 6 | 3 | 8.2 | 5.5 | 3.1 | 5.6 | 0.5 |
| F008 board | 3 | 5 | 4 | 2 | 5.3 | 3.3 | 1.8 | 3.5 | 0.3 |
| F009 benchmark (build) | 4 | 6 | 5 | 3 | 7.8 | 4.5 | 2.4 | 4.9 | 0.4 |
| F010 Front Desk skills | 2 | 3 | 3 | 2 | 4.9 | 2.4 | 1.2 | 2.8 | 0.2 |
| F011 prediction | 2 | 3 | 3 | 2 | 4.9 | 2.4 | 1.2 | 2.8 | 0.2 |
| F012 sandbox | 3 | 5 | 4 | 2 | 5.3 | 3.3 | 1.8 | 3.5 | 0.3 |
| Gate runs (G1–G6) | – | – | – | 6 | 12.0 | 1.5 | – | 4.0 | – |
| **Total** | **60** | **92** | **78** | **43** | **119** | **64** | **35** | **68** | **6** |

### Method

Each feature's cost is tasks × the per-task cost plus P × the per-planner cost, using these mix-weighted rates:

| Rate (pp) | anthropic | openai | cursor | agy-argon | google |
| --- | --- | --- | --- | --- | --- |
| Per task (workers plus reviews) | 0.44 | 0.94 | 0.61 | 0.72 | 0.09 |
| Per planner run | 2.0 | 0.25 | – | 0.67 | – |

F000 adds a guard-review adjustment. Opus reviews 10 of its 15 runs instead of the mix's 3.75, which adds 6.25 pp to anthropic. The other review pools drop accordingly: openai −3.0, cursor −1.9, agy-argon −4.2.

The F001 before and after batches are not extra runs:
- The before batch is the 10 clean claude.brain-planning runs made before the F001 prompt change: F000 and early F001 planning, topped up from the latest clean 2A Opus planning rows.
- The after batch is the first 10 clean planning runs after the change, made during F001–F003 work.
- A dedicated replay batch of 10 Opus planning runs would cost about 25 pp of anthropic each time. It is not planned.

### Assumed task split

- **F000 (12 tasks; most are guard code):**
  1. golden argv fixture and test;
  2. base-compare check and its CI step;
  3. `verify-mission.sh --receipts-dir`;
  4. the committed 2A receipt fixture and the CI audit step;
  5. the CI matrix (two operating systems × Python 3.12 and 3.14) and the version print;
  6. runner discovery with `--list` and its fixture test;
  7. `run_id.py` and its table test;
  8. Python CLI migration, part 1;
  9. Python CLI migration, part 2;
  10. shell CLIs and the no-own-parser lint test;
  11. promoted lessons;
  12. the 2A PROGRESS freeze test.

  The 2A PROGRESS refresh itself is an orchestrator commit, not a worker task.
- **F001:**
  1. T-001, the stats tool;
  2. T-002, ledger planning rows and the receipt and ledger subagent fields;
  3. effort-by-role launch checks;
  4. the batch command and the before batch;
  5. goal-style prompts with token budgets;
  6. compare and the review calibration replay.
- **F002:** parser, real captures, snapshot via drive-cli, forecast/ledger/training set, the dispatch gate with the native map, and pause and probe.
- **F004:** event schema and add, render and golden, generated status and the GOAL status check, brief, and verify and spawn wiring with the archive.
- **F003:** state machine with progress events, the check/review/fix stages, seat and tool repair, terminal states and resume, the quota hook with the no-Claude-worker rule, and Front Desk wiring.
- **F007:** 3 guard tasks (admission and locks, worktree launcher, merge) plus 2 lane demo tasks.

## Reading the totals

- Over a 4–5 week mission, anthropic needs about 24–30 pp per week and every other pool under 17. The 2% floor and expiring-quota-first ordering should rarely stop the loop.
- The tightest pools:
  - anthropic: shared with the Front Desk, and carries F000's guard reviews. The planner falls back to Argon or Sol.
  - agy-argon: weekly window, steep cost per run.
- Planning tokens: about 8 runs (F000 and early F001) happen before the F001 prompt change, at about the Opus baseline. That gives roughly 8 × 1.82M + 35 × 1.0M ≈ 50M, against 43 × 1.23M ≈ 53M at the 2A median throughout.
- Not included: the F009 benchmark pilot. v1 with 10 tasks × 2 runs × 4 economy lanes, plus a Sol-high baseline on 10 tasks × 2 runs, is about 100 runs. The pilot would cost:
  - openai: about 76 pp, 60 of it the Sol baseline;
  - google: 20;
  - cursor: 10;
  - anthropic: 8.

  Recommendation: run the pilot only into quota that the meter shows expiring within 24 h, and cut the Sol baseline to 5 tasks if openai is tight.
- Risks on the estimate:
  - Plan-defect retries. If the verify-failed rate stays at the 2A start rate (6 of 17), W grows by about 30%.
  - F000 receipt privacy (GOAL risk 9). If any 2A receipt fails the privacy check, F000 needs one or two more tasks.
