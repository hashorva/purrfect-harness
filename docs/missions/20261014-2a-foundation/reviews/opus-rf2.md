I found no blocking issues. I couldn't run anything: Python and the test suite needed approval here, and cloning to a scratch copy was blocked. So this is a code-reading review of HEAD `3cf5e34`. I made no changes. The tests named below exist but I did not run them here.

**(1) The worker's self-report can't stop its ledger row.** The final text reaches the row through `observe_self_reported` (`scripts/observe_output.py:42-80`). That function checks the value with `valid_model_id` (`scripts/model_id.py:16`), and `safe_model_flag` checks it again (`scripts/execution_runner.py:46-51`). Each of the five inputs is caught:
- `sk-1234…` (24 characters after `sk-`) matches the `sk-…{20,}` secret pattern.
- A UUID matches `MODEL_UUID_SHAPE`.
- 40 a's match the `[A-Za-z0-9+/=]{40,}` pattern.
- `x/tmp/y` contains `/tmp/`.
- 32 hex characters match `[0-9A-Fa-f]{32,}`.

Each one becomes `unknown`. Anything `valid_model_id` accepts also passes the row-wide privacy check (`ledger.py:127-132`): a model id can't contain spaces or `@` and is at most 80 characters. So the self-report can never make `validate_row` refuse the row. `tests/test-ledger.py:1025-1038` writes a row for each of the five values and checks that it exists.

**(2) A self-report never changes door, pool or billing.** These come only from the configured models (`execution_runner.py:158-160`). The self-report feeds only `anti_gaming_flags`, and only as a fixed label. `tests/test-ledger.py:1006-1022` covers this.

**(3) A broken ledger module only skips the ledger step.**
- The ledger import is wrapped in `except Exception` (`execution_runner.py:24-30`), and `write_ledger_row` then just logs a warning and returns.
- The receipt is written before the ledger step (`execution_runner.py:455`).
- None of the receipt-path modules (`execution_receipt`, `execution_spec`, `execute_provider`, `observe_output`) import ledger.
- `model_id.py` imports only `re`.

`tests/test-execution-integration.py:2154-2167` covers a syntax error and an import-time crash.

**(4) Old v2 rows still validate, and view works.** `self_reported_model` is optional (`ledger.py:323-324`). All 29 committed rows have schema version 2 and `tier`, and none has `self_reported_model`. `tests/test-ledger.py:204-222` validates the committed history and runs `view` on it.

One non-blocking risk: `ledger.py:36-46` keeps its own copy of the secret and path patterns that `model_id.py` also defines. If the copy in `model_id.py` is ever loosened, the row-wide privacy check would start refusing values the model check accepts, and rows would be dropped again. Today the two copies are identical.

Verdict: PASS