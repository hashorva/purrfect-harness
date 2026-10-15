# A-2: Pull parallel worktree dispatch forward from 2B?

Architect proposal, run `e60b00a8-9594-4352-928c-3b069d4593a1`, 2026-10-15. For the owner's decision.

**Recommendation: no. Keep parallel dispatch in 2B, and start 2B with the minimum slice in §5.**
In 2A, spend the effort where the data shows the time goes: fewer plan defects (§2).

## 1. What exists today (facts, with code locations)

- **One writer per repository.** `dispatch_policy.acquire_lock` refuses any workspace that is not
  the repository root ("cross-repository execution is disabled in Phase 1"). The lock is the
  directory `.tasks/locks/workspace-<sha256(path)>.lock` in the root. A linked worktree has a
  different path, so it is refused today. `spawn-brain.sh` takes the same lock, so an Architect
  review cannot overlap a worker either.
- **Acceptance is already serial.** `verification_record.py` (about lines 353–355) refuses acceptance while
  *any* lock directory exists. With two lanes, acceptance waits for a moment when no run holds a lock.
- **The verifier is already worktree-native (T-011).** It checks out the receipt's `git_after`
  head in a temporary detached worktree, requires the snapshots to be equal, and reads live state
  through `PURRFECT_LIVE_ROOT`. T-012 makes records numbered and immutable per run.
- **Every artifact is keyed by run UUID** (spec, log, receipt, VerificationRecord; the F005
  ledger row is planned the same way). `.tasks/` is gitignored, so a linked worktree has no
  `.tasks/`. All lanes must write to the root's `.tasks/`. UUID keys mean they cannot collide.
- **Scratch clones are proven (T-007/T-008 seat smoke):** a clone, a committed fixture mission, and
  a classification taken from the clone's receipt and Git state only.
- **Receipts re-walk history.** `execution_receipt.py` checks `merge-base --is-ancestor` and
  `rev-list base..after` when it loads a receipt. A worker's commits must stay reachable for
  ever, so a lane is merged with `--no-ff`, never squashed or rebased.
- **Codex in a worktree is broken as written.** The adapter passes `--add-dir <repo>/.git`
  (`execute_provider.py:27`). In a linked worktree `.git` is a file; the object store is the
  common dir (`git rev-parse --git-common-dir`). Codex commits would fail until this is fixed.
- **Tests can already run concurrently.** T-001-R1 moved the guard mutation into a temporary
  copy; two concurrent copies of every `tests/test-*.py` passed.

## 2. What the nightly data says

From `routing-data.jsonl` (17 worker rows) and the receipts of this mission:

| | claude.economy | codex.economy | cursor.economy | total |
|---|---|---|---|---|
| runs | 5 | 6 | 6 | 17 |
| done | 4 | 2 | 5 | 11 |
| verify-failed | 1 | 4 | 1 | 6 |
| model-attributable failures | 0 | 0 | 1 (T-015 a1) | 1 |

- **5 of the 6 failures are plan defects** (`attributable:false`: allow-list gaps, checks run in
  the wrong root, a check contradicting the task's own edit). Each one cost a qualification run
  and usually an Architect review. Codex took 4 of them: they were first attempts, not model faults.
- **Worker time is not the bottleneck.** Night 2 receipts (from 20:00Z): 21 worker runs, 78 min
  in total (median row 308 s, max 546 s); 14 Architect runs, 173 min; wall span 7.4 h. Workers
  use about **17%** of the night, the Architect about **39%**, and the Front Desk (mechanical
  review, verification, task text, probes) the rest. No two runs overlapped.
- **Parallelism is available on paper but rarely in order.** Of the 21 committed pending tasks
  (T-018…T-038), 160 of 210 pairs are file-disjoint (PROGRESS.md excluded), but most of them
  are chained by "Depends on" inside a feature. Hot files: `tests/run-tests.sh` (6 tasks),
  `tests/test-execution-integration.py` (6), `scripts/fleet_state.py` (5), `harness-manifest.json` (4).

**Upper bound of the gain:** two lanes overlap at most the worker share. That is about 40 min a
night at best, roughly 5–10% of the wall time, while review stays serial. Halving the
plan-defect rate saves more: each defect costs about one worker run plus one Architect review,
roughly 15–35 min.

## 3. Design, if built

- **Admission rule (refused before launch, like T-015's gate):** both tasks are committed; their
  allow-lists are disjoint, compared conservatively (two patterns overlap if either's literal
  prefix before the first glob character is a prefix of the other's); neither "Depends on" the
  other; different providers on different quota pools; no brain run is active. PROGRESS.md is the
  one shared path (below).
- **Locks:** one lock per worktree, keyed by its path as today, and the owner file records the
  task's allow-list so the second admission can compare. The rule "workspace must be the root"
  becomes "workspace is the root or a linked worktree with the same `--git-common-dir`".
  Brain runs keep an exclusive lock over everything.
- **Worktree:** `git worktree add -b wt/<run-id> .tasks/worktrees/<run-id> <base>` (gitignored).
  The spec records the workspace; spec, log and receipt go to the root's `.tasks/`. This needs
  a new ExecutionSpec version; v1–v3 evidence keeps its meaning.
- **Merge (orchestrator only, serial):** VERIFY PASS on the lane's run, then
  `git merge --no-ff wt/<run-id>` into the mission branch, in admission order. PROGRESS.md gets
  `merge=union` in `.gitattributes`, because two prepends at the top otherwise always conflict;
  the orchestrator checks that both entries are present. Any other conflict stops the merge: no
  automatic resolution, and the lane is re-dispatched on the new base. After each merge the full
  suite runs once on the merged HEAD, before acceptance. Acceptance still cites the lane's own
  VerificationRecord.
- **Quota and pause:** the owner's caps (12 worker + 4 Architect a night; stop a pool at an
  estimated 80% of its 5-hour window or 70% of the weekly cap) are counted per pool before each
  spawn. A paused pool stops its lane only; the other lane goes on. No silent move to another seat.

## 4. Risks

- **A worker writes outside its worktree.** The receipt only sees Git-visible changes in its own
  workspace. Mitigation: snapshot the root checkout and the other worktree before and after;
  refuse the merge if either changed.
- **Shared `~/` CLI state.** Two sessions of one CLI share its config, session and auth-refresh
  files. Mitigation: never the same provider twice in parallel.
- **Two Codex sandboxes.** Both would get write access to the shared object store and refs
  through the common-dir `--add-dir`, so one could move the other's branch. Mitigation: at most
  one Codex lane, and only after the common-dir fix.
- **Hot files.** `tests/run-tests.sh` blocks most pairs. Test discovery by glob instead of a
  fixed list would remove the most common overlap; that is a separate, cheap change.
- **More surface during a phase whose failures are mostly plan text.** Merge failures and
  admission refusals add new failure classes before the existing one is under control.

## 5. Recommended minimum slice (start of 2B)

Two disjoint tasks on two providers, one orchestrator merge: for example T-040 (docs) on
`claude.economy` and T-018 (parser) on `cursor.economy`. No Codex lane. Work: three guard tasks,
each reviewed by the Architect: (P1) admission and per-worktree locks; (P2) launcher worktree
mode and the new spec version; (P3) the merge script with `merge=union` and the post-merge suite.
Expected cost: about 3 Architect runs and 4–6 worker runs, which is one night's Architect budget.

**Checks that prove it:**
- the two receipts' `started_at`–`finished_at` intervals overlap;
- each receipt has scope `pass` in its own worktree;
- the root checkout's and the other worktree's snapshots are unchanged across both runs;
- both VerificationRecords pass;
- both merges are conflict-free and PROGRESS.md holds both entries;
- `bash tests/run-tests.sh` exits 0 on the merged HEAD;
- `verify-mission.sh --require-workers` exits 0 after both acceptances (receipts still re-walk);
- negatives, refused before any lock, spec or provider: overlapping allow-lists, a
  "Depends on" edge, the same provider twice, a Codex lane, and a brain run while a lane is active.

**Stays out:** more than two lanes; the same provider twice; Codex lanes; parallel Architect
runs; parallel acceptance; automatic conflict resolution; a scheduler or queue; `--repo` targets.

## 6. Decision for the owner

- **(A) Recommended:** keep parallel dispatch in 2B and start 2B with §5. In 2A, adopt one process
  rule: before committing a task, the planner runs its verification commands in a scratch clone.
  They must fail on the base, and pass after a scripted application of the intended edit
  (this run did this for T-040).
- **(B)** Pull §5 into 2A as a new feature appended to `features.json`, after F003 and F004 are
  accepted. Cost: about one night's Architect budget. Expected saving: under 10% of wall time.
