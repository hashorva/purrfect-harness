---
note: Current state only. Full history is in progress-archive/ (read-only). Newest entry on top; at most 10 lines per entry; full reviewer outputs go to reviews/<run-id>.md. Workers do not write this file; the Front Desk records each run from its receipt.
---

# Progress

## GATE 1 PRESENTED (2026-10-16) — NOT advanced; waiting for your verdict
F001, F003, F004, F005, F006 accepted (F002 removed at Gate 0). F004: run 35ecb39a-5c22-4108-acef-41f7fc694ad6, record sha256 64e8240b…; `ACCEPT OK`; `verify-mission.sh --require-workers` VERIFY OK; ledger folded in the same commit (21 rows, second fold a no-op). Deterministic suite green on the last code commit (`bash tests/run-tests.sh` exit 0; docs/feature/ledger-only commits since). Evidence package: `reviews/gate1-prep.md`. To advance: `verify-mission.sh` exit 0, set `status: awaiting-gate` in GOAL.md, your verdict, then a "Human - GATE 1" entry.

## DAY 4 STATUS (live; the full report replaces this at the end)
Order from the owner: speed rules; 1 (done: F004 accepted, Gate 1 presented); 6, 3, 2, 5, 7, 10, 8, 9, 4.

## DAY 3 STOP REPORT (2026-10-16; superseded by the day-4 sections above where they differ)

- **Ready for you:** F004 acceptance (command and sha in `reviews/gate1-prep.md`; that file is also the Gate 1 package: after F004 is accepted, F001-F006 are accepted, the suite is green on HEAD and `verify-mission.sh` is OK). Gate 1 is prepared, not advanced.
- **Done this round:** step 0 (PROGRESS.md archived, 717 KB to 10 KB); F003, F006 accepted; cursor.premium re-frozen (drift event, smoke passed); ledger v2 (T-041, T-042) then F005 accepted with the first fold (8 v2 rows, 1 drift event; the 31 v1 rows set aside); privacy near-misses (T-044), skipped-check-is-a-failure (T-043), workers no longer write PROGRESS.md (T-045); agy dropped by amendment (F004/F007/GOAL, T-026/T-039 deferred); F004 acceptance run (T-046); F007 smoke code (T-037, R1) and the **real F007 smoke on this Mac** (exit 0, 4 workers + 1 brain) with its evidence file (T-038).
- **Worker runs this round (T-041 onward): 18**: 9 done, 9 not: by class task 3 (2 attributable: T-042 attempt 1 no commit, T-037 live-tree check order; 1 plan defect), harness 3 (launcher prompt vs task conflict; a no-change run cannot be verified), environment 3 (stray bytecode; 2-minute baseline outliving a Codex tool window; my backtick in an oracle). Seats: cursor.economy 7, codex.economy 6, claude.economy 5. Category x seat, attributable task failures only: ledger x cursor.economy 1, diagnostics x cursor.economy 1.
- **Architect/brain runs: about 17** (6 plan runs, 7 guard reviews, 2 timed out with nothing written, 1 proposal, 1 early misfire). No vendor limit message from any CLI; no seat paused; agy.economy stays out. Calibration: grok-4.7-high and Opus agreed on every blocking verdict (all PASS), but none of the three had a real blocking issue, so grok's detection of one is untested; grok missed 2-4 non-blocking items per review.
- **Decisions I need from you:**
  1. **F007 step 2:** the real smoke shows Codex reports usage but no model (observed model `unknown`). Amend the step (codex and cursor may stay unknown), read Codex's own session record after the run (observed), or leave F007 open. F007 acceptance command is NOT prepared until you decide (record run f544e83c-6189-4e96-80a6-677224ef1dfa exists and passes, but the step as written is not met).
  2. **F004 acceptance** (the command in gate1-prep.md), then Gate 1.
  3. **Structured progress** (`docs/proposals/20261016-structured-progress.md`): Architect recommends the first feature of 2B (2 S + 2 M + an S rule-6 tool); you decide 2B or pull into 2A.
  4. **AGENTS.md** and `docs/templates/AGENTS.md.template` still say sessions append to PROGRESS.md, and mcp-hygiene rule 5 and its self-check still say to write PROGRESS.md (grok found it): your files / a small docs task (T-047 queued).
  5. T-043 and T-044-T-046 were dispatched under label F004 (no feature of their own); say if you want an F008 for mission hygiene.
  6. Open from before: the lesson candidates, the near-miss bypasses left after T-044 (format marks, `%HOME%`, percent-encoding), ledger N3 (every read path validates against the working-tree registry; renaming a door later breaks old rows).

## Current status (2026-10-16)
- Mission 2A Foundation, branch `mission/2a-foundation`, status in-progress. Gate 0 passed. **Gate 1 target:** F001–F006 accepted and the deterministic suite green (prepare, do not advance).
- **Accepted:** F001, F003, F005, F006 (F005 with the first ledger fold). **F004 ready (acceptance command prepared); F007 open (step 2 vs Codex).** (agy was dropped by the amendment (agy dropped from the mission by owner decision; T-026 and T-039 deferred).
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
- **2026-10-16 — T-060 (Argon registry lane) and T-026 (chair on agy, fixture proof) delivered by the Architect (run c9300dc7-3bdb-4f65-a426-120a69c624f1; T-026: no code change needed, a test-only proof, 8/8 mutants); rule 6 (focused) holds for both; dispatch T-060 on claude.premium**
- **2026-10-16 — ARCHITECT PLANNING RUN: T-060 and T-026 only (rest of the F009 plan). Not a diff review. Skeleton into this entry first, then extend the SAME entry per block.** T-039 landed (contract 8, Opus PASS); agy.economy is admitted (6/6 probes). Deliver as blocks `=== FILE: tasks/T-060.md == …
  Full text: `reviews/entry-a4f1f5c5.md`.
- **2026-10-16 — agy.economy re-frozen to gemini-3.8-flash-medium (drift event) and ADMITTED: 6 of 6 probes ok, MCP list empty** Fleet: agy.economy `gemini-3.8-flash-high`/medium → `gemini-3.8-flash-medium`/medium (effort in the model name; Flash quota; never fast); `validate-fleet` rc 0; drift row local, folded at the next acceptance. Probes (`probe-seat.sh agy.economy`, 3 in a fresh temp folder: ok, 4.3/5.3/8.5 s, 15016–15027 input tokens; 3 in the repo folder with the same adapter argv: ok, 6.1/7.5/4.4 s); `agy mcp list` = "No MCP servers configured" before and after. Evidence local under `.tasks/probes/`. agy.economy joins the rotation. (probe-seat.sh has no in-repo option yet: the repo probes used its dry-run argv by hand; a small follow-up.)
- **2026-10-16 — T-039 reviewed by Opus: PASS (run 860e93f6-5486-44e0-8449-3357954c9f47); agy.economy re-freeze next, then admission probes** Opus by effect with fake agy: contract 8 argv = stream-json, no --effort, model suffix must match effort (wrong/missing refused before launch); contract 7 and other providers unchanged; the real flash-low sample replays to model gemini-3.8-flash-low, 15015/1 tokens; every no-turn shape (empty SUCCESS with 0 turns/0 tokens, missing result) is a failure; the watchdog counts agy log growth as output. Full text `reviews/entry-511c4cce.md`.
- **2026-10-16 — Opus review of T-039 (brain run 860e93f6-5486-44e0-8449-3357954c9f47, log `.tasks/logs/860e93f6-5486-44e0-8449-3357954c9f47.log`): Verdict: PASS.** Worker run 3bf1573e: receipt completed, exit 0, scope pass, clean `git_after` c7b9226; verification record passes (11 of 11 commands, i …
  Full text: `reviews/entry-511c4cce.md`.
- **2026-10-16 — T-039 verified (attempt 2, run 3bf1573e-766c-408b-8893-9e1211b0ab4b, cursor.economy; commits 1a37351 + c7b9226); Opus review requested** VERIFY PASS (all commands incl. the full suite).
  Full text: `reviews/entry-300fac75.md`.
- **2026-10-16 — T-039 attempt 1 (codex.premium, run 9fdb5d1b-5b8e-465b-83e4-49e817496bbe, commit 1a37351): verification FAIL — the integration helper still asserts contract 7 (32 sub-tests, 8 != 7); task failure** My speed shortcut (rule 6 without the full suite) did not catch it; the verifier did. Attempt 2 note added (fix tests/test-execution-integration.py:306 and any other hard-coded current contract); the attempt 2 worker runs one 30-second test, not the whole file.
- **2026-10-16 — T-039 (agy adapter, contract 8) rule 6 checked (focused; the spec-load check needs the live .tasks/specs, now passed via PURRFECT_LIVE_ROOT: 183 specs load, 0 bad); dispatch on codex.premium**
- **2026-10-16 — T-048-R1 verified and grok re-review PASS (probe names are safe); Architect agy-lane plan hit the 40-minute limit with T-039 complete (partial plan kept); T-039 rule 6 next** Grok on 7a77c5c: no blocking issue (residual: a bare token that matches the safe character set would still be kept as a name; judged non-blocking). Architect run e432a18d: exit 124 but the plan file had T-039 ready (13 of 13 mutants caught), order T-039 -> T-060 (registry: argon family, agy-argon door + weekly-only pool) -> T-061 (admission probes) -> my re-freeze of the agy seats -> T-026; T-060, T-061 and T-026 were not delivered; I will ask for them again after T-039 lands.
- **2026-10-16 — ARCHITECT PLANNING RUN: F009 agy lane (owner item 2 a, c, d). Not a diff review. PLAN FIRST: write your skeleton into this entry in the first minutes, then extend the SAME entry as each block is ready.** Facts: `evidence/agy-mcp-hang.md` (cause: an MCP server; fixed; `agy mcp list` …
  Full text: `reviews/entry-a2cd5705.md`.
- **2026-10-16 — T-048 verified (run 9ba27d36-cbc8-4fb4-b782-a46829083dc3, codex.premium, commit 455a0af) but grok review FAIL (privacy); T-048-R1 written, rule 6 checked, dispatch on cursor.economy** Grok: `probe_seat.mcp_names` keeps the whole first token of a line with no ": ", so a line like `MCP_URL=https://user:password@evil.example/mcp?token=S1` would be stored as a server name in mcp.json (local-only evidence, but the task said names only). T-048-R1 = names must match [A-Za-z0-9._ -]{1,64} (claude's "claude.ai Claude Docs" kept whole; codex table first column; anything else dropped); oracle fails on base, passes after.
- **2026-10-16 — T-049 reviewed by Opus: PASS (run 7038bb5c-4b3c-4cc6-b7c7-9dc6b56bcb81); seeded-defect calibration: grok-4.7-high caught 3 of 3** Opus: silent-since-launch stalls (exit 123) and 0-turn failures (exit 122) behave as planned; 15 of 20 mutants caught; the owner's literal 90 s idle rule would stop healthy runs (suite, 142 s silent tool calls, long thinking, rate-limit backoff), so the plan keeps 90 s to first byte and 900 s idle (your decision, overrides exist). Follow-ups (T-057 queued): tests for M7/M9/M13, reject nan/inf, validate the env value in the wrapper before persisting the spec; **F009 risk: agy -p prints plain text only at the end, so any agy run over 90 s would stall; needs stream-json (the adapter plan has it) or a per-provider startup limit.**
  Seeded defects (item 8; `.tasks/seed-review.py`): grok-4.7-high found all three planted blocking bugs with file:line and a failing input (A T-043 marker without re.M; B T-042 git read without --no-replace-objects; C T-044 `~name/` rule removed). Argon not yet tested (needs agy admission). Rows in routing-data.jsonl.
- **2026-10-16 — Opus review of T-049 (brain run 7038bb5c-4b3c-4cc6-b7c7-9dc6b56bcb81, log `.tasks/logs/7038bb5c-4b3c-4cc6-b7c7-9dc6b56bcb81.log`): Verdict: PASS.** Reviewed worker run 260236bf (receipt: completed, exit 0, scope pass, clean `git_after` 7292638, 14 paths all allow-listed, seat claude …
  Full text: `reviews/entry-b0d0dcea.md`.
