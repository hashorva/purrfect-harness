# T-037 revised: mutants and rule 6 (Architect run 204f6de4-89d4-4765-bf2c-d5ebd7462fa3, 2026-10-16)

Base: 7db9588. Reference patch (outside the repo): scratchpad `T-037-reference.patch`,
sha256 `50fec78170ed1ba232d41f551fe91a8eb66e52e1db1cb3dc8ff81de873f9f60f`
(`scripts/seat_smoke.py` +81/-10, `tests/test-seat-smoke.py` +70).

## Rule 6 (scratch clones, base vs. patch committed)

| # | command | base | after |
| - | ------- | ---- | ----- |
| 1 | five named F007 tests | 1 (errors=5) | 0 |
| 2 | `--f007` without `--keep` -> 2 + message | 1 | 0 |
| 3 | real dry-run plan (order, no agy, brain argv) | 2 (argparse) | 0 |
| 4 | test-seat-smoke.py (whole file) | 0 | 0 |
| 5 | test-reconstruct.py | 0 | 0 |
| 6 | shellcheck | 0 | 0 |
| 7 | full suite | not run on base | 0 (ALL TESTS PASSED) |
| 8 | clean tree | 0 | 0 |
| 9 | no `__pycache__` | 0 | 0 |

Commands 1-3 are the oracles; 4-9 are regression checks and pass on both, as in T-046.
Every bullet is one code span with no backtick inside (checked by script).

## Code mutants (run against `test-seat-smoke.py -k f007`)

| Mutant | Result |
| ------ | ------ |
| M1 `--f007` without `--keep` accepted | KILLED (requires_keep_and_refuses_seat) |
| M2 reconstruct with `--all` instead of the worker ids | KILLED (happy_path, missing_ledger_row): confirms the brain-receipt defect in the old task |
| M3 exit code ignores `audit_exit` | SURVIVED |
| M4 `agy.economy` back in `F007_SEATS` | KILLED (dry_run, happy_path) |
| M5 brain run skipped | KILLED (happy_path, missing_ledger_row) |
| M6 last seat not verified | KILLED (happy_path, missing_ledger_row) |
| M7 exit code ignores `reconstruct_exit` | SURVIVED |
| M8 `--f007 --seat` accepted | KILLED (requires_keep_and_refuses_seat) |

M3/M7 survive because no fake scenario makes only the audit, or only reconstruct, fail
while every run completes. Non-blocking: the summary still records both values, and T-038
(the real run) reads them. Optional hardening for a later task: a fake mode where the brain
exits 0 out of scope (audit fails alone), and a hook that removes a ledger row before
reconstruct (reconstruct fails alone).

## Old T-037 defects found

1. `reconstruct-run.sh --all` selects the brain receipt (no VerificationRecord), so the old
   objective could never exit 0 (M2 proves the effect).
2. The old check `fleet-doctor.sh --smoke --f007; test $? -eq 2` passes on the base
   (argparse exits 2 on an unknown flag): a rule-6 violation.
3. The old fake CLI crashes on a brain prompt (seat regex); the revised task says so.
