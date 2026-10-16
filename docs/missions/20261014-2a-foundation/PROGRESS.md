---
note: Current state only. Full history is in progress-archive/ (read-only). Newest entry on top; at most 10 lines per entry; full reviewer outputs go to reviews/<run-id>.md. Workers do not write this file; the Front Desk records each run from its receipt.
---

# Progress

## Current status (2026-10-16)
- Mission 2A Foundation, branch `mission/2a-foundation`, status in-progress. Gate 0 passed. **Gate 1 target:** F001–F006 accepted and the deterministic suite green (prepare, do not advance).
- **Accepted:** F001, F003, F005, F006 (F005 with the first ledger fold). **F004** and **F007** wait for the agy amendment (agy dropped from the mission by owner decision; T-026 and T-039 deferred).
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
- **2026-10-16 — ARCHITECT PLANNING RUN T-044 (brain run cd8b0381-28d5-462f-8aa7-c88b24e1f4fa, log `.tasks/logs/cd8b0381-28d5-462f-8aa7-c88b24e1f4fa.log`): T-044 delivered.** Planning only. The spec said action `review`, but no worker diff is waiting; I did the planning request above. No worker ran, …
  Full text: `reviews/entry-917890ce.md`.
- **2026-10-16 — ARCHITECT PLANNING RUN T-044 ONLY (not a diff review). HARD DEADLINE: write your entry by minute 25** Design T-044 with task text, a reference patch (outside the repo tree), and a mutant list as blocks `=== FILE: tasks/T-044.md ===`, `=== FILE: reviews/<your run id>-mutants.md ===` (tell me the patch path in your entry). Task: extend the `scripts/ledger.py` privacy rule with the owner's near-misses: `/tmp` and `/etc` without a trailing slash, case-insensitive absolute paths (`/TMP/x`, `/Users/` in any case), `${HOME}`, `~root/x` (any `~name/`), NBSP or a double space after Bearer, U+061C (Arabic letter mark). Legitimate relative paths, ids, model names, check labels and real values from `.tasks/receipts`, `routing-data.jsonl` and `tests/fixtures/ledger/*` must still pass (measure false positives on those and list the numbers). Owner rule 6: every verification command fails on the base and passes after the patch; the full suite passes after. Feature field: use `F004` (dispatch label; there is no F008). The allow-list MUST include the PROGRESS.md allowance as in tasks/T-042.md. Real date 2026-10-16. Do not review commits.
- **2026-10-16 — T-043 reviewed by Opus: PASS; calibration 3 of 3 complete** Opus run 201e6ecf-f918-4afb-952c-052f0757bd12 (`reviews/201e6ecf-f918-4afb-952c-052f0757bd12.md`): 25 of 26 mutants killed (survivor: marker pattern without re.M); all 78 existing records still validate; no repo test file triggers the new detection. Non-blocking: ANSI/CR-only/`pytest -q` undetected; `run-tests.sh` check() hides child skips; quadratic regex on hostile long lines.
  **Calibration result (3 guard reviews: T-041, T-042, T-043):** grok-4.7-high and Opus agreed on the blocking verdict every time (PASS, none), but none of the three had a real blocking issue, so grok's detection of one is still untested. Grok found no hardening gaps that Opus missed; it missed 2–4 non-blocking items per review. Rows in routing-data.jsonl (`type: review-calibration`).
  T-043 is a label under F004 only (no feature of its own). Next: T-044 planning (privacy near-misses).
- **2026-10-16 — T-043 reviewed by Opus (commit 53fb0f5): PASS, nothing blocking. Calibration 3 of 3: same blocking verdict as grok, and grok missed 1 surviving mutant plus 3 hardening gaps.** Brain run 201e6ecf-f918-4afb-952c-052f0757bd12, log `.tasks/logs/201e6ecf-f918-4afb-952c-052f0757bd12.log`. …
  Full text: `reviews/entry-0dd51d47.md`.
- **2026-10-16 — Grok calibration review 3 of 3 done (T-043): PASS, no blocking, substantive static review; Opus review requested** **ARCHITECT REVIEW REQUEST, T-043 (commit 53fb0f5 only; the VERIFIER is the strongest guard).** `git show 53fb0f5`; task `tasks/T-043.md`; grok's review `reviews/grok-c …
  Full text: `reviews/entry-1e939a2e.md`.
- **2026-10-16 — T-043 verified (run b0dbcaf5-1621-4515-9df6-7196fd498672, claude.economy haiku); calibration review 3 of 3 (grok) started** Receipt: completed, exit 0, scope pass, commit 53fb0f5, 3 paths; VERIFY PASS (7 commands incl. both oracles and the full suite). Before verifying I deleted a stray `scripts/__pycache__/ledger.cpython-314.pyc` (written by my own `ledger.py fold` run for the F005 acceptance, not by a worker) — recorded per the standing rule.
  Verifier code is a guard: Opus review follows grok's.
- **2026-10-16 — T-043 has no feature: dispatch bookkeeping label F004 (decision needed from the owner, not blocking)** The dispatcher requires a pending feature; the Architect labelled T-043 as F008, which does not exist in features.json (and I will not add a feature without the owner). F001 is accepted, so it is refused. T-043 and T-044 are dispatched under the open feature F004 as a label only; they are not F004 acceptance evidence. If you want a feature for mission hygiene work (verifier, privacy near-misses, launcher prompt), say so and I will add F008 by an approved amendment.
- **2026-10-16 — T-043 ready (rule 6 checked incl. full suite); dispatch on claude.economy** Architect plan run 31a836d5-eed3-48ec-bdc5-e7c9e62fb554 (task text in tasks/T-043.md, mutants in reviews/31a836d5-…-mutants.md; the reference patch stays in the Architect's scratchpad, copied to my scratchpad). My check: 2 oracle commands fail on base and pass after the patch; the full suite passes after the patch (353 s).
