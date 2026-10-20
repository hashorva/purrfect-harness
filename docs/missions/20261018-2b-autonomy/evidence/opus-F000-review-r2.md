I found no blocking issues, but this is from reading the code only. Shell commands were refused, so I couldn't make the scratch clone or run any of the failing inputs, `tests/run-tests.sh` or `shellcheck`. Every result below is a code trace.

- **T-018 (agy `--print-timeout` edit in adapter and fixtures):** a pull request that changes `30m`→`60m` in `scripts/execute_provider.py:171,174` and edits `agy-v*.json` to match now fails CI. The history check in `scripts/check-golden-argv.py:39-46` treats a modified or deleted recorded fixture as an error; only a new `-v<N>` file above the base's highest contract is allowed. CI runs the step with `CI=true` and `fetch-depth: 0` (`.github/workflows/ci.yml:28-30,88-91`), and with no `origin/main` it exits 2 instead of skipping (`:57-59`).
- **T-019 (`--run-id ../../../../tmp/x` and `--run-id '*'`):** `uuid.UUID` raises on both values, so `scripts/run_id.py:20-25` refuses them. That check runs before any path use:
  - `scripts/verify-mission.sh:14`, which runs before `active-mission.sh` and the call into `verification_record.py`;
  - `scripts/accept-feature.sh:14`;
  - `scripts/verification_record.py:478`, before `root_path` and `mission_path` at line 481.
  
  The explorer traced the internal callers (`verify`, `accept`, `bind`, `run_records`), `reconstruct_run.py` and `execution_spec.py construct`, and each validates before joining or globbing a path. `spawn-worker.sh` and `spawn-brain.sh` have no `--run-id` flag; the worker generates the id itself.
- **T-020 (scanner bypasses):**
  - `from uuid import UUID` is flagged at `tests/test-run-id.py:73-74`.
  - The escaped-dash pattern is flagged: Python compiles `\-` as a literal dash, and `:25-26` also strips the backslashes as a fallback.
  - `scripts/lib/ids.py` is covered because `rglob` scans every subdirectory, and the exemption only matches the top-level `run_id.py` (`:107-109`).

Two gaps I don't count as blocking:
- **Direct push to `main`:** on a push run, `origin/main` is the same commit as `HEAD`, so `check-golden-argv.py` compares `HEAD` with itself and passes without checking anything. It only protects pull requests unless branch protection blocks direct pushes.
- **Scanner `fold` limits:** `fold` (`tests/test-run-id.py:44-56`) doesn't resolve `"-".join([...])`, `%` or `.format`. So a pattern built as `"-".join(["[0-9a-f]{8}", ...])`, or a shell BRE using `[[:xdigit:]]\{8\}-`, isn't flagged. That falls short of the T-020 commit's "any spelling" claim, but every entry point still validates the run id.

Verdict: PASS