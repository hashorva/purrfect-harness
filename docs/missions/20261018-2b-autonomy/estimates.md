# 2B estimates (ESTIMATED — every number here has source `estimated`)

These numbers plan Gate 0. They are not readings. The F002 meter replaces the per-run quota constants with observed before/after deltas after the first measured batches, and the gate reports compare the two.

## Inputs

- 2A outcomes (`routing-data.jsonl`, 159 run rows; the owner's brief said 158 runs and 100 done): done 112 (70%), verify-passed-review-failed 16 (10%), verify-failed 17 (11%), scope-failed 6 (4%), other 8 (5%: failed 4, baseline-stopped 2, no-change 1, seat-limit 1).
- Worker runs per task: 1 / 0.70 ≈ 1.43, rounded up to **1.45**.
- Review runs per task: about 80% of runs reach review, plus re-review after a fix: **1.2**.
- Planner runs: at most 3 tasks per run, plus oracle repairs and splits: **ceil(1.3 × ceil(tasks / 3))**; plus one brain run per gate (5).
- 2A worker mix (done runs): cursor 41%, codex 35%, claude 18%, agy 6%. Escalation to a premium or mid seat: about 10% of runs.
- Review mix under the different-vendor rule: Sol 30%, Grok 25%, Argon 20%, Opus 25%. Planner: Opus 80%, Argon 10%, Sol 10%.
- Planning tokens: 2A baseline median 1,233,224 (Opus 1,816,741); 2B target under 1,000,000.

## Per-run quota cost (percentage points of the pool's weekly window, the unit the meter reports as a drop in percent left)

| Pool | Run | pp of week | Basis |
| --- | --- | --- | --- |
| anthropic | Opus planning / gate | 2.5 | no limit hit on 2026-10-18 with about 10 Opus planning runs, 4 reviews and the Front Desk; assumed |
| anthropic | Opus review | 1.0 | assumed (about 0.4 of a planning run's tokens) |
| anthropic | Haiku worker / Sonnet-Opus escalation | 0.4 / 1.5 | assumed |
| openai | Luna worker / Terra-Sol escalation | 0.8 / 1.5 | 38 codex.economy runs over 5 days with no limit: upper bound 2.6; a third of that assumed |
| openai | Sol review / Sol planning | 1.2 / 3.0 | assumed |
| cursor | Composer worker / Grok review or escalation | 0.5 / 0.8–1.0 | 46 cursor.economy runs with no limit: upper bound 2.2; assumed |
| agy-argon | Argon review / Argon planning | 2.5 / 6.0 | two weekly 429s (resets 155 h and 161 h) after about 15–20 Argon planning runs: 5–7 each |
| google | Flash worker | 1.0 | 5 runs only; assumed |

The Front Desk's own Claude use (Sonnet) and claude.ai chat come out of the anthropic pool too, and are not counted below.

## Per feature

W = worker runs including expected retries (of W: about 70% done, 10% review-failed, 11% verify-failed, 4% scope-failed, 5% other). R = review runs. P = planner runs. Quota columns are pp of one week's window for that pool, over the whole feature.

| Feature | Tasks | W | R | P | anthropic | openai | cursor | agy-argon | google |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F001 delegation | 4 | 6 | 5 | 3 | 7.8 | 4.5 | 2.4 | 4.9 | 0.4 |
| F002 quota meter | 6 | 9 | 8 | 3 | 8.6 | 6.4 | 3.7 | 6.3 | 0.5 |
| F003 loop driver | 6 | 9 | 8 | 3 | 8.6 | 6.4 | 3.7 | 6.3 | 0.5 |
| F004 structured progress | 4 | 6 | 5 | 3 | 7.8 | 4.5 | 2.4 | 4.9 | 0.4 |
| F005 worker inner loop | 4 | 6 | 5 | 3 | 7.8 | 4.5 | 2.4 | 4.9 | 0.4 |
| F006 task-size signal | 2 | 3 | 3 | 2 | 4.9 | 2.4 | 1.2 | 2.8 | 0.2 |
| F007 parallel lanes | 5 | 8 | 6 | 3 | 8.2 | 5.5 | 3.1 | 5.6 | 0.5 |
| F008 board | 3 | 5 | 4 | 2 | 5.3 | 3.3 | 1.8 | 3.5 | 0.3 |
| F009 benchmark (build) | 4 | 6 | 5 | 3 | 7.8 | 4.5 | 2.4 | 4.9 | 0.4 |
| F010 Front Desk skills | 2 | 3 | 3 | 2 | 4.9 | 2.4 | 1.2 | 2.8 | 0.2 |
| F011 prediction | 2 | 3 | 3 | 2 | 4.9 | 2.4 | 1.2 | 2.8 | 0.2 |
| F012 sandbox | 3 | 5 | 4 | 2 | 5.3 | 3.3 | 1.8 | 3.5 | 0.3 |
| Gate runs (G1–G5) | – | – | – | 5 | 10.0 | 1.3 | – | 3.3 | – |
| **Total** | **45** | **69** | **59** | **36** | **92** | **51** | **27** | **57** | **4** |

Method: per task, workers plus reviews cost anthropic 0.44, openai 0.94, cursor 0.61, agy-argon 0.72, google 0.09 pp; per planner run, anthropic 2.0, openai 0.25, agy-argon 0.67 pp (mix-weighted). Feature cost = tasks × per-task + P × per-planner.

Task split assumed: F001 = T-001 stats tool, T-002 wiring and ledger planning rows, T-003 effort-by-role launch checks plus goal-style prompts, T-004 review calibration replay. F002 = parser, real captures, snapshot via drive-cli, forecast/ledger/training set, dispatch gate with native map, pause and probe. F003 = state machine, check/review/fix stages, seat/tool repair, terminal states and resume, quota hook, Front Desk wiring. F007 = 3 guard tasks (admission and locks, worktree launcher, merge) plus 2 lane demo tasks.

## Reading the totals

- Over a 3–4 week mission, no pool needs more than about 30 pp per week, so the 2% floor and expiring-quota-first ordering should rarely stop the loop. The tightest pools are anthropic (shared with the Front Desk; the planner falls back to Argon or Sol) and agy-argon (weekly, steep per run).
- Planning tokens: 36 runs × 1.0M (target) ≈ 36M, against 36 × 1.23M ≈ 44M at the 2A median.
- Not included: the F009 benchmark pilot. v1 with 10 tasks × 2 runs × 4 economy lanes plus a Sol-high baseline on 10 tasks × 2 runs ≈ 100 runs: openai about 76 pp (60 of it the Sol baseline), google 20, cursor 10, anthropic 8. Recommendation: run the pilot only into quota that the meter shows expiring within 24 h, and cut the Sol baseline to 5 tasks if openai is tight.
- Risk on the estimate: plan-defect retries. If the verify-failed rate stays at the 2A start rate (6 of 17), W grows by about 30%.
