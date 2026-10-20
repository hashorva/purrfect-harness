I found three blocking issues: one in T-010 and two in T-014-R1/R2. T-011, T-012, T-013 and T-015 have nothing blocking. I read code and git history only; running scripts needed approval, so I didn't run the test suite or try the failing inputs below.

**Blocking issues**

1. **T-010: a fixture can be changed along with the adapter, and the test still passes.** `tests/test-golden-argv.py:21-27` compares the live adapter's argv with whatever the fixture files currently say. Nothing records what the fixtures held when they were first written: no hash, no manifest, no git check. Lines 39-42 only check file names, JSON formatting and how many cases each file has. The "immutable" rule appears only in prose, in `tests/fixtures/golden-argv/README.md:3`.
   - **Failing input:** in `scripts/execute_provider.py`, change agy's `"--print-timeout", "30m"` to `"60m"` for every contract, and make the same edit in `agy-v1.json` … `agy-v9.json`. `test-golden-argv.py` passes.
   - `test-evidence-2a.py` doesn't catch it either, because its fixture has no agy receipts (it asserts codex, claude and agent only, lines 84-85).
   - So the new `AGENTS.md` line "the golden argv test enforces it" is not true as written.
   - The recorded argv itself is correct where I checked it against history: codex v1/v2 at `8298222`, claude v1 at `8298222`, claude v6 at `c598964`, claude v8 (current and historical forms), and agent v4 at `865063c`.

2. **T-014-R2: a run id is used in paths before it is validated.**
   - In `verify()`, `scripts/verification_record.py:209-215` builds paths from the run id and calls `.exists()` on them before `bind()` validates it at line 216.
   - In `accept()`, line 396 reaches `run_records` (lines 342-345), which joins `f"{run_id}.json"` and runs `record_dir.glob(f"{run_id}.*.json")`. No check runs first, and `scripts/accept-feature.sh:14` only checks that the id is non-empty.
   - **Failing inputs:**
     - `bash scripts/verify-mission.sh --run-id ../../../../tmp/x docs/missions/20261018-2b-autonomy` checks whether a file outside the mission exists before refusing the id.
     - `bash scripts/accept-feature.sh --run-id '*' --verification-sha256 <64 hex> --accepted-by o docs/missions/20261018-2b-autonomy` globs the whole verification directory. If numbered records exist, it fails with "invalid number: <another run's file>" instead of a run-id refusal.

3. **T-014-R2: the scanner is easy to bypass.** `tests/test-run-id.py:85-95` only counts five literal strings (`uuid.UUID(`, `[1-8]`, `[89ab]`, `{36}`, `{8}-`). It only looks at `.py` and `.sh` files directly in `scripts/`.
   - **Failing input:** add `from uuid import UUID` and `UUID(value).version in range(1, 9)` to any script. None of the five strings appears, and the test passes.
   - These also pass: a pattern written as `[0-9a-f]{8}\-…`, or a parser placed in a subdirectory such as `scripts/lib/ids.py`.

**Checked, nothing blocking**

- **T-011:** The fixture is scrubbed: no personal paths, real email addresses or secrets. The only non-placeholder `@` is `t@example.invalid`. The owner's name does appear in `features.json` approval text. The audit runs the real `verify-mission.sh --require-workers`, and a mutation test shows an argv change makes it fail. The CI step is wired at `.github/workflows/ci.yml:85-86`.
- **T-012:** The matrix is Ubuntu with Python 3.12, Ubuntu with 3.14, and macOS with 3.14. `test-ci-workflow.py` pins this, and a CI step checks the suite runs the matrix's Python version.
- **T-013:** All 19 tests that were in the old hand-written list match the discovery pattern, so none was dropped. `test-run-id.py` also runs now. The separate bytecode checks after each test group became one final check, which still catches leftover bytecode.
- **T-015:** The commit touches only `AGENTS.md` and the three named `SKILL.md` files. Every added line matches the task text character for character, in the right place. Nothing else changed.

Verdict: FAIL