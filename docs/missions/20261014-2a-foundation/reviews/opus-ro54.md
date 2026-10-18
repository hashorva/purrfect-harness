I found no blocking issues, but this is a static review only. I never ran the tests: every command that would make a scratch clone or run anything (`git clone`, `cp -R`, `git archive`, `shutil.copytree`, `python3 tests/test-observe-output.py`, and a probe script I wrote at `/private/tmp/claude-501/-private-var-folders-nz-r359d1z15512kjwfjl14ypv00000gn-T-tmp-rXAedw2im5-repo/7786267e-a9ef-46b2-a6d4-9aab7cc92910/scratchpad/probe.py`) was waiting on an approval that never came. Nothing ran against the original repo or the real `~/.codex`.

What I checked against `scripts/observe_output.py`, `tests/test-observe-output.py`, `harness-registry.json` and the two callers (`execution_runner.py:418-439`, `probe_seat.py:215`):

- **Only `model` is read:** `_codex_model_from_session` (`:265-286`) takes only `obj.model` and `payload.model`. Nothing else is stored, and the only thing returned is the one validated value. If any candidate fails validation, or two different values appear, the result is unknown.
- **Errors:** session read errors are caught, and the runner swallows any other exception with a fixed `WARN: observation unavailable` message, so no file content reaches logs or errors. The CLI's `main` only prints `unknown provider`. A `PermissionError` on older Pythons could put a path in stderr, but never a session field.
- **Odd files:**
  - Binary, UTF-16 or undecodable: `errors="replace"` plus per-line `ValueError` turns these into unknown.
  - Deep nesting: `RecursionError` is caught.
  - Huge ints: the over-4300-digit error is a `ValueError`, also caught.
  - Huge files: they are read whole, which costs memory and time but exposes nothing.
  - U+2028 splitting a line: the leftover piece can't form a valid object holding `model`, because content quotes are escaped. A spoof could at worst turn the result into unknown.
- **Paths:**
  - Symlinks: a symlinked final file is rejected (`:254`), and FIFOs fail `is_file`.
  - Path traversal: `thread_id` must be a single UUID with no newline, and it's only compared against file names, never joined into a path.
  - Two matching files give unknown (tested).
  - Race between find and read: a swap can only redirect the read to another file the user owns, still model-only through the same validator. Not blocking.
- **Display names:** matching is exact and case-sensitive, mapped values are re-validated, and unknown names give unknown (tested).
- **Validator (`:20,24-32`):** ASCII-only character classes, no IGNORECASE, `fullmatch` with `\Z` and explicit newline/CR rejection. Exactly 80 characters passes and 81 fails. I found no bypass via unicode, a trailing newline or length.
- **Hermeticity:** `setUp` points `CODEX_SESSIONS_DIR` at a temp dir for every test. The CLI subprocess gets it too. The fallback test sets `HOME` to a fake home before unsetting the variable, and restores both afterwards. `test-execution-integration.py` also isolates it. No other test sends a codex stream with a valid thread id (the `test-probe-seat` stub has no `thread_id`), so no test can scan the real home.

Verdict: PASS