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
- **2026-10-16 — T-048 verified (run 9ba27d36-cbc8-4fb4-b782-a46829083dc3, codex.premium, commit 455a0af) but grok review FAIL (privacy); T-048-R1 written, rule 6 checked, dispatch on cursor.economy** Grok: `probe_seat.mcp_names` keeps the whole first token of a line with no ": ", so a line like `MCP_URL=https://user:password@evil.example/mcp?token=S1` would be stored as a server name in mcp.json (local-only evidence, but the task said names only). T-048-R1 = names must match [A-Za-z0-9._ -]{1,64} (claude's "claude.ai Claude Docs" kept whole; codex table first column; anything else dropped); oracle fails on base, passes after.
- **2026-10-16 — T-049 reviewed by Opus: PASS (run 7038bb5c-4b3c-4cc6-b7c7-9dc6b56bcb81); seeded-defect calibration: grok-4.7-high caught 3 of 3** Opus: silent-since-launch stalls (exit 123) and 0-turn failures (exit 122) behave as planned; 15 of 20 mutants caught; the owner's literal 90 s idle rule would stop healthy runs (suite, 142 s silent tool calls, long thinking, rate-limit backoff), so the plan keeps 90 s to first byte and 900 s idle (your decision, overrides exist). Follow-ups (T-057 queued): tests for M7/M9/M13, reject nan/inf, validate the env value in the wrapper before persisting the spec; **F009 risk: agy -p prints plain text only at the end, so any agy run over 90 s would stall; needs stream-json (the adapter plan has it) or a per-provider startup limit.**
  Seeded defects (item 8; `.tasks/seed-review.py`): grok-4.7-high found all three planted blocking bugs with file:line and a failing input (A T-043 marker without re.M; B T-042 git read without --no-replace-objects; C T-044 `~name/` rule removed). Argon not yet tested (needs agy admission). Rows in routing-data.jsonl.
- **2026-10-16 — Opus review of T-049 (brain run 7038bb5c-4b3c-4cc6-b7c7-9dc6b56bcb81, log `.tasks/logs/7038bb5c-4b3c-4cc6-b7c7-9dc6b56bcb81.log`): Verdict: PASS.** Reviewed worker run 260236bf (receipt: completed, exit 0, scope pass, clean `git_after` 7292638, 14 paths all allow-listed, seat claude …
  Full text: `reviews/entry-b0d0dcea.md`.
- **2026-10-16 — T-049 verified (run 260236bf-dd11-4553-8578-3f8e1078a885, claude.premium, commit 7292638); Opus review requested (GUARD: runner watchdog and zero-turn failure)** VERIFY PASS (oracle, named tests, integration, observe-output, shellcheck, full suite).
  Full text: `reviews/entry-d9f08c87.md`.
- **2026-10-16 — T-050 reviewed by Opus: PASS (run 4abdd954-b293-4998-af68-033aa71070df); strict-mcp-config proven on this Mac; T-049 rule 6 checked (focused); dispatch T-049 on claude.premium** Opus: 8 mutants caught, one survivor (schema enum, pre-existing gap); observed from its own contract-7 brain run: init event `mcp_servers: []` and no `mcp__` tools, while 7 claude.ai connectors exist, so `--strict-mcp-config` leaves them out on this Mac. Non-blocking: schema-enum parity test; claude stream-json fixture in test-observe-output; logs grow with --verbose. A run stopped before `result` gives observed `unknown` (T-049 follow-up).
- **2026-10-16 — Opus review of T-050 (brain run 4abdd954-b293-4998-af68-033aa71070df, log `.tasks/logs/4abdd954-b293-4998-af68-033aa71070df.log`): Verdict: PASS.** No feature accepted (F008 has open steps).
  Full text: `reviews/entry-5358ed17.md`.
- **2026-10-16 — T-050 verified (run e829a076-eb0f-46c3-9ee0-864c43667ddb, claude.economy, commit 6991b90); Opus review requested** VERIFY PASS (oracle, spec tests, integration, shellcheck, full suite).
  **ARCHITECT REVIEW REQUEST, T-050 (commit 6991b90; provider contract 7: claude stream-json + --strict-mcp-config).** Confirm by effect with fake CLIs: claude worker and brain argv carry `--strict-mcp-config` and `stream-json --verbose`, other providers' argv unchanged at 7, contract 6 specs still validate, the observation parser still gets model and usage from a stream-json log; mutate each new check once and count the tests that catch it; judge your own caveat (does `--strict-mcp-config` leave out the claude.ai connectors? you cannot test it with a real CLI; say what a safe probe is). Short, fake CLIs, scratch clones, PYTHONDONTWRITEBYTECODE=1. PROGRESS entry at most 8 lines. End with Verdict: PASS or FAIL.
- **2026-10-16 — T-050 (claude contract 7: stream-json + --strict-mcp-config) rule 6 checked (focused); dispatch on claude.economy** Architect plan a9e69754: order T-050, T-049, T-048 (T-049's startup watchdog would stop every Claude run at 90 s under contract 6, which prints nothing until the end). Owner decision flagged by the Architect: idle limit = 90 s since launch (no byte at all) and 900 s after the first output, because a silent tool call is normal (one test file alone ran 133 s silently); overrides via SPAWN_*_STALL_SECS / IDLE_SECS. I follow the plan and report it; set the idle value to 90 if you want your literal rule.
- **2026-10-16 — Architect (Opus brain run a9e69754-3c78-46f6-a040-24b29a630779): probe-seat / stall watchdog / MCP isolation plan (F008) delivered; dispatch order T-050, T-049, T-048** Log `.tasks/logs/a9e69754-3c78-46f6-a040-24b29a630779.log`. Planning only: no diff reviewed, no worker or provider …
  Full text: `reviews/entry-cbb8aaeb.md`.
- **2026-10-16 — Architect run e08df13d (probe plan) interrupted after 9 s by me (pkill): I launched it before the request was in PROGRESS.md; no change made, tree clean. Request now written; relaunching.**
- **2026-10-16 — ARCHITECT PLANNING RUN (not a diff review): seat probe, stall watchdog, MCP isolation (owner item 3). PLAN FILE FIRST: in your first minutes write the plan skeleton (task titles, allow-lists, oracles) to your PROGRESS entry's linked file `docs/missions/20261014-2a-foundation/reviews …
  Full text: `reviews/entry-f56fda37.md`.
- **2026-10-16 — T-047 verified (run 93256451-ae5c-4dc0-828c-ea2cb8ad3389, cursor.economy): docs drift fixed (AGENTS.md, consumer template, mcp-hygiene); agy evidence recorded; MCP server lists found** VERIFY PASS (oracle + shellcheck + full suite + clean tree + bytecode). Grok review of the docs diff follows (routine). `evidence/agy-mcp-hang.md` written from the owner's finding (issue #1087; MCP server never finished starting; fix; 39 s to 7 s).
  **MCP servers found (names only; I changed no CLI config):** claude: claude.ai Claude Docs, Cloudflare Developer Platform, Supabase, Notion, Google Drive, Google Calendar, Gmail (all connected), plus a local `supabase` HTTP server pending approval; codex: code-review, codex_app, computer-use (disabled), cua_repl, node_repl (enabled); cursor-agent: none; agy: none. For unattended Claude workers this is why `--strict-mcp-config` (item 3) matters; for codex two enabled servers (cua_repl, node_repl) are reported to you.
