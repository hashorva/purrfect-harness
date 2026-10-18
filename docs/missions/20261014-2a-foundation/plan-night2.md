# Night 2 plan — mission 2A Foundation (Architect run 7c022e62-340c-47e5-9e56-243f0ec06cff)

Draft only. The Front Desk copies each `T-0NN.md` unchanged to
`docs/missions/20261014-2a-foundation/tasks/` and commits it before dispatch. Nothing here
changes `features.json`, `fleet.json` or the mission status.

Plan: READY (see "Owner decisions" for items that block single seats, not the plan).

## Ordered list

Size: S = one short session, M = one full economy session, L = the upper limit for one
economy session. Review: `Architect` = a `spawn-brain.sh review` run (batch where shown);
`code-reviewer` = the read-only subagent.

| # | Id | Title | Feature | Category | Size | Review | Seats to avoid |
|---|---|---|---|---|---|---|---|
| 1 | T-007 | Seat smoke slice 1: clone, smoke mission, `--smoke --dry-run` | F007 (carrier) | diagnostics | M | Architect, batch B1 | codex (clones contain `.agents/`) |
| 2 | T-008 | Seat smoke slice 2: launch, classify, summary | F007 (carrier) | diagnostics | M | Architect, batch B1 | codex |
| — | S1 | **Front Desk:** real `bash scripts/fleet-doctor.sh --smoke` (all 7 worker seats) | — | orchestrator step | — | — | — |
| 3 | T-009 | Cursor contract 4: plain model ID | F004 | adapter | M | Architect, batch B2 | cursor.* (broken until this lands) |
| — | S2 | **Front Desk:** `fleet-doctor.sh --smoke --seat cursor.economy --seat cursor.premium` | — | orchestrator step | — | — | — |
| 4 | T-010 | Export `PYTHONDONTWRITEBYTECODE=1` in both launchers | F007 (carrier) | launcher | S | Architect, batch B2 | — |
| 5 | T-011 | Verification in a clean temporary worktree | F007 (carrier) | verification | L | Architect, alone (B3) | — (premium seat for attempt 2) |
| 6 | T-012 | Numbered VerificationRecords | F007 (carrier) | verification | M | Architect, batch B4 | — |
| — | P-1 | **Front Desk probe:** Codex `--add-dir .agents` (2 tiny Luna calls) | — | orchestrator step | — | — | — |
| 7 | T-013 | Codex `--add-dir .agents` (only if P-1 passed) | F004 | adapter | S | Architect, batch B4 | — |
| 8 | T-016 | N1: compare provider names after conversion | F004 | launcher | S | Architect, batch B4 | — |
| 9 | T-014 | Registry `sandbox_limits` | F004 | registry | S | Architect, batch B5 | — |
| 10 | T-015 | `dispatch_policy` refuses allow-lists that hit a write limit | F004 | dispatch-policy | M | Architect, batch B5 | codex (edits `.agents/`) |
| 11 | T-017 | Registry validator gaps; N3 pinned | F004 | registry | S | Architect, batch B5 | — |
| — | A-2 | **Architect run:** parallel worktree dispatch proposal (document) | — | proposal | — | owner | — |
| — | P-2 | **Front Desk probe:** JSON output and `--json-schema` per CLI (4 tiny calls) | — | orchestrator step | — | — | — |
| 12 | T-018 | Observation parser + fixtures | F003 | parser | M | code-reviewer | — |
| 13 | T-019 | Receipt v2 `observation` block | F003 | receipts | M | Architect, batch B6 | — |
| 14 | T-020 | Adapters request JSON; runner fills observation (F003 acceptance run) | F003 | adapter | M | Architect, batch B6 | — |
| — | S3 | **Front Desk:** re-smoke all seats (argv changed) | — | orchestrator step | — | — | — |
| 15 | T-021 | Registry model-name encoding; door providers | F004 | registry | S | Architect, batch B7 | — |
| 16 | T-022 | Fleet v2 document validation | F004 | fleet | M | Architect, batch B7 | — |
| 17 | T-023 | Fleet v2 resolver | F004 | fleet | M | Architect, batch B7 | — |
| 18 | T-024 | Per-spawn resolution + drift log | F004 | launcher | M | Architect, batch B8 | — |
| 19 | T-025 | Delete FALLBACKS | F004 | registry | S | Architect, batch B8 | — |
| 20 | T-026 | Chair seat → agy `claude-opus-5-5-high` with drift (F004 acceptance run) | F004 | fleet | S | Architect, batch B8 | — |
| — | A-1 | **Architect run:** brain-seat move plan (document; not applied) | — | proposal | — | owner | — |
| 21 | T-027 | Ledger row schema + validator | F005 | ledger | M | code-reviewer | — |
| 22 | T-028 | Ledger privacy rule | F005 | ledger | S | Architect, batch B9 | — |
| 23 | T-029 | Runner writes a ledger row per run | F005 | ledger | M | Architect, batch B9 | — |
| 24 | T-030 | Fold rows and drift events exactly once | F005 | ledger | M | Architect, batch B9 | — |
| 25 | T-031 | Derived view helper | F005 | ledger | S | code-reviewer | — |
| 26 | T-032 | Docs: ledger in the loop (F005 acceptance run) | F005 | docs | S | code-reviewer | codex (edits `.agents/`) |
| 27 | T-033 | Verdict schemas + dependency-free validator | F006 | schema | M | code-reviewer | — |
| 28 | T-034 | Registry `structured_output`; post-run validation | F006 | registry | S | Architect, batch B10 | — |
| 29 | T-035 | Skills name the schemas (F006 acceptance run) | F006 | docs | S | code-reviewer | codex (edits `.agents/`) |
| — | G1 | **GATE 1 (human):** after F001-F006 accepted; deterministic suite green | — | gate | — | human | — |
| 30 | T-036 | Reconstruct command | F007 | diagnostics | S | code-reviewer | — |
| 31 | T-037 | F007 smoke mode | F007 | diagnostics | M | Architect, batch B10 | codex |
| — | H-1 | **Front Desk on the Mac:** `fleet-doctor.sh --smoke --f007 --keep --dest .tasks/smoke/f007` (5 worker + 1 brain run) | — | orchestrator step | — | — | — |
| 32 | T-038 | F007 evidence (F007 acceptance run) | F007 | docs | S | code-reviewer, then human | — |
| — | G2 | **GATE 2 (human):** reads the reconstruct output | — | gate | — | human | — |

Every worker task: `max_attempts: 2`; `worker:`/`invocation:` = `any usable economy seat (the
Front Desk rotates)`; JSON-argv verification commands; a "Why each check exists" section; the
long-command rule and the standing rules in the Iteration policy.

## Dependencies

- T-007 → T-008 → Architect B1 → S1.
- T-009 → Architect B2 → S2. T-009 is independent of T-007/T-008 and may run before them if a
  seat is idle, but the Cursor seats stay unusable until S2.
- T-010 → T-011 → T-012 (all touch the verification path; serial).
- P-1 → T-013 (only if P-1 passed) → T-014. T-016 → T-015 (both edit `spawn-worker.sh`).
  T-014 → T-015 and T-014 → T-017 (same registry files).
- P-2 → T-018 → T-019 → T-020 → S3.
- T-009, T-017 → T-021 → T-022 → T-023 → T-024 → T-025 → T-026 → A-1.
- T-019 → T-027 → T-028; T-020 + T-028 → T-029; T-029 + T-024 → T-030; T-027 → T-031;
  T-028 + T-030 + T-031 → T-032.
- T-033 → T-034 (also needs T-021 and P-2) → T-035.
- T-012 + T-029 → T-036; T-008 + T-020 + T-026 + T-029 + T-036 → T-037 → H-1 → T-038 → G2.
- G1 after F001, F003, F004, F005, F006 are accepted.

## Orchestrator steps (Front Desk; not worker tasks)

**S1 — real seat smoke.** After T-007/T-008 are verified and Architect batch B1 is PASS:
`bash scripts/fleet-doctor.sh --smoke` from the live root (clean tree). Expected before the
fixes: `cursor.*` `unusable` (bracket argument), `codex.*` `usable-with-limit` (`.agents/`),
`claude.*` `usable`, `agy.economy` unknown. Record the summary path and each seat line in
PROGRESS.md; a seat's first use needs `usable` or `usable-with-limit` (then route around the
limit). New limits go to the sandbox-limit table through a small docs task.

**S2 — Cursor re-smoke** after T-009 is verified and reviewed. Expected: `cursor.economy`
`usable`; `cursor.premium` `unusable: cursor model name encodes effort xhigh; spec effort is medium`
until the owner decides (see Owner decisions).

**S3 — full re-smoke** after T-020 (every provider's argv changed).

**P-1 — Codex `.agents/` probe** (two tiny Luna calls, included quota):

```bash
P=$(mktemp -d "${TMPDIR:-/tmp}/codex-agents-probe.XXXXXX")
git clone --quiet --no-hardlinks "$(pwd -P)" "$P/a" && git clone --quiet --no-hardlinks "$(pwd -P)" "$P/b"
codex exec -C "$P/a" -s workspace-write --add-dir "$P/a/.git" --add-dir "$P/a/.agents" -m gpt-6-luna -c 'model_reasoning_effort="low"' \
  "Create .agents/probe.txt containing the line probe, then run: git add .agents/probe.txt && git commit -m probe. Reply DONE or the exact error."; echo "with_flag_exit=$?"
codex exec -C "$P/b" -s workspace-write --add-dir "$P/b/.git" -m gpt-6-luna -c 'model_reasoning_effort="low"' \
  "Create .agents/probe.txt containing the line probe, then run: git add .agents/probe.txt && git commit -m probe. Reply DONE or the exact error."; echo "control_exit=$?"
git -C "$P/a" log --oneline -1 -- .agents/probe.txt; git -C "$P/b" log --oneline -1 -- .agents/probe.txt
```

PASS = commit in `a`, none in `b`. Record verbatim results in
`evidence/codex-add-dir-agents.md`. If both fail: drop T-013; the limit stays. If both succeed:
drop T-013 and re-open the T-006 attempt 2 diagnosis (the limit was not the path).

**P-2 — JSON output probe** (one tiny call per CLI, included quota; run from `mktemp -d`):
`claude -p --output-format json --model haiku "Reply with OK only."`;
`codex exec --skip-git-repo-check --json -s read-only -m gpt-6-luna -c 'model_reasoning_effort="low"' "Reply with OK only."`;
`cursor-agent -p --trust --output-format stream-json --model composer-2.5 "Reply with OK only."`;
`agy --help` first, then agy's JSON mode if it lists one. Also each CLI's `--help` (and
`codex exec --help`) for `json-schema` / `output-format`. Save stdout, stderr and exit code per
CLI under `.tasks/probes/observe/`, check the files for emails, tokens or account ids, and
record in PROGRESS.md: which CLI reports the model, which usage fields, which has a schema flag.

**H-1 — F007 real smoke** on the Mac (needs logged-in CLIs; 5 worker + 1 brain run):
`bash scripts/fleet-doctor.sh --smoke --f007 --keep --dest .tasks/smoke/f007`.

## Architect runs requested by this plan

- **A-1, after T-026 (F004 done):** a short written plan for moving the brain seat to agy
  `claude-opus-5-5-high` as a logged drift event (fleet v2 brain seat, doors `["agy","claude"]`,
  the drift event, the rollback, what the owner approves). Not applied.
- **A-2, after T-017 (backlog done):** a short proposal (document, no code) to pull parallel
  worktree dispatch forward from 2B, built on T-011's worktree mechanics and the T-007 clone
  design: disjoint allow-lists, one lock per worktree, serial acceptance.

The Architect's write scope is PROGRESS.md, so each document is drafted under
`.tasks/plans/<run id>/` and the Front Desk commits it under `docs/proposals/`.

## Review batches

B1 = T-007+T-008 (before S1). B2 = T-009+T-010. B3 = T-011 alone. B4 = T-012+T-013+T-016.
B5 = T-014+T-015+T-017. B6 = T-019+T-020. B7 = T-021..T-023. B8 = T-024..T-026.
B9 = T-028..T-030. B10 = T-034+T-037. A batch may be split if the Claude window is short;
never merged across a dependency that needs a PASS first (B1 before S1; B3 before T-012).

## Design decisions (chosen; alternatives rejected)

1. **Smoke environment = a scratch `git clone` of HEAD; each seat runs `spawn-worker.sh`
   inside the clone.** The clone is its own repository root, so the Phase 1 `--repo` guard is
   untouched. Rejected: a linked worktree (its `.git` is a file; Codex's `--add-dir .git` would
   not cover the object store, giving a false Codex failure); lifting the `--repo` guard (not
   allowed in Phase 1). The clone gets one fixture commit: other active missions removed, a
   smoke mission with a fleet that is a byte copy of the frozen fleet except `mission.path`
   and an `approved_by` that names the source file and hash. The live snapshot is compared
   before and after; any change fails the smoke.
2. **Brain seats are not smoked;** the latest completed in-scope brain receipt proves the
   brain seat (this run's receipt will). Only F007's mode launches a brain run, because the
   smoke mission's audit needs one.
3. **Smoke result has three states** (`usable`, `usable-with-limit`, `unusable`), decided from
   receipts and Git only, so a Codex seat with the `.agents/` limit stays usable for other work.
4. **Cursor fix = new provider contract 4 (plain model ID), contracts 1-3 unchanged.** v1-v3
   specs keep their recorded argv byte for byte. Contract 4 refuses a model name whose effort
   token contradicts the spec effort. Rejected: silently sending `grok-4.7-xhigh` for a seat
   whose recorded effort is `medium` (the spec would be false evidence).
5. **Clean-worktree verifier keeps record schema v1.** Checks run in a temporary worktree at
   the receipt's commit; the live tree is no longer compared; `PURRFECT_LIVE_ROOT` is exported
   for checks that need machine-local state (F007's evidence lives under `.tasks/`). Numbered
   records are a separate task (T-012) so each guard change gets its own review.
6. **Seat limits:** only allow-list write limits are decidable by `dispatch_policy.py`;
   login-state limits stay a routing rule. Rejected: parsing worker check prose.
7. **Codex `.agents/` question is answered by a direct probe (P-1) before any code,** like the
   F004 evidence. T-013 is dispatched only on a PASS.
8. **Carrier feature F007 for backlog tasks T-007, T-008, T-010, T-011, T-012.** Dispatch needs
   one pending feature; F001 is accepted. F007 is the closest (real smoke, reconstructable
   evidence, verify-mission on the smoke mission). These runs are slice evidence only; F007 is
   accepted only on T-038. T-009, T-013..T-017 are filed under F004 (adapter, registry,
   dispatch policy).
9. **Request item 6 correction:** the billing-class, `no_zdr` and `priority` negatives already
   exist (`test_registry_type_and_legacy_name_guards`). The real gaps are unchecked fields
   (encodings, capabilities, seat specs, fallbacks); T-017 covers those.
10. **Ledger write failure never changes a run's outcome** (WARN only); the receipt is the
    primary evidence. Drift events are folded with the ledger so they reach Git ("never
    silently").
11. **F006 validator is dependency-free** (`jsonschema` is not installed); it refuses schema
    keywords it does not implement, so it cannot pass a schema it does not understand.

## Owner decisions (morning report)

1. **`cursor.premium` is internally inconsistent:** frozen model `grok-4.7-xhigh`, frozen
   effort `medium`. Under contract 4 it is refused before launch. Options: (a) re-freeze the
   seat as `grok-4.7-medium` / `medium`; (b) re-freeze as `grok-4.7-xhigh` / `xhigh`; (c) leave
   it unusable until fleet v2. A fleet change is an owner-approved re-freeze (or a drift
   event once F004 lands). Until then only `cursor.economy` (Composer) is usable on Cursor.
2. **`agy.economy` has the same pattern:** `gemini-3.8-flash-high` with effort `medium`, and
   the adapter sends both `--model gemini-3.8-flash-high` and `--effort medium`. S1 shows
   whether agy accepts that; if not, the same three options apply.
3. The carrier-feature mapping above (decision 8): accept, or name another feature.
4. A-1 (brain move) and A-2 (parallel dispatch) need approval when written.
