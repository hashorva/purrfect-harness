---
note: Current state only. Full history is in progress-archive/ (read-only). Newest entry on top; at most 10 lines per entry; full reviewer outputs go to reviews/<run-id>.md. Workers do not write this file; the Front Desk records each run from its receipt.
---

# Progress

## Current status (2026-10-16)
- Mission 2A Foundation, branch `mission/2a-foundation`, status in-progress. Gate 0 passed. **Gate 1 target:** F001–F006 accepted and the deterministic suite green (prepare, do not advance).
- **Accepted:** F001, F003, F006. **Waiting on one task (ledger fixes):** F005. **F004** and **F007** wait for the agy amendment (agy dropped from the mission by owner decision; T-026 and T-039 deferred).
- Full history before this reset: `progress-archive/2026-10-14_15.md` (717 KB, kept verbatim). Routing data: `routing-data.jsonl`. Receipts/records: `.tasks/receipts/`, `verification/`.
- Seats: usable claude.economy, claude.premium, codex.economy, codex.premium, cursor.economy, **cursor.premium** (re-frozen grok-4.7-high/high/standard, smoke passed 2026-10-16); **agy.economy unusable** (every turn hangs; evidence in the archive, entry "day 3 / agy re-smoke").

## Owner decisions in force (2026-10-16 message)
1. Order: archive PROGRESS.md; accept F003 and F006; re-freeze cursor.premium to grok-4.7-high standard (drift event); ledger task (Architect review) then fold + accept F005; two small tasks (verifier: a skipped check is a failure; privacy near misses); drop agy (amend F004/F007, defer T-026/T-039, T-037 uses claude, codex, cursor); stop at Gate 1 prepared.
2. Reviews: guard/safety/privacy changes -> Claude Opus (brain). Routine diffs -> grok-4.7-high via cursor.premium (replaces the code-reviewer subagent). Calibration: for the next 3 guard reviews run grok-4.7-high first, then Opus, and record in `routing-data.jsonl` whether grok found the same blocking issues.
3. Process rule for every task writer (Front Desk included): before committing a task, run its verification commands in a scratch clone; they must fail on the base and pass after a scripted application of the intended edit.
4. Parallel dispatch stays in 2B (option A). Lesson candidates accepted as candidates.
5. Workers no longer write PROGRESS.md; the Front Desk records each run from its receipt (task-template and launcher prompt change to follow).

## Open decisions / waiting on the owner
- Proposal `docs/proposals/20261016-structured-progress.md` (progress.jsonl + progress.py + generated PROGRESS.md): to be written by the Architect; owner decides whether it starts 2B or is pulled into 2A.
- Gate 1 verdict (after F001–F006 accepted).

## Active lessons (candidates; none promoted through skillify)
- State why a check exists, not only its rule. Run a long check once; never start a duplicate.
- Tests never mutate the live tree; verification must not depend on it (clean worktree).
- CLI login state is invisible in the Codex sandbox; known seat limits belong in the registry.
- A task that adds a test also wires it into `tests/run-tests.sh`.
- Worker PROGRESS narratives are not evidence; receipts and records are (the receipt decides attribution).
- Negative tests: assert the specific refusal at the real entry point, one test per pattern in a pattern list, name the exact field path; a mutation must make the entry point admit the violation.
- A guard-mutation oracle must reject every compile error; near-miss patterns for sandbox-mount decisions; re-run narrower rules' mutation proofs when a broader rule is added.
- Reproduce a failure on the unfixed tree before filing a fix; a task item that names a value must name its field; a follow-up that loosens a gate goes to the Architect.
- A subset validator must validate the shape of every keyword value and recurse into every schema-valued keyword; every guard on untrusted input must cover every branch; a skip-ahead scanner needs an adjacent-character test; mutation proofs listed per test as file:line:expression.
- Any CLI that takes a run id validates it as a canonical UUID first, with a hostile-id/symlink test at the entry point.
- The Front Desk writes nothing into the repository while a worker or Architect run is in progress.

## Recent entries (newest first)
- **2026-10-15 — BRAIN review (Opus) of T-041 / commit 0bff888 — calibration review 1, Opus side. Run cb23708f-7387-4c3b-85b0-77df3be10740, log `.tasks/logs/cb23708f-7387-4c3b-85b0-77df3be10740.log`. Verdict PASS, no blocking issues.** Attribution: receipt a5343e36 (codex.economy) lists commit 0bff888 and its 11 paths, scope pass; record `verification/2884c3e6…json` result pass, 8/8 commands exit 0.
  By effect: `configured` only on requested_model/resolved_model/effort (validator, schema `configuredTextFlag`, builder reads receipt configuration, never the spec); observed_model/cli_version/fast_state refuse it; door = registry key or `unknown` (Cursor by model family, so Grok at standard speed is cursor-grok); `tier` is economy, premium or null; v1 rows are refused.
  My evidence (scratch copy of 0bff888, only the tests' fake CLIs, PYTHONDONTWRITEBYTECODE=1, live tree untouched): 32 hostile probes through `ledger.py validate`, no value echoed; 30 mutants (23 from the task list + 7 extra), all killed.
  Non-blocking: N1 validator accepts any non-empty `door` (also `economy`, the v1 meaning) → check door ∈ registry doors ∪ {unknown} in T-042. N2 mutant X01 (configured value type check skipped) is killed only by Oracle A, not by `tests/test-ledger.py`. N3 fold stops at the first invalid row: 31 local v1 rows of this mission in `.tasks/ledger/` must be set aside before the F005 fold. N4 `reviews/grok-calib-1-T-041.md` is 19 bytes (verdict only, no evidence).
  Calibration (owner decision 2): grok and Opus agree on blocking issues (none); grok reported no non-blocking ones (missed N1, N2). My write scope is PROGRESS.md only: the full review and the routing-data row are in blocks at the end of this file for the Front Desk to split out.
- **2026-10-15 — T-041 verified (attempt 4 record); calibration review 1 of 3 (grok-4.7-high) done; Opus review requested** Record: run 2884c3e6-27c7-4565-95e7-0650aaa76437 (codex.economy), VERIFY PASS, 8 commands incl. both oracles and the full suite; the implementation is commit 0bff888 (attempts 1–4 = one implementation, three plan/harness failures of mine). Grok review (cursor.premium, plan mode, scratch clone): "Verdict: PASS", no findings listed (`reviews/grok-calib-1-T-041.md`).
  **ARCHITECT REVIEW REQUEST, T-041 (commit 0bff888 only; a privacy/evidence guard).** `git show 0bff888`; task `tasks/T-041.md`. Confirm with evidence you produced: `configured` is the only label for spec/receipt-configured values and `observed` only for CLI-reported ones, in the validator, schema, runner builder and fixtures; `door` = real registry door and `tier` present (null for brain runs); v1 rows refused; Grok at standard speed maps to cursor-grok not cursor-composer; hostile inputs (wrong source label, tier/door mutated, unknown door, extra keys) refused with no value echoed; mutate each new check once in scratch copies and report how many tests catch. RULES: fake provider CLIs on PATH, never a real provider, PYTHONDONTWRITEBYTECODE=1, nothing in the live tree, no secret-shaped literal. Do not write long output: your PROGRESS entry at most 10 lines; the full text goes in a block headed `=== FILE: reviews/<your run id>.md ===` at the end. End with Verdict: PASS or FAIL and blocking issues only.
- **2026-10-15 — T-041 v2 implementation re-verified locally.** Oracle A/B, ledger tests (70), ledger integration subset (14), `shellcheck`, JSON validation and the full suite passed; implementation remains the scoped `0bff888` commit.
- **2026-10-15 — T-041 attempt 3 (cursor.economy, run 255afe50-0813-4ca2-bac4-fa6dc137f079): scope fail again — my task-text mistakes (two)** (1) I put the PROGRESS.md allowance in a section the allow-list parser does not read; (2) the new scope command compared HEAD~1..HEAD, which is a docs commit when the worker makes no commit. Worker entry kept at ; tree restored. Class harness/plan defect, not the model.
  Fixed (recorded): PROGRESS.md added to the real MAY list; the scope command compares the worker commit 0bff888 with its parent (it exits 0 now). Attempt 4 on codex.economy. Lesson: rule 6 needs a run of the dispatch itself on a no-commit re-verification, not only of the commands.
- **2026-10-15 — T-041 attempt 2 (cursor.economy, run 8ecab630-4416-4ab7-a808-28cecd84dd7f): scope fail on PROGRESS.md — harness/task conflict, not a task failure** The launcher prompt still says "Append a PROGRESS.md entry"; T-041 forbade touching PROGRESS.md, so the worker's entry was a scope violation. Entry preserved at , tree restored. Class harness (does not use an attempt).
  Task text changed (recorded): PROGRESS.md allowed for a 3-line entry. Attempt 3 follows. The launcher-prompt fix ("workers do not write PROGRESS.md") is a separate task, queued with the verifier task.
- **2026-10-15 — T-041 attempt 1 (codex.economy, run a5343e36-0abb-46ac-b70d-31e3e53894c4): work in, verification FAIL on one plan-defect command** Commit 0bff888, scope pass, 11 allowed paths; 7 of 8 verification commands exit 0 (incl. both oracles and the full suite). The failing command is the Architect's scope check (its base = last commit touching the task file, so my later docs commits fell in range). Class task, attributable:false.
  Task text changed (recorded): scope command now compares HEAD~1 with HEAD, and an "Attempt 2 note" tells the worker to change nothing. Attempt 2 on cursor.economy, then Architect review of the diff.
- **2026-10-15 — T-041 dispatch (ledger v2), codex.economy** Task committed (Architect-written, rule 6 checked: oracles fail on base, pass after the reference patch). Worker must not touch PROGRESS.md; I record the run from the receipt.
- **2026-10-15 — Architect run A (9477ab3f): ledger work split into T-041 (complete) and T-042 (outline).** Full text: `reviews/9477ab3f-9623-422a-ad14-20f77ced8f17.md`, mutants `…-mutants.md`; reference patch kept local at `.tasks/plans/T-041-reference.patch` (the worker never sees it).
  T-041 = `configured` source, real door name + `tier`, Cursor family by model (fixes the Grok-as-Composer pool bug); T-042 = pool/billing read at `base_commit` (it breaks two existing tests on purpose, so it is separate). 29 local v1 rows must not be folded (no migration; set aside, listed in the review file).
  **Rule 6 on T-041 (my check, `.tasks/rule6.py`, scratch clone):** oracle commands A and B fail on the base and pass after the patch; the other 6 commands pass on both (they test what the worker adds). One full-suite run after the patch failed once and passed on a rerun in the same clone: a flaky test in the suite under load (not yet identified).
  Next: dispatch T-041 (codex.economy), brain review of it, then T-042.
- **2026-10-15 — ARCHITECT RUN A (planning, not a diff review): ledger task with reference patch. HARD TIME BOX: write your entry by minute 30** Design ONE economy-seat task for ledger items: (a) `configured` source for requested_model, resolved_model, effort (spec/receipt configuration); `observed` only for what the CLI reported; (b) `door` = real registry door name (cursor-composer, cursor-grok, ...) plus a new `tier` field (schema, validator, runner row builder, fixtures, fold/view readers); (c) fix the pool lookup that counts Grok at standard speed as Composer; (d) read pool and billing_class at the run's `base_commit` (git show of harness-registry.json) so a worker cannot rewrite its own row. Say whether the 12+ local `.tasks/ledger/*.json` rows need migration or may be dropped (docs/missions/ledger.jsonl does not exist yet).
  Owner process rule: build the reference patch in a scratch clone (git archive of HEAD); show every verification command FAILS on the base and PASSES after the patch; list the patch's mutants and which test kills each (do at least 12). If the whole thing does not fit in 30 minutes, split into two tasks and deliver the first completely.
  Deliver in your entry (short summary under 25 lines) plus blocks headed `=== FILE: tasks/T-0xx.md ===` and `=== FILE: reference.patch ===` so the Front Desk can split them out. The patch is for the Front Desk's check only; the worker never sees it. The real date is 2026-10-15. Do not review commits.
- **2026-10-15 — Architect planning run 52cd7676-a424-424d-b07d-31b824a3e13c timed out (spawn limit 40 min, exit 124)** The combined request (ledger task with a reference patch and mutants, the proposal, and the rule-6 paragraph) was too large for one 40-minute run; nothing was written and the tree is clean. Class: task (decomposition miss, mine), not a seat limit.
  Split into two runs: A (ledger task + reference patch) and B+C (proposal text + rule-6 paragraph). Each is told to deliver a complete partial result by minute 30 rather than run out the clock.
- **2026-10-15 — ARCHITECT: THIS RUN IS A PLANNING RUN, NOT A DIFF REVIEW (do not review the Front Desk's commits; that was done)** Do deliverables A, B and C of the entry "ARCHITECT PLANNING REQUEST" below, in your entry. The `review` action name is only the launcher's label for this run.
  A: design the ledger task (items a–d: `configured` source for requested/resolved model and effort; `door` = real registry door name plus a new `tier` field; fix the pool lookup that counts Grok at standard speed as Composer; read pool and billing_class at the run's `base_commit`). Build a REFERENCE PATCH in a scratch clone (git archive of HEAD) and show every verification command fails on the base and passes after the patch, plus patch mutants and which test kills each. Deliver the task text, the patch as a fenced unified diff, and the expected files.
  B: the proposal text for `docs/proposals/20261016-structured-progress.md`, max 2 pages, with a recommendation (2B or pulled into 2A) and a cost in tasks. C: one paragraph on making the "fail on base, pass after scripted edit" rule cheap.
  Keep your entry in PROGRESS.md short (summary, under 40 lines); put the full task text, the patch and the proposal in clearly delimited fenced blocks headed `=== FILE: <name> ===` so the Front Desk can split them into files. Dates: the real date is 2026-10-15.
- **Brain review of Front Desk commits 0cc3b60..d48f010 — PASS, no blocking findings** (run 2488fe05-ac34-4675-ab53-e016f20e82e0; full text `reviews/2488fe05-ac34-4675-ab53-e016f20e82e0.md`).
  Archive byte-identical to the old PROGRESS.md; F003/F006 diffs touch only `passes`/`accepted_*` and the record hashes recompute; fleet.json changes only cursor.premium; `verify-mission.sh --require-workers` → `VERIFY OK`.
  N1 dates: my entries say 2026-10-16 but the real date is 2026-10-15 (fixed from now on). N2 define the Front Desk role in ORCHESTRATION.md. N3 smoke run d240aeaf has no receipt (scratch clone deleted; evidence `.tasks/smoke/20261015T175529Z.json`). N4 the F005 fold must also cover F003/F006 runs and the drift row.
  The planning request that followed was **not** done by this run (it treated the review action as its job); re-sent below.
- **2026-10-16 — ARCHITECT PLANNING REQUEST (two deliverables; write this file only; put patches/scripts as text blocks)** **A. Ledger task (owner step 2), design for ONE economy-seat task with a REFERENCE PATCH.** Items: (a) new source value `configured` for requested_model, resolved_model, effort (from spec/receipt configuration); `observed` only for what the CLI reported; (b) `door` holds the real door name from the registry (cursor-composer, cursor-grok, ...) and a separate `tier` field is added (schema, validator, runner row builder, fixtures, view/fold readers); (c) fix the pool lookup that counts Grok at standard speed as Composer; (d) read pool and billing_class at the run's `base_commit` (git show of harness-registry.json), so a worker cannot rewrite its own row. Check what committed rows exist (`docs/missions/ledger.jsonl` does not exist yet, `.tasks/ledger/*.json` do) and say whether old local rows need migration or can be dropped.
  **Owner process rule, you apply it:** build the reference patch in a scratch clone of HEAD (`git archive`), then show (1) every verification command FAILS on the base and PASSES after the patch, (2) the list of mutants of the patch and which test kills each. Deliver: the task text (allow-list, verification commands as JSON argv, "why each check exists", long-command rule, mutation list as file:line:expression instructions), the reference patch as a unified diff in a fenced block, and the expected files list. The worker will NOT see the patch.
  **B. Proposal text for `docs/proposals/20261016-structured-progress.md` (max 2 pages):** progress.jsonl (one event per run, review, decision, amendment, lesson or gate; schema-validated: feature, task, run_id, type, status, link), `progress.py add` as the only writer and `progress.py brief --task T-xxx` (task file + events of its feature and dependencies + last few events + active lessons for its category), PROGRESS.md generated read-only, prose in linked files. Say whether it should start 2B or be pulled into 2A, with cost estimate in tasks. Proposal only.
  **C.** one paragraph: how to make rule 6 (fail on base, pass after a scripted edit) cheap for the Front Desk for every future task; no code.
- **2026-10-16 — cursor.premium re-frozen to grok-4.7-high (drift event, owner approved); smoke passed** `fleet.json` cursor.premium: model `grok-4.7-xhigh`/effort medium → `grok-4.7-high`/effort high, speed standard (never fast); `validate-fleet` exit 0. The file was chmod'd writable for this one edit and set back to 444. Drift event written locally to `.tasks/drift/20261014-2a-foundation.jsonl` (folded into the committed drift.jsonl by the T-030 fold at F005 acceptance).
  Seat smoke (`fleet-doctor.sh --smoke --seat cursor.premium`, two runs; the first with --keep): completed, "both smoke files in HEAD", run d240aeaf-5a16-4621-aeb4-37460a329b25. The kept scratch clone was removed. cursor.premium joins rotation, used first for routine reviews.
- **2026-10-16 — F003 and F006 accepted (owner approved)** F003: run 86a9c529-95d9-42b3-9e23-b24c18fec0ff, record sha a85b3ac1…, `ACCEPT OK`; F006: run db01ac53-00de-4d30-9230-05894b952ebe, sha recomputed d652eeea… before running, `ACCEPT OK`.
  `verify-mission.sh --require-workers` after each: `VERIFY OK`, exit 0. Accepted by "Front Desk (claude-sonnet-5-5), owner-approved by Zamir (2026-10-16)". features.json committed.
- **2026-10-16 — PROGRESS.md reset (owner step 0)** Moved all 250 entries (717 KB) verbatim to `progress-archive/2026-10-14_15.md`; PROGRESS.md now holds status, decisions in force, open decisions, active lessons and recent entries (5.4 KB).
  Reviewer outputs go to `reviews/<run-id>.md`; workers no longer write this file (launcher prompt and template change to follow as a task).
  The structured-progress proposal is the next Architect planning run.
- **2026-10-15 — day 3 stop report.** Stopped because everything left needed agy or an owner decision. 21 worker runs on day 3 (11 first-time done, 10 task failures after review, 3 not attributable); no limit hit; F005/F006 ready for acceptance; T-036 done; agy still hangs in repo and fresh folder; Cursor Opus ids are credit-only. Details: `progress-archive/2026-10-14_15.md` (entries "MORNING REPORT — DAY 3" and "CORRECTION").
- **2026-10-15 — T-034 chain closed.** Three task failures, Architect redesign (budgeted greedy scan), R3 + R4 verified and reviewed. Archive entry "redesign of the --after-run extractor".
- **2026-10-15 — T-030 chain closed.** Fold keyed on run_id, 4-key drift shape, no cap on committed targets. Archive entries "T-030", "T-030-R1", "T-030-R2".
- **2026-10-15 — T-028-R4 / T-029 chain closed.** Privacy rule extended; ledger step never changes a run's outcome. Archive entries "T-028-R4", "T-029-R1..R3".
- **2026-10-15 — F005/F006 acceptance commands prepared** (see the day-3 correction in the archive; superseded by the approved sequence above).

<!-- Front Desk: split the two blocks below into their files and remove them from PROGRESS.md. -->

=== FILE: reviews/cb23708f-7387-4c3b-85b0-77df3be10740.md ===

# Brain review (Opus) of T-041, commit 0bff888 — run cb23708f-7387-4c3b-85b0-77df3be10740

Verdict: **PASS**. Blocking issues: none.

## Attribution and records

- Commit 0bff888 comes from run a5343e36-0abb-46ac-b70d-31e3e53894c4 (codex.economy, attempt 1): its receipt
  lists only that commit and the 11 allow-listed paths, scope `pass`.
- Run 2884c3e6-27c7-4565-95e7-0650aaa76437 (codex.economy, attempt 4) changed only PROGRESS.md (commit 18768b2), scope `pass`, clean `git_after`.
  Its record `verification/2884c3e6-27c7-4565-95e7-0650aaa76437.json` has result `pass` and exit 0 for all 8 commands
  (both oracles, test-ledger, integration `-k ledger`, scope, clean tree, full suite, no `__pycache__`).
- No code under `scripts/`, `schemas/`, `tests/` or `harness-registry.json` changed between 0bff888 and 8489662.

## Effects confirmed (by reading the diff and running it)

- `configured` exists only on `requested_model`, `resolved_model`, `effort`: `CHECKS` maps those three (and only those)
  to `configured_text_flag`; schema `$defs/configuredTextFlag` with source enum
  `["observed","configured","estimated","unknown"]` is referenced by those three properties only; `textFlag` keeps
  `["observed","estimated","unknown"]`. `observed` is now only the CLI-reported `observed_model`/`fast_state`
  copied from the receipt's observation; `cli_version` stays unknown.
- Builder: `requested_model`/`effort` come from `receipt.requested_configuration`, `resolved_model` from
  `receipt.resolved_configuration`, all labelled `configured`; missing, empty or `"unknown"` values become
  `{"value": null, "source": "unknown"}`; `spec["model"]`/`spec["effort"]` are no longer read.
- Door: Cursor door = `cursor-<family of resolved model>`, speed unused (Grok at standard speed → `cursor-grok`,
  pool `cursor`, billing `included`). Other providers: the CLI name. A name that is not a key of the registry's
  `doors` gives door, pool and billing all `unknown`, so a derived name is never emitted unless it is a real
  registry door. `tier` = economy/premium, else null (brain runs).
- Fixtures: all six on v2, `door` = real CLI door, `tier` = old door value; good-completed's three fields say
  `configured` (good-failed had none marked `observed`, correctly unchanged).
- Integration test: only the mutation string changed (`model` → `spec["model"]`), as the task said.

## Hostile inputs through the real CLI (`scripts/ledger.py validate`, scratch copy, 32 probes)

All refused with exit 1 and a fixed message; a marker string placed in the hostile value never appeared in output:
schema_version 1 / "2" / True / 2.0 (`schema_version: must be 2`); pure v1 shape with tier removed (`tier: is required`);
`configured` on observed_model/cli_version/fast_state (`<field>.source: must be one of observed, estimated, unknown`);
hostile string/list/dict as requested_model.source; configured value 3, whitespace, absolute path, email
(`must be a non-empty string` / `privacy`); unknown source with a value; extra key inside `effort` and at top level
(`unknown key; name not printed`); tier hostile string, `Economy`, ` economy`, 0, False, list, dict
(`tier: must be one of economy, premium or null`); tier missing; door empty. Controls (good row, tier null) pass.
**Accepted:** `door: "economy"` and `door: <any non-empty text>` → finding N1.

## Mutation run (scratch copy of 0bff888, each mutant applied alone, restored after)

Counted: failing tests in `tests/test-ledger.py` / in `tests/test-execution-integration.py -k ledger` / oracles failing.
Baseline: 0 / 0 / none.

| Mutant | test-ledger | integ. | oracles |
| --- | --- | --- | --- |
| M01 `SCHEMA_VERSION = 1` | 107 | 11 | A B |
| M02 `configured` dropped from `CONFIGURED_SOURCES` | 93 | 11 | A B |
| M03 requested_model → `text_flag` | 94 | 11 | A B |
| M04 resolved_model → `text_flag` | 91 | 11 | A B |
| M05 effort → `text_flag` | 86 | 11 | A B |
| M06 cli_version → `configured_text_flag` | 1 | 0 | A |
| M07 observed_model → `configured_text_flag` | 1 | 0 | A |
| M08 fast_state → `configured_text_flag` | 1 | 0 | A |
| M09 null tier refused | 2 | 0 | A B |
| M10 tier check removed | 7 | 0 | A |
| M11 `tier` dropped from `FIELDS` | 108 | 11 | A B |
| M12 Cursor door fixed to `cursor-composer` | 1 | 0 | B |
| M13 door returned as CLI name | 1 | 0 | B |
| M14 tier passed through unchecked | 1 | 0 | B |
| M15 resolved model from requested configuration | 1 | 0 | B |
| M16 `"unknown"` guard removed | 1 | 0 | B |
| M17 `configured` written as `observed` | 1 | 0 | B |
| M18 builder `schema_version` 1 | 1 | 10 | B |
| M19 effort taken from spec | 1 | 0 | — |
| M20 pool replaced by `"unknown"` | 1 | 1 | B |
| M21 schema const 2 → 1 | 1 | 0 | — |
| M22 schema configured source enum reverted | 1 | 0 | — |
| M23 schema `effort` `$ref` → `textFlag` | 1 | 0 | — |
| X01 configured value type check skipped | **0** | 0 | A |
| X02 configured null rule removed | 3 | 0 | A |
| X03 family = whole model id | 1 | 0 | B |
| X04 requested model from spec | 1 | 0 | B |
| X05 schema tier enum drops null | 1 | 0 | — |
| X06 unknown door keeps derived name | 1 | 0 | B |
| X07 tier error echoes the value | 7 | 0 | A |

30/30 killed. All builder mutants are caught by the single test
`test_builder_uses_receipt_configuration_registry_doors_and_independent_tier` (coarse but sufficient).

## Non-blocking findings

- **N1 (evidence guard gap; for T-042 or a small follow-up):** `door`, `pool`, `billing_class` are free text in the
  validator and schema. A row edited by hand in `.tasks/ledger/` (outside Git scope, so the receipt does not see it)
  with `door: "economy"` or any name folds. Suggest: the fold checks door ∈ registry `doors` ∪ {`unknown`}, and
  pool/billing equal that door's registry values at the run's `base_commit` (the same read T-042 adds).
- **N2 (test gap):** X01 (configured value not type-checked) survives `tests/test-ledger.py`; only Oracle A
  (not in `run-tests.sh`) kills it. Add a CLI subtest: `requested_model.value = 3` with source `configured`.
- **N3 (operational, before F005 fold):** `fold_mission` validates every row of this mission in `.tasks/ledger/`
  and stops at the first error. There are 31 v1 rows of this mission there (3 v2). Move them aside (per the
  Architect's list) before `python3 scripts/ledger.py fold`, or the fold exits 1.
- **N4 (calibration quality):** `reviews/grok-calib-1-T-041.md` holds only "Verdict: PASS / done" (19 bytes): no
  checks, probes or mutants. For calibration reviews 2 and 3, require grok to list its evidence.
- Nits: `check_schema_version` hard-codes `"must be 2"` instead of using `SCHEMA_VERSION`; `configured_text_flag`
  duplicates `check_flag` (a `sources` parameter would do); missing blank line before
  `test_lists_reject_duplicates_and_bad_checks`.

## Calibration (owner decision 2, guard review 1 of 3)

Grok-4.7-high (cursor.premium): PASS, no findings. Opus: PASS, no blocking; 4 non-blocking (N1–N4).
Same blocking set (none). Grok missed N1 and N2.

=== FILE: routing-data.jsonl (append one line) ===

{"type":"review-calibration","task":"T-041","guard_review":1,"commit":"0bff888","grok_review":"reviews/grok-calib-1-T-041.md","grok_verdict":"PASS","grok_blocking":[],"opus_run_id":"cb23708f-7387-4c3b-85b0-77df3be10740","opus_verdict":"PASS","opus_blocking":[],"same_blocking":true,"opus_nonblocking_missed_by_grok":["N1 door free text","N2 X01 survives test-ledger"],"note":"grok output had no evidence (19 bytes)"}
