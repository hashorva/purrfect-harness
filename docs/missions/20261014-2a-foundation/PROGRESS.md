---
note: Append-only. Newest entry on top. One entry per worker session or human gate.
---

# Progress

## 2026-10-14 — Worker (claude.economy, haiku) — T-001-R2 guard mutation compiles

- **Task:** T-001-R2 (F001), attempt 1 of 2. Run id not supplied in the task; no receipt written by this worker.
- **Changed (tests/test-verification-record.py only):** `snapshot-pre-post` replacement is now `'if False: pass\n'`; the mutation oracle also rejects `IndentationError` and `TabError` with the same message style as `SyntaxError`.
- **Baseline (before edit):** `shellcheck scripts/*.sh tests/*.sh` exit 0; `harness-manifest.json` JSON exit 0; `features.json` JSON exit 0; `python3 tests/test-fleet-state.py` exit 0.
- **Checks after edit:**
  - `GUARD_MUTATION_LABEL=snapshot-pre-post python3 tests/test-verification-record.py` (PYTHONDONTWRITEBYTECODE=1): exit 0, 12 tests OK. The label filter limits only the mutation loop; the file's other tests also ran.
  - `python3 tests/test-verification-record.py` (PYTHONDONTWRITEBYTECODE=1): exit 0, 12 tests OK; all 8 mutations pass their oracle.
  - `bash tests/run-tests.sh` (run once): exit 0, "ALL TESTS PASSED".
  - `test -z "$(git status --short)"`: exit 1 before commit, because the scoped test change was still uncommitted. Re-checked after the commit (see below).
- **Not reproduced:** I did not re-run the pre-fix tree to watch `snapshot-pre-post` fail with `IndentationError`; the diagnosis comes from T-001-R2. The new oracle would reject that output, and the passing full guard run shows the repaired mutation fails with `AssertionError`.
- **Not done:** no feature accepted, no `features.json` or `fleet.json` edit, no gate or status change, no other worker or brain launched.

## 2026-10-14 — Front Desk (Sonnet 5.5) — Architect plan received; tasks committed

- **Plan receipt:** run `b031098e-63f8-42da-ac88-ad4286429cb4`, receipt `.tasks/receipts/b031098e-63f8-42da-ac88-ad4286429cb4.json`: outcome `completed`, exit 0, scope pass, commit `380eab2` (PROGRESS.md only, as its write scope allows). `Plan: READY`.
- **Done:** copied the Architect's five drafts unchanged from `.tasks/plans/b031098e-63f8-42da-ac88-ad4286429cb4/` to `tasks/` (T-001-R2, T-002, T-003, T-004, T-005). Mechanical checks only: frontmatter task_id/feature/worker present, no `{{` left, none lists `features.json` or `fleet.json` in its allow-list.
- **Design decisions (a)-(e) in the Architect's entry:** treated as Architect decisions inside the owner's brief; none needs a file outside a task's allow-list. The owner may still overrule them; flagged in the next report.
- **Dispatch order:** T-001-R2 (claude.economy, haiku), T-002 (codex.premium), T-003 (codex.economy), T-004 (codex.economy), T-005 (cursor.economy; dispatch as `cursor` only after T-003 is accepted-by-review). Then one Architect review of T-001-R2, T-002 and T-003 together (Architect run 4 of 4).
- **Budget counters:** worker runs 3 of 12 so far; Architect 3 of 4 (this plan). The 5 planned tasks bring workers to 8 of 12.
- **L-005 candidate:** a task that adds a test file also adds it to `tests/run-tests.sh`; "suite passed" proves nothing about a test the suite does not run.

## 2026-10-14 — Brain / Architect (claude/opus, effort high) — F001 task plan

- **Run:** `b031098e-63f8-42da-ac88-ad4286429cb4`; log `.tasks/logs/b031098e-63f8-42da-ac88-ad4286429cb4.log`; spec role `brain`, action `review`, base `7898d88`. The launcher writes the receipt `.tasks/receipts/b031098e-63f8-42da-ac88-ad4286429cb4.json` when this run ends; it did not exist while this entry was written. This is Architect run 3 of 4 tonight.
- **Where the tasks are:** a `review` brain run may write only this file (spec `write_scope`), so committing `tasks/T-*.md` here would fail the scope check. The five task files are complete drafts in `.tasks/plans/b031098e-63f8-42da-ac88-ad4286429cb4/` (gitignored, machine-local). Each one parses with the real `dispatch_policy.worker_write_scope` and the verifier's command-bullet rules, with no `{{` left. **Front Desk:** copy them unchanged to `tasks/` and commit them in one commit before the first dispatch.
- **Ordered plan (one feature, F001; dispatch in this order):**
  1. `T-001-R2`, `claude.economy` (haiku, medium, unknown). `tests/test-verification-record.py` only: replacement `'if False: pass\n'`; oracle also rejects `IndentationError`/`TabError`. **Architect review.**
  2. `T-002`, `codex.premium` (terra, medium, unknown). `fleet_state.py` loads `PROVIDERS`/`CAPABILITIES`/`SEAT_SPECS`/`EXECUTABLES` from the registry; golden parity test (old constants copied from `1345c67` into the test); registry type/enum negative tests; fail-closed when the registry is missing; fixture copies get the registry; `test-registry.py` joins `run-tests.sh`. **Architect review.**
  3. `T-003`, `codex.economy` (luna, medium, unknown). `spawn-worker.sh`/`spawn-brain.sh` accept `cursor` and convert it once to the persisted name `agent` through `harness_registry.py persisted-name`; specs stay identical. **Architect review.**
  4. `T-004`, `codex.economy`. `fleet-doctor.sh` + `fleet_doctor.py`, registry fields `identity_pattern` and `login_check`, fixture test, manifest ownership. **`code-reviewer`.**
  5. `T-005`, `cursor.economy` (composer-2.5, medium, standard; dispatch as `cursor` after T-003). The skills and `MODEL_ROUTING.md` docs edits. Its verification commands cover F001 steps 1-8, so **F001 is accepted on T-005's run only**. **`code-reviewer`.**
- **One Architect review for all guard code:** after T-001-R2, T-002 and T-003 are each verified (`verify-mission.sh --run-id`), one `spawn-brain.sh ... review` reviews all three commits. That is Architect run 4, the last one tonight. It may run before or after T-004. It must PASS before F001 acceptance. Budget after the plan: worker runs 8 of 12, Architect 4 of 4. A guard FAIL therefore waits for the next night's Architect budget.
- **Design decisions in the tasks (owner may overrule before dispatch):**
  - (a) Persisted data keeps `agent`: frozen `fleet.json` (read-only, cursor seats say `agent`), inventory v1 and ExecutionSpec v3. `fleet_state.py` reads a *legacy view* of the registry (`cursor` → `agent`). F004 (fleet v2) moves persisted data to canonical names. This touches the least guard code and keeps all evidence valid byte for byte.
  - (b) `execution_spec.PROVIDERS` stays as it is. It is the frozen v1-v3 evidence schema, and old evidence must not depend on mutable registry data. F001 step 2's grep does not match it (`frozenset(`), and `dispatch_policy.py` needs no change (it imports `CAPABILITIES` from `fleet_state`).
  - (c) The doctor checks registry `binary` names only, never legacy names. Evidence from this run: `agent` on PATH resolves to two different programs (`~/.grok/bin/agent` → `grok-1.0.52`, `~/.local/bin/agent` → `cursor-agent 2026.10.14-0f9edde`). Checking `agent` would ERROR and break F001 step 5.
  - (d) Identity patterns come from `--version` outputs recorded in this run: `2.1.299 (Claude Code)`, `codex-cli 0.162.0`, `2026.10.14-0f9edde`, `1.3.5`, and Grok `grok 1.0.52 (0920c8169e27) [stable]` as the negative case. Login checks are non-billable and come from each CLI's own `--help`: `claude auth status`, `codex login status`, `cursor-agent status` (all exit 0 here), and `agy models` (agy has no status command). Doctor output never includes login output, because `cursor-agent status` prints the account email. **Not proven:** each vendor CLI's exit code when logged out; nobody could log out to test it. The fixtures prove only the doctor's logic.
  - (e) "Symlinks are WARN" is read as: several PATH hits that resolve to the same real file. A single symlink hit is fine (most of these CLIs are symlinks). In this run's PATH none of the four binaries had duplicates, so WARN depends on the caller's PATH. The real-Mac check requires only exit 0; the fixtures prove WARN.
- **Found while planning:** (1) `tests/test-registry.py` is not in `tests/run-tests.sh` (the suite lists tests one by one), so T-001's "full suite exit 0" never ran it; T-002 adds it. (2) `tests/test-execution-integration.py` (fixed script list) and the guard-mutation temp copy in `tests/test-verification-record.py` do not copy `harness-registry.json`; T-002 fixes both in the same change that creates the dependency.
- **L-005 candidate:** a task that adds a test file also adds it to `tests/run-tests.sh`; "suite passed" proves nothing about a test the suite does not run.
- **Audit:** `bash scripts/verify-mission.sh docs/missions/20261014-2a-foundation` → `VERIFY OK`, exit 0, before this entry.
- **Not done:** no worker dispatched, no `accept-feature.sh`, no change to features.json, fleet.json, gate or status. No CLI was run beyond `--version`, `--help`, the three status commands and `agy models`.

Plan: READY

## 2026-10-14 — Front Desk (Sonnet 5.5) — T-001 attempt 2 reviewed and verified; Architect planning requested

- **Mechanical review:** run `3495b35c-2b2a-4ccf-b8c3-38ba47274430`, receipt `.tasks/receipts/3495b35c-2b2a-4ccf-b8c3-38ba47274430.json`: outcome `completed`, exit 0, scope pass, commit `1345c67`, 5 changed paths all in the allow-list. `verify-mission.sh --run-id 3495b35c-2b2a-4ccf-b8c3-38ba47274430` → `VERIFY PASS`, exit 0. Record `verification/3495b35c-2b2a-4ccf-b8c3-38ba47274430.json` is **slice evidence for F001 (T-001), not F001 acceptance**.
- **Code review (routine diff, `code-reviewer` subagent, read-only):** Verdict PASS. Registry equals the old constants (`cursor` for `agent`), every required field present, loader rejects each missing field, one negative test per field, no `grok` provider, `cursor-agent` binary with `agent` as legacy name only, no blocking issues. Limit it stated: it could not run `git diff`; the commit stat and receipt scope cover the untouched-files check. Non-blocking note: the loader's type/enum checks (billing class, `no_zdr`, `priority`) have no negative tests.
- **Budget counters (night of 2026-10-14; owner caps 12 worker, 4 Architect):** worker runs 3 (T-001 a1, T-001-R1, T-001 a2); Architect runs 2 (mission-init, R1 review). This entry requests Architect run 3. One Architect run would remain. No credits, no fast modes used.
- **ARCHITECT REQUEST (planning, action `review`):** F001 has only its first slice done (registry data, loader, parity test; nothing consumes it yet). Write the remaining F001 tasks as committed files under `tasks/` (T-002, T-003, ...), in dispatch order. Each task: one small change an economy worker can finish, its own allow-list and deny-list, JSON-argv verification commands, the long-command rule in its Iteration policy, and a "why" line for each check. Cover F001 steps 2-8: move the consumers of PROGRESS-listed constants to the registry (`PROVIDERS`, `CAPABILITIES`, `SEAT_SPECS`; FALLBACKS stays until F004), rename provider `agent` to `cursor` with `agent` as a legacy name so v3 evidence validates, `scripts/fleet-doctor.sh` (WARN vs ERROR rules in F001) with fixtures, and the mission-init and dispatch-worker skill edits. Also write `T-001-R2` (queued repair from the previous review, `tests/test-verification-record.py` only). Because only one Architect run remains tonight, put the guard-touching changes (`dispatch_policy.py`, `execution_spec.py`, `fleet_state.py`, verification code) into as few tasks as the design allows, and say which tasks need Architect review and which can go to the `code-reviewer`. Do not change `features.json`, `fleet.json` or the status; do not dispatch workers. End with the ordered task list and `Plan: READY` or `Plan: BLOCKED` with the blocking design question.

## 2026-10-14 — T-001 attempt 2 worker — registry slice complete

- **Baseline:** `shellcheck scripts/*.sh tests/*.sh`, manifest/features JSON validation, and `python3 tests/test-fleet-state.py` all exit 0.
- **Changed:** added manifest-owned `harness-registry.json` with provider, door, seat and fallback data; added `scripts/harness_registry.py` loader with field-level validation and clear errors; added parity, missing-field and legacy-name tests in `tests/test-registry.py`. `cursor` is the provider key and `agent` is listed only as its legacy name. Added registry and loader paths to manifest install/update ownership lists.
- **Checks:** registry/manifest JSON validation exit 0; `env PYTHONDONTWRITEBYTECODE=1 python3 tests/test-registry.py` exit 0 (3 tests); shellcheck exit 0; `git diff --check` exit 0; `bash tests/run-tests.sh` exit 0 (`ALL TESTS PASSED`).
- **Scope/state:** only task allow-listed files changed. `scripts/fleet_state.py` remains untouched; no feature acceptance or mission gate/status change made.
- **Commit:** `feat(registry): add harness-registry.json, loader and parity test`.

## 2026-10-14 — Front Desk (Sonnet 5.5) — Architect review recorded; T-001 attempt 2 dispatch

- **Architect review of `68942df`:** run `127dd9c6-faa4-4bb3-9a70-0897226ea49a`, receipt `.tasks/receipts/127dd9c6-faa4-4bb3-9a70-0897226ea49a.json` (outcome `completed`, exit 0, scope pass, commit `5dec815`). **Verdict: PASS** on all three points: all 8 mutations still applied, each still makes its focused test fail, nothing in the live tree is written. `bash scripts/verify-mission.sh docs/missions/20261014-2a-foundation` exit 0.
- **Finding queued (pre-existing, not R1, not blocking):** the `snapshot-pre-post` mutation leaves `verification_record.py` uncompilable (`IndentationError`), so its proof is vacuous; the oracle rejects `SyntaxError` but not `IndentationError`. Proposed small repair, `tests/test-verification-record.py` only: replacement `'if False: pass\n'` and an oracle that rejects `IndentationError`/`TabError`. Guard test, so it needs Architect review. Not dispatched yet; queued as `T-001-R2` after T-001.
- **T-001 updated for attempt 2 (owner-approved):** baseline = shellcheck, JSON validation, `python3 tests/test-fleet-state.py`; `python3 tests/test-registry.py` is a task check (verification commands); the full suite stays in the verification commands; the long-command rule is in the Iteration policy.
- **Next:** dispatch T-001 attempt 2 on `codex.economy`.

## 2026-10-14 — Brain / Architect (claude/opus, effort high) — review of T-001-R1 (`68942df`)

- **Run:** `127dd9c6-faa4-4bb3-9a70-0897226ea49a`; log `.tasks/logs/127dd9c6-faa4-4bb3-9a70-0897226ea49a.log`; spec role `brain`, `claude`/`opus`, effort `high`. The launcher writes the receipt `.tasks/receipts/127dd9c6-faa4-4bb3-9a70-0897226ea49a.json` when this run ends; it did not exist while this entry was written.
- **Receipt `8d4ec44c…` (re-checked):** outcome `completed`, exit 0, `workspace_changed: true`, scope `pass`, no violations; base `15d9de6` → commit `68942df`; changed paths = the three allow-listed files. VerificationRecord `8d4ec44c….json` result `pass` at `68942df`.
- **(1) Every original mutation is still applied — confirmed.** The `mutations` tuple at `68942df` is byte-identical to `15d9de6` (`diff` of the tuple block: no output). Same 8 labels: task-at-base, spec-hash, receipt-hash, identity-rebind, snapshot-rebind, snapshot-pre-post, lock, acceptance-hash. The loop, `GUARD_MUTATION_LABEL` filter and oracle (`AssertionError` required; `NameError`/`SyntaxError`/`\nERROR` rejected) are unchanged; only the mutated file's root and the sub-run `cwd` moved to the temp copy.
- **(2) Each mutation still breaks its focused test — confirmed, same as before.** I ran the guard test from `git archive` exports of `15d9de6` and `68942df` (scratch only, live tree untouched) with a wrapper that logged each focused sub-run. Both: test OK, 8/8 sub-runs exit 1, same target, same failing subtest labels, and the same `AssertionError` once run UUIDs and temp paths are normalized. New sub-runs ran in `…/T/verification-guard-mutation-*`. Non-vacuity baseline: the 5 unmutated focused targets pass from a temp copy of the same 4 directories (exit 0, 5 tests), so the copy is complete.
- **(3) The test writes nothing in the live tree — confirmed.** Ran the whole `tests/test-verification-record.py` (12 tests, exit 0) in this checkout while a watcher hashed `git status` and every file under `scripts/ tests/ schemas/ docs/missions/templates` every 50 ms: zero changes; before/after snapshots equal; `git status --short` empty; no `verification-guard-mutation-*` temp directory left. The rest of `tests/` grep-checked for live-tree writes: one hit (`tests/test-fleet-state.py:128`), which is a false positive (writes a temp-dir `fleet`).
- **Template:** the long-command rule is in the Iteration policy; `ShippedWorkerTemplateIntegration` passed in the 12-test run.
- **Finding (pre-existing at `15d9de6`, not caused by R1; does not block it):** the `snapshot-pre-post` mutation replaces a guard line with a bare `if False:\n`, so the mutated `verification_record.py` does not compile (`IndentationError`, line 179). The focused test fails because the script will not load, not because the guard is removed. The oracle misses this: it rejects `SyntaxError`, but the printed name is `IndentationError`. Probe with a compiling mutation (`if False: pass\n`): the focused test fails correctly (`AssertionError: 0 == 0 : VERIFY PASS`), so the guard *is* mounted; only this label's proof is vacuous. Proposed bounded fix (separate task, `tests/test-verification-record.py` only): use `'if False: pass\n'` as that replacement, and make the oracle also reject `IndentationError`/`TabError` (or reject any traceback from the mutated script).
- **Audit:** `bash scripts/verify-mission.sh docs/missions/20261014-2a-foundation` → `VERIFY OK`, exit 0, before this entry.
- **Not done:** no `accept-feature.sh` (R1 is F001 slice evidence, not F001 completion); no features.json, fleet, gate or status change; no worker dispatched.
- **Next:** dispatch T-001 attempt 2 per the Front Desk plan. The snapshot-pre-post fix can be a small `claude.economy` / `codex.economy` task before or after it.
- **L-004 candidate:** a guard-mutation oracle must reject every compile error (`SyntaxError` and its subclasses), not only one name.

Verdict: PASS

## 2026-10-14 — Front Desk (Sonnet 5.5) — T-001-R1 reviewed and verified; Architect review requested

- **Mechanical review (receipt, scope, exit codes, verifier only):** run `8d4ec44c-791c-45a5-b672-8e1454c89a32`, receipt `.tasks/receipts/8d4ec44c-791c-45a5-b672-8e1454c89a32.json`: outcome `completed`, exit 0, scope pass, commit `68942df`, changed paths all in the allow-list. `bash scripts/verify-mission.sh --run-id 8d4ec44c-791c-45a5-b672-8e1454c89a32 docs/missions/20261014-2a-foundation` → `VERIFY PASS`, exit 0.
- **Record:** `verification/8d4ec44c-791c-45a5-b672-8e1454c89a32.json` is **slice evidence for F001 (T-001-R1), not F001 acceptance**. F001 is accepted only on the run that completes it, after a current `verify-mission.sh`. No `accept-feature.sh` was run.
- **Roles for the rest of 2A (owner):** Front Desk review is mechanical only. Routine diffs go to the `code-reviewer` subagent. Guards, safety tests, verification/acceptance/dispatch code, or any diff the Front Desk is unsure about go to the Architect via `spawn-brain.sh ... review`.
- **REVIEW REQUEST for the Architect (commit `68942df`, changes the guard-mutation test in `tests/test-verification-record.py`):** run `git show 68942df`. Confirm, with evidence: (1) every original mutation (labels in the `mutations` tuple) is still applied; (2) each mutation still makes the focused test fail (compare against the pre-change file at `15d9de6`); (3) nothing in the live tree is written by the test (check `git status --short` and file hashes of `scripts/` before and after a run). End your PROGRESS entry with the line `Verdict: PASS` or `Verdict: FAIL`, and list your evidence.

## 2026-10-14 — T-001-R1 worker — complete; awaiting orchestrator verification

- **Checked:** every `tests/test-*.py` file and `tests/run-tests.sh` for filesystem writes, copies, deletes and permission changes. The integration tests' mutations target their temporary fixture repositories; `tests/test-verification-record.py` was the live-tree writer. Its guard mutation now runs against a temporary copy of `scripts/`, `tests/`, `schemas/` and `docs/missions/templates/`, removed by `TemporaryDirectory` even on failure. No other live-tree writes were found.
- **Changed:** `tests/test-verification-record.py` to isolate the guard mutation while preserving the real focused test entry-point assertion; `docs/missions/templates/WORKER_TASK.template.md` to include the required long-command rule in Iteration policy.
- **Baseline:** shellcheck, manifest/features JSON validation and `python3 tests/test-fleet-state.py` all exit 0.
- **Checks:** `python3 tests/test-verification-record.py` exit 0 (12 tests); two concurrent copies of each `tests/test-*.py` completed without failure; `bash tests/run-tests.sh` exit 0 (`ALL TESTS PASSED`). The shipped template rendered and verified through the full suite. `git diff --check` exit 0. The test runs left no changes beyond the two intended files before this progress entry.
- **Result:** no feature acceptance or mission gate/status change. Scoped change and this entry committed as `test: mutate a temporary copy, never the live tree`.

## 2026-10-14 — T-001 worker — blocked at baseline

- **Did:** read the task, mission instructions, newest progress, features, fleet-state constants and manifest; inspected `git log --oneline -10`.
- **Baseline:** `bash tests/run-tests.sh` exit 1 before any implementation edits. The failing check reported `VerificationRecord and acceptance real-entry contracts`; remaining output was truncated by the command tool, so no further failure detail is available.
- **Result:** stopped as required by T-001's pre-code baseline rule. No registry files, manifest ownership, or acceptance/gate state changed. Retry requires baseline repair and redispatch.

## 2026-10-14 — Front Desk (Sonnet 5.5) — T-001 attempt 1 diagnosed; T-001-R1 written

- **Diagnosis (proven):** not a sandbox limit. The suite passes under `codex sandbox -P :workspace` (test file 12/12 in 68s, full suite 149s). The worker started a second copy of the suite while the first was still running; `tests/test-verification-record.py` (line 285) edits the live `scripts/verification_record.py` to mutate guards, so the concurrent copy saw a broken guard. Reproduced: two concurrent copies, one fails with 3 failures, first at `test_required_guard_mutations_break_the_real_focused_entry_and_restore`, `AssertionError ... not found` at line 320. Tree clean afterwards.
- **Owner-approved fix:** T-001-R1 (feature F001, `codex.economy`): grep all tests for live-tree writes, make mutations happen in a temporary copy, add the long-command rule to the worker template's Iteration policy. Checks: two concurrent copies of every `tests/test-*.py` exit 0; `git status --short` empty; `bash tests/run-tests.sh` exit 0 (once).
- **T-001 attempt 2:** only after R1 is accepted. Its baseline becomes shellcheck, JSON validation and `python3 tests/test-fleet-state.py`; `python3 tests/test-registry.py` is a T-001 check, not a baseline; the full suite stays in its verification commands. T-001 text is updated then.
- **L-002 candidate:** run a long check once; never launch a duplicate while it runs. (Replaces the earlier sandbox guess; no L-002 text was ever written to this file.)
- **L-003 candidate:** tests must never mutate the live tree; mutate a temp copy.

## 2026-10-14 — Front Desk (Sonnet 5.5) — status in-progress

- **Did:** moved `approved` → `in-progress`. `verify-mission.sh` exit 0 on the in-progress mission. Dispatching T-001 (F001, codex.economy, attempt 1) next.

## 2026-10-14 — Front Desk (Sonnet 5.5) — fleet frozen, status approved

- **Fleet:** `fleet.json` frozen from the inventory probed 2026-10-14T15:00:44Z, approved by Zamir at 2026-10-14T15:25:56Z. `validate-fleet` exit 0. No re-probe between approval and freeze.
- **Seats:** brain = claude / opus (alias), effort high. cursor.premium = grok-4.7-xhigh; cursor.economy = composer-2.5 (effort medium, speed standard). codex.premium = gpt-5.6-terra; codex.economy = gpt-6-luna. agy.economy = gemini-3.8-flash-high. claude.premium = sonnet; claude.economy = haiku (alias, effort medium). Not bound: agy.premium (unavailable), brain_codex, brain_fable.
- **Brain evidence:** run `ec402a2f-6830-425a-b932-88332b044933`, receipt `.tasks/receipts/ec402a2f-6830-425a-b932-88332b044933.json`; `verify-mission.sh` exit 0 before this entry.
- **Status:** `approved`.

## 2026-10-14 — Human — GATE 0 (chair option 2)

- **Verdict:** option 2 approved: freeze now with the brain on `claude` / `opus`, effort high.
- **Chair intent:** Opus via agy (Google AI Pro pool). Interim: Opus via claude, because the v3 brain seat cannot carry an agy model. Switch to agy Opus when F001 (registry lets agy carry an Opus seat) and F004 (logged mid-mission change) are both accepted; the switch is a logged drift event, not a fleet rewrite.
- **Change:** F004 gets the step "the chair seat can resolve to agy claude-opus-5-5-high, and the change is logged as a drift event." (draft-stage edit, before freeze).
- **Assumption (Front Desk):** worker seats frozen at effort `medium`, as in Phase 1; speed `standard` for cursor, `unknown` elsewhere. Say so if you want other values before dispatch beyond T-001.

## 2026-10-14 — Human — GATE 0

- **Verdict:** approved with changes (recorded by Front Desk from the owner's message).
- **Scope:** F002 (Grok Build provider) removed; ids not renumbered. Grok runs through `cursor-agent`. F007 smoke uses claude, codex, cursor-agent (Composer and Grok) and agy. Dependent steps in F001, F003, F004, F005, F007 were aligned in the same draft-stage edit.
- **Findings recorded:** `cursor-agent` JSON gives usage and `session_id` but no model, so observed model is `unknown` unless stream-json init reports it. Grok Build headless: `acceptEdits` cancelled both file and shell tool calls. Deferred experiment X-GROK: Grok via `grok` against via `cursor-agent`, measured in the ledger on spare quota.
- **Decisions:** (1) chair Opus 5.5, effort high, via `agy` model `claude-opus-5-5-high`; fall back to `claude` / `opus` only if the first agy brain run fails to launch, and record why. (2) Frozen-fleet amendment approved: a probe may change an active mission, never silently. (3) Phase 1 non-goals lifted for Phase 2; 2A uses none. (4) Budgets: per spawn 40 min; per night max 12 worker + 4 Architect runs; per pool stop at an estimated 80% of a 5-hour window or 70% of the weekly cap; never credits, never fast modes.
- **Architect questions:** (1) each run writes `.tasks/ledger/<run_id>.json` (gitignored); the orchestrator folds rows into `docs/missions/ledger.jsonl` in each acceptance commit and at gates. (2) Terra premium, Luna economy; tier follows family, not version. (3) FALLBACKS copied unchanged in T-001, deleted in F004.
- **Approved:** T-001 on codex.economy (Luna).
- **Next:** blocked before freeze. The `brain` seat is fixed to `claude`/`opus` in `scripts/fleet_state.py` (`SEAT_SPECS`); `freeze` accepts only `brain`, `brain_codex` or `brain_fable` and checks provider/family match. An `agy` Opus brain cannot be frozen with the current code. Status stays `draft` until the owner decides.

## 2026-10-14 — Brain (claude/opus, effort high) — mission-init

- **Run:** `ec402a2f-6830-425a-b932-88332b044933`; log `.tasks/logs/ec402a2f-6830-425a-b932-88332b044933.log`. The launcher writes the receipt `.tasks/receipts/ec402a2f-6830-425a-b932-88332b044933.json` when this run ends; it did not exist while this entry was written.
- **Checked:** GOAL.md, features.json, PROGRESS.md and tasks/T-001.md exist, match the templates, and have no `{{` placeholders. GOAL status stays `draft`. `active-mission.sh` reports no active mission (exit 1, expected for a draft).
- **Baseline (base `cef58cc`):** `shellcheck scripts/*.sh tests/*.sh` exit 0; JSON validation of the manifest and features.json exit 0; `bash tests/run-tests.sh` exit 0.
- **Inventory:** no re-probe. `.tasks/fleet-inventory.json` (probed 2026-10-14T15:00:44Z) matches the GOAL Fleet table seat for seat. `grok` is on PATH but not in the inventory (F002).
- **Architect edits (features.json, ids and scope unchanged, all `passes:false`/`bootstrap:false`):** made these steps checkable by a command: F001 step 2 (grep for literal definitions, not names that `dispatch_policy.py` still imports), F001 step 5 (marked local-only, kept out of CI), F001 step 7 (exact greps), F002 step 5, F004 step 3 (drift write failure must fail the spawn), F007 step 5 (reconstruct command replaces "a human can rebuild"). Added an F005 step: a committed `ledger.jsonl` row must not break the clean-tree or snapshot-equality checks.
- **Open for Gate 0 (beyond the four proposal decisions):** (a) F005: where and when the ledger row is committed, because appending after a run dirties the tree that the next launch and `verify-mission.sh` require clean; (b) `codex.premium` binds `gpt-5.6-terra` while `codex.economy` binds the newer `gpt-6-luna`, so confirm or swap; (c) the `FALLBACKS` constant (`gpt-5.6-sol`, `cursor-grok-4.5-high`) is older than the observed models; T-001 copies it as-is for parity.
- **First task:** T-001 (F001 slice 1), proposed `codex.economy` (luna). T-001 was committed in `cef58cc`.
- **Not done:** no worker dispatched, no fleet.json frozen, no feature accepted, no status change.

## 2026-10-14 — Front Desk (Sonnet 5.5) — mission-init setup

- **Did:** Created branch `mission/2a-foundation`, committed the Phase 2 proposal (`8cf00ee`), checked the CLIs, ran `fleet-inventory.sh`, scaffolded this draft mission.
- **Step 2:** duplicate PATH entries only; all hits resolve to one binary per CLI (owner accepted).
- **L-001 candidate:** in prompts and tasks, state why a check exists, not only its rule.
- **Inventory:** seats and health are in the Gate 0 report and `GOAL.md`. `claude` seats are alias-sourced (0 models listed). `agy.premium` is unavailable. No `grok` provider yet (feature F002).
- **Blocked / handoff notes:** Architect run (brain) pending. Status stays `draft`. No worker dispatched.
