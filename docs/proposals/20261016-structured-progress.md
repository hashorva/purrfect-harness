---
title: Structured progress (progress.jsonl, progress.py, generated PROGRESS.md)
status: proposal
author: Architect (Opus brain run a6f4e954-7bc6-4100-8a1a-06d09edd4d21)
date: 2026-10-16
decides: owner (start of 2B, or pulled into 2A)
---

# Structured progress

## Problem, with evidence from Mission 2A

- PROGRESS.md grew to 717 KB in two days and had to be archived as-is
  (`progress-archive/2026-10-14_15.md`). One more day added a 29 KB archive.
  Agents read prose to find out what is true, and the truth is in receipts and records.
- The Front Desk wrote four tools by hand to cope: `.tasks/note.py` (adds an
  entry of at most 10 lines), `.tasks/compact.py` (splits `=== FILE:` blocks,
  moves long entries to `reviews/entry-<sha8>.md`, archives all but 8 entries),
  `.tasks/route.py` (one routing row from receipt, spec and fleet) and
  `.tasks/rule6.py`. There are 36 files in `reviews/`. The `entry-<sha8>` names
  say nothing about the feature, task or run they belong to.
- `routing-data.jsonl` (81 rows) is already structured. It is written by hand and
  repeats fields that the ledger (`docs/missions/ledger.jsonl`, `scripts/ledger.py`)
  already validates with privacy rules.
- The brain review's only write scope is PROGRESS.md (`scripts/dispatch_policy.py:269`).
  So every Architect deliverable passes through PROGRESS.md as a `=== FILE:` block,
  and the Front Desk copies it out.

## Design

**`<mission>/progress.jsonl`**: append-only, one canonical JSON line per event.
Schema `schemas/progress-event.schema.json`, validated in the same subset style as `ledger.py`:

| Field | Rule |
| --- | --- |
| `schema_version` | `1` |
| `seq`, `at` | sequence number and UTC time; both set by `progress.py`, never by the caller |
| `type` | `run`, `verify`, `review`, `decision`, `amendment`, `lesson`, `gate`, `oracle`, `note` |
| `status` | enum per type: run `dispatched/completed/failed`; verify/review/oracle `pass/fail`; decision `open/decided`; gate `approved/rejected`; lesson `candidate/promoted/retired` |
| `feature`, `task`, `run_id` | `F\d{3}` / `T-\d{3}(-R\d+)?` / canonical UUID, each nullable. `run_id` is required for run, verify and review, and must have a receipt (the receipt decides attribution) |
| `summary` | one line, at most 300 characters, checked with the ledger privacy rules (no absolute paths, no secrets) |
| `link` | repo-relative path that must exist (`reviews/…`, `verification/…`, `evidence/…`), or null |
| `by` | `front-desk`, `brain`, `architect`, `orchestrator`, `human` (a gate is recorded by the orchestrator with `by: human`) |
| `supersedes`, `category` | optional: the `seq` that a decision or lesson replaces; the category a lesson applies to |

Events are never edited. A correction is a new event with `supersedes`. The prose
(review findings, decision reasons, lesson text) stays in linked files under
`reviews/`, named `<run-id>.md` or `<seq>-<slug>.md`.

**`scripts/progress.py`**:

- `add`: the only writer. It validates the event, checks that the run exists and
  that the link exists, takes the workspace lock, appends one line and then
  renders PROGRESS.md.
- `render [--check]`: builds PROGRESS.md from features.json and the events.
  It is deterministic and has five parts: a "generated, do not edit" banner,
  a feature table (passes, accepted run, last event), open decisions (not
  superseded), active lessons, and the last 15 events. `--check` exits 1 when
  the file differs.
- `brief --task T-xxx`: prints a bounded brief of at most 8 KB. It holds the task
  file, the events for its feature and for the features named in a new
  `Depends on:` line of the task template, the last 5 events, and the active
  lessons whose `category` matches the feature's `category`. It is the read path
  for workers, the brain and the 2B loop driver.

**Wiring:**

- The brain review write scope becomes `progress.jsonl`, `PROGRESS.md` and
  `reviews/<run_id>*.md`.
- `spawn-brain.sh` changes "Append PROGRESS.md" to "record with `progress.py add`".
- `verify-mission.sh` runs `render --check`, so a hand-edited PROGRESS.md blocks a gate.
- mission-init creates `progress.jsonl`.
- In ORCHESTRATION, the Human GATE entry becomes a `gate` event.

**Migration:** the existing PROGRESS.md and its archives are frozen, verbatim, as
`progress-archive/`. One `note` event links to them. No history is converted.

**Not in scope:**

- Deriving `routing-data.jsonl` from the ledger. That belongs to 2B F002 (lane
  choice from the ledger) and is noted there.
- A board view. 2B F006 reads `progress.jsonl`.

## 2A or 2B: recommendation, start of 2B

Make it the first 2B feature, ahead of F002 (loop driver), F006 (board) and
F008 (lessons intake), which all consume it. Reasons not to pull it into 2A:

1. 2A is two amendments (F004 and F007) away from Gate 1.
2. Adding a feature needs a features.json amendment.
3. The wiring task changes a guard (the brain write scope), so it needs an Opus
   review in the middle of a mission.
4. The hand tools are good enough for the remaining 2A tasks.

Pull it into 2A only if the owner wants the 2A close-out (Gate 1 and Gate 2)
recorded as events.

## Tasks (owner rule 6: each oracle fails on the base and passes after a scripted reference edit)

| Task | Size | Oracle |
| --- | --- | --- |
| P1 schema and `validate` | S | `tests/test-progress.py`: committed valid rows pass. One hostile row per rule fails and names the field path: absolute path, secret, bad UUID, unknown type, wrong status for the type, multi-line summary, missing link, run without a receipt. Fails on the base because the script does not exist. |
| P2 `add` and `render --check` | M | In a temp clone fixture mission, 3 `add` calls give a PROGRESS.md that is byte-identical to a committed golden file. One hand edit makes `render --check` exit 1. `add` with an unknown run_id exits 2. A mutant that skips the lock or the validation is killed. |
| P3 `brief` | S | Golden brief for a fixture task: it includes the dependency feature's events, leaves out unrelated features, includes only lessons of the matching category, and stays at most 8 KB. |
| P4 wiring (guard, Opus review) | M | The brain-review write-scope assertion in `tests/test-execution-integration.py` changes to the new list. A fixture mission with a hand-edited PROGRESS.md makes `verify-mission.sh` exit non-zero. Wired into `tests/run-tests.sh`. |

Total: 2 S + 2 M, plus the S rule-6 tool (see `reviews/a6f4e954-…-rule6.md`), which is best done first.
