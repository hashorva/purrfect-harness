# T-043 mutants (Architect run 31a836d5-eed3-48ec-bdc5-e7c9e62fb554)

Run against the reference patch (`T-043 reference` commit in a scratch clone of d10aeb0) with
`python3 tests/test-verification-record.py -k skip -k revalidation -k validator` (about 21 s each).
14 run, 14 killed, 0 equivalent.

| id | mutation (scripts/verification_record.py unless noted) | killed by |
| --- | --- | --- |
| M1 | `passed = passed and exit_code == 0` (skip does not fail) | reported-skips test; oracle E |
| M2 | scan stdout only | reported-skips (unittest summary is on stderr; `SKIPPED` on stderr); oracle E |
| M3 | scan stderr only | reported-skips (pytest, TAP, marker on stdout); oracle E |
| M4 | `skip_detected` not added to the outcome | reported-skips (`skip_detected` assertion) |
| M5 | revalidation: `item["exit_code"] == 0` only | revalidation label `skip` (neither oracle reaches it) |
| M6 | validator admits any `skip_detected` value | validator weakest list; oracle F |
| M7 | marker without `^` | near misses (` SKIP indented`); oracle E (` SKIP x`) |
| M8 | marker with `re.I` | near misses (`skip: lower case`) |
| M9 | unittest `skipped=[0-9]+` unanchored | near misses (`identical-skipped=3`, `OK (skipped=0)`); oracle E |
| M10 | stdout/stderr tails echoed in `VERIFY SKIP` | reported-skips canary; oracle E canary |
| M11 | pytest pattern without `N skipped` | near misses (`===== 3 passed in 0.12s =====`); oracle E |
| M12 | TAP without the `#` directive | near misses (`ok 1 - skip handling works`); oracle E |
| M13 | schemas/verification-record.schema.json enum drops `tap` | validator test enum equality; oracle F |
| M14 | pattern name `TAP` instead of `tap` | reported-skips (kind), validator enum equality; oracle F |

Pattern list justification (false positives): every pattern is anchored at column 0 and is the
runner's own summary or marker (`OK (skipped=N)` is the only unittest OK form with skips, since
unittest prints skipped before expected failures; pytest's `=== ... N skipped ... ===` summary;
TAP's `# skip` directive; the repo's own `SKIP ...` convention in tests/test-fleet-v2.py:282 and
pytest `-rs` `SKIPPED [n]`). Real output check: each of the 13 `tests/test-*.py` files run on d10aeb0
exits 0 and matches no pattern; `tests/run-tests.sh` prints only `  ok   :`/`  FAIL :` lines
(indented, so no marker match). `python3 -S tests/test-fleet-v2.py` (jsonschema hidden) prints
`SKIP schema/code agreement: ...` and is detected as `marker`.
=== END FILE ===
