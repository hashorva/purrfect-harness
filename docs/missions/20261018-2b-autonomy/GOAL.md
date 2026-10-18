---
status: draft
owner: Zamir
orchestrator: opus
created: 2026-10-18
intake: owner spec 2026-10-18 (dark factory, items a-h), docs/proposals/20261014-phase-2.md (sections 6-10, 13), docs/proposals/20261016-structured-progress.md, docs/proposals/20261015-parallel-dispatch.md (section 5), 2A DAY 6 REPORT
---

# Goal

## Mission (2–4 sentences, outcome not tasks)

Mission 2B "The Dark Factory": a prompt goes in; the planner splits it into tasks small enough for economy seats; workers build with their full abilities; deterministic checks judge every piece; failures are re-prompted automatically, and broken tools are repaired first; it stops only at the goal or a real blocker. No human in the loop between gates.

## Why now / forcing function

2A (v3.1.0) made every run provable and the fleet native-only, but a human still drives each step. There is no quota meter: the 2A pause notes are error text and are not trusted. The median planning run costs 1.23M tokens (1.82M on Claude Opus), and PROGRESS.md is still written by hand. 2A is done, so this folder can go `approved` → `in-progress` after Gate 0 without a second active mission.

## In scope

Features in `features.json`, in the owner's order (item → id):

- a → F001 Delegation and full ability (finish and measure 2A item B; planning-run median under 1M tokens with no drop in review quality)
- b → F002 Quota meter (real usage screens, 2% floor, expiring quota first, native-only, pauses end at the vendor-shown reset, training set)
- c → F003 Loop driver (dispatch → checks → review → fix → re-review; repair a broken seat or tool first)
- d → F004 Structured progress (progress.jsonl, progress.py, generated PROGRESS.md)
- e → F005 Worker inner loop (ruff, type checker, shellcheck; resumed repair for lint/type; fresh run for logic)
- f → F006 Task-size signal (more than 2 review rounds → back to the planner to split)
- g → F007 Parallel lanes, minimum slice (two disjoint tasks, two providers, one serial merge)
- h → F008 static board, F009 held-out benchmark, F010 Front Desk skills for every CLI, F011 prediction model, F012 OS-level Bash sandbox for Claude bypassPermissions workers

Item h is five features, so each one is accepted on its own evidence (Gate 0 decision 1).

## Explicitly OUT of scope (workers: do not touch)

- The 2A mission directory (read-only input: `routing-data.jsonl` is the token baseline).
- Proposal items not in the owner list: anti-gaming checks, lessons intake, the STE rewrite (X-003), the overnight non-Claude-chair smoke.
- Fast modes, usage credits, API billing, X-FAST. A `grok` provider (Grok stays on `cursor-agent`).
- Cross-vendor seats: no vendor's door resolves another vendor's family (2A T-100). No agy Opus/Sonnet/GPT-OSS seat.
- More than two lanes, the same provider twice, a Codex lane, parallel planner runs, parallel acceptance, automatic merge resolution.
- Live `claude`, `codex`, `cursor-agent`, `agy`, or `drive-cli.sh` against a real CLI inside `tests/run-tests.sh` or CI. Live checks are local-only task verification commands.
- Letting the prediction model dispatch or override the 2% floor.

## Constraints

- Hard rules: see AGENTS.md — all apply.
- Native-only: every model runs only on its own vendor's quota. claude: Opus, Sonnet, Haiku. codex: Sol, Terra, Luna. agy: Argon, Flash. cursor: Composer, Grok. Repair and escalation stay inside the vendor: haiku → sonnet → opus; luna → terra → sol; composer → grok; flash → argon.
- Effort by role: brain (planner) high; reviewers medium; economy workers medium; premium workers medium, and only on escalation or a planner-justified guard task.
- Review rule: the reviewer is a different vendor than the worker (fleet-proposal.md). Guard and safety code is reviewed by Claude Opus, so guard tasks never go to a Claude worker.
- Quota rule (replaces the 2A 80%/70% pool stop; Gate 0 decision 2): dispatch only if percent left minus the batch forecast is greater than 2 on every window the vendor shows for that pool. Unknown is refused. Among allowed pools, the soonest reset wins.
- Pauses end at the reset time on the vendor usage screen. Never trust a reset time parsed from error text. An unparsable screen is `unknown`, and the meter probes again after 30 minutes.
- Every number carries a source flag: `observed`, `estimated`, or `unknown`. Never guess.
- Runtime Python is the standard library. Dev tools (`ruff`, the type checker) are installed only with `uv tool install`.
- Real CLI behaviour first: before a task relies on a CLI feature (a flag, a usage screen, a stream event), a recorded real `--help` output or real stream/screen capture is committed under `evidence/` and cited by the task.
- Provider contract: any adapter argv change bumps the provider contract in the same task, and old receipts still validate.
- Verification bullets are one Markdown code span whose text is a JSON argv of non-empty strings, with no backtick inside the span. Tests are named by file and `Class.method`, as `["env","PYTHONDONTWRITEBYTECODE=1","python3","tests/<file>.py","<Class>.<method>"]`, never `python -m unittest <path>`. The full file, `shellcheck scripts/*.sh tests/*.sh`, `bash tests/run-tests.sh`, clean tree and no `__pycache__` are their own bullets. Allow-list bullets are backtick-quoted paths only.
- Frozen oracle: verification commands are immutable per run (frozen at the task commit). A bad oracle needs a new task or a retry with a real change, never an edit of the frozen commands. The verifier checks a run against that run's own commit.
- Rule 6: before a task is committed, the planner or Front Desk runs its oracle in a scratch clone: it must fail on the base and pass after the reference patch (kept outside the repo tree).
- Planner runs write at most 3 task files, each at most 150 changed lines. Planner output is plain task files in four-backtick fenced blocks or `=== FILE: <path> ===` blocks.
- Flaky is failing: a test that passes only on rerun is a failure. Never skip, retry-wrap, or loosen it; make it deterministic.
- CI (ubuntu-latest with Python 3.12, and macos-latest; tmux, jq and jsonschema installed) must be green on every gate commit.
- Workers never edit `features.json`, `fleet.json`, or `PROGRESS.md`. Until F004 is accepted, the loop writes only `loop-state.json`; after it, `scripts/progress.py` is the only PROGRESS writer.

## Architect instructions (read before you change features.json)

- Keep ids F001–F012. Do not renumber. You may tighten steps. Do not drop the 2% floor, the unknown-not-guessed rule, native-only, or the in-vendor ladder.
- T-001 is the first slice of F001: the stdlib measurement tool and its fixture tests (new files only). T-002 wires it into `tests/run-tests.sh` and adds ledger-sourced planning rows.
- Every feature stays `passes: false` and `bootstrap: false`.
- A step a script cannot decide is a defect. Rewrite it until a command can decide it.

## Fleet

See `fleet-proposal.md` (bindings JSON, policy JSON, review pairing). Gate 0 runs `bash scripts/fleet-doctor.sh` and `bash scripts/fleet-inventory.sh` first, then `freeze-v2` with the approved bindings. Dispatch reads only `fleet.json`.

Tier chosen at GATE 0: mixed (economy first), proposed.
Orchestrator (brain): claude / Opus, effort high; fallbacks `brain_argon` (agy / Argon high) and `brain_codex` (codex / Sol high), each on its own vendor's quota, proposed.

## Budgets (confirmed at Gate 0)

- Per spawn: 40 min wall time.
- Per 24 h: at most 24 worker runs, 24 review runs, 8 planner runs. The loop stops at the cap, not at a guess.
- Per pool: the 2% floor (above). Never credits, never fast modes.
- Planning tokens: target median under 1,000,000 total (input + output + cache read) per planning run, measured by `scripts/planning_stats.py`. A single planning run over 3,000,000 is listed in the next gate report.
- Per task: at most 2 worker attempts per rung, and at most 2 review rounds before the F006 split signal.
- Mission estimate: about 45 tasks, 69 worker runs, 59 review runs, 36 planner/gate runs (estimates.md).

## Risks

1. Usage screens change format or are boxed TUI panels: drive-cli stalls (exit 4) on boxed menus and alt-screen clears (2A residual). Mitigation: F002 starts with real captures; an unparsable screen is `unknown`, and the factory waits safely rather than guessing.
2. Claude Pro is shared by the planner, the Opus reviewer, the Front Desk and claude.ai chat. Mitigation: the meter sees it; planner fallbacks run on Argon or Sol quota, never on another vendor's door.
3. Unattended `bypassPermissions` Claude workers before F012: Bash is a net, not a wall (evidence/claude-unlock-residual-risk.md). Mitigation: Gate 0 decision 5 (F012 first), or no Claude worker on unattended nights until F012 is accepted.
4. Plan defects dominate failures (2A: 5 of 6 early failures were plan text). Mitigation: rule 6 per task, the size cap, and the F006 split signal.
5. Loop runaway or silent spending. Mitigation: per-24h caps, a forecast before every batch, stops at ladder exhaustion, and gate-wait as a terminal state.
6. Hot files (`tests/run-tests.sh`, `harness-manifest.json`) block lane pairs. Mitigation: F007 admission refuses overlap; lane demo tasks are chosen for disjoint files.
7. The F001 1M target may not be met. Then F001 stays `passes: false` and the gate report shows the measured median. Later features still proceed (they do not depend on the target).
8. F011 needs 300 kept forecasts; it may not be reachable within this mission. Gate 5 then records an owner amendment, not a relaxed step.

## Human gates

- GATE 0: owner approval of this package (GOAL, features.json, fleet-proposal.md, estimates.md, T-001), a fresh fleet inventory and `freeze-v2`, and the brain receipt (`verify-mission.sh`). Decisions:
  1. Item h as F008–F012.
  2. The 2% floor replaces the 2A 80%/70% pool stop.
  3. Type checker `ty` via `uv tool install ty` (fallback `mypy`), confirmed by a real `--help` capture.
  4. Prediction threshold: 300 kept batch forecasts with before and after readings.
  5. Order: F012 (sandbox) before F003, or keep the owner order (recommended: before).
  6. Budgets above.
  7. Mid seats `claude.mid` (Sonnet) and `codex.mid` (Terra) frozen now, dispatchable after F005.
  8. T-001 creates new files only; T-002 wires the test (exception to the wiring lesson).
- GATE 1: after F001 and F002. The factory can see its own cost.
- GATE 2: after F003 and F004. The factory runs its loop and records it.
- GATE 3: after F005 and F006. The factory repairs and re-splits its own work.
- GATE 4: after F007. Two lanes run in parallel.
- GATE 5: after F008–F012.

When a human gate is reached: run `bash scripts/verify-mission.sh` (must exit 0), confirm CI is green on the gate commit, set `status: awaiting-gate`, get the human verdict, and record it (a **Human — GATE n** entry before F004; a `gate` event with `by: human` after F004). Then set `status: done` or `in-progress`. Chat approval alone is not the record — receipts are.

## Source of truth

The binary checklist lives in `features.json` in this mission folder. This file is narrative only — if they disagree, features.json wins.

## Status lifecycle

`draft` → `approved` (GATE 0) → `in-progress` → `awaiting-gate` (optional) → `done`
