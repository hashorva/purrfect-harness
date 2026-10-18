No blocking issues.

The run path pins a full object id before the provider starts, then reads `harness-registry.json` with `git --no-replace-objects cat-file blob <base_commit>:harness-registry.json`. Empty and dash-prefixed ids return `{}` before `git` is started. A non-hex id, a missing commit, a commit with no registry file, malformed JSON, a non-object top level, and non-object `doors` (including a huge string or array) also return `{}`, so the row is `unknown` / `unknown` / `unknown`. A working-tree edit, including one made after the provider starts, is not what that command reads. Refusals are the fixed strings `door: must be a registry door name or unknown` and `door: registry unavailable`; the door value, the registry body, and the path are not part of those messages.

The new tests fail if the door-membership check, the `--no-replace-objects` flag, the pinned `base_commit` (replaced by `HEAD`), the non-zero-exit `return {}`, the working-tree read, or `validate_row(row)` is removed. Command execution was blocked in this session, so those suites and temp-copy mutants were not executed; the conclusion is from the assertions and the branches they call.

Non-blocking observations:

- `base_registry_doors` in `scripts/execution_runner.py:71` accepts any other non-empty string. `base_commit=":0"` is index stage 0 of `harness-registry.json`, and `HEAD` follows the ref. A launched run does not pass those: `execution_spec.py` requires a 40–64 hex object id, and the spec is loaded once before the provider.
- At `scripts/execution_runner.py:82`, only `UnicodeError` and `JSONDecodeError` become `{}`. A deeply nested document raises `RecursionError`, and `write_ledger_row` (`scripts/execution_runner.py:237`) then skips the row with `ledger: row build failed` and does not write the body.
- `ledger.py validate`, `fold`, and `view` call `validate_row(row)` with no `door_names` (`scripts/ledger.py:522` and `scripts/ledger.py:560`), so they use the working-tree registry. The runner passes the base-commit names (`scripts/execution_runner.py:230`).
- The builder and the validator each call `base_registry_doors` (`scripts/execution_runner.py:116` and `:230`). If that blob disappears between the two calls, the second result is `{}` and the membership check skips the row. The task asks for both calls, and the provider process group is stopped before the write.
- `tests/test-ledger.py:693` matches the explicit-`door_names` error with an unanchored regex. The CLI cases at `tests/test-ledger.py:668` require the stderr line to be exactly `ERROR: ledger: door: must be a registry door name or unknown`.

Verdict: PASS
done
