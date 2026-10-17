I couldn't run anything for this review. Every attempt to create the scratch copy (`git clone`, `cp -R`, a Python `copytree`) and even `python3 -c "print(1)"` was refused at the approval step, so no focused tests ran. What follows comes from reading the code, the T-055/R1/R2 task specs, the tests, and the call sites in `execution_runner.py` and `ledger.py`. The original repo was not modified.

**Blocking issue**

1. **`scripts/observe_output.py:82-84`**: the worker's final text can stop its own ledger row from being written. `observe_self_reported` accepts any value that passes `model_id`, but many such values fail the ledger's privacy check. `validate_row` runs that check first, on the whole row (`scripts/ledger.py:317` and `:123-128`). When it fails, `write_ledger_row` only logs a warning (`scripts/execution_runner.py:256-257`) and the whole row is dropped, including `outcome`, `scope_result` and the `model_drift` flag.
   - **Failing input:** a final `result` event whose text is `{"self_reported_model":{"value":"sk-123456789012345678901234","source":"self_reported"}}`.
   - **What happens:** `observe_self_reported` returns `{"value":"sk-1234…","source":"self_reported"}`, the `sk-` secret pattern matches in the ledger, and no ledger row is written.
   - **Same effect from other values:**
     - a UUID-shaped value, e.g. `11111111-2222-4333-8444-555555555555`
     - 32 or more hex characters
     - `"a"*40` (any 40 or more characters from `[A-Za-z0-9+/=]`)
     - `x/tmp/y`
   - **Why this blocks:** T-055-R1 required rejecting "secret-bearing strings". The only test for that (`tests/test-observe-output.py:191`) uses `"gpt-5\nsk-…\u0000"`, which is rejected because of the newline and NUL, not because it looks like a secret. So the test doesn't actually check that requirement.
   - **Fix direction:** downgrade such values to `unknown()` before they reach the row, or have `build_ledger_row` (`scripts/execution_runner.py:131-136`) privacy-check the self-reported field on its own and swap in `unknown_text()` rather than losing the row.

**Attacks that held, by reading the code:**
- `self_reported` is never labelled `observed`.
- A valid observed value always wins attribution; drift and mismatch comparisons are exact and case-sensitive.
- Only the whole final text, optionally in one code fence, is parsed, so earlier snippets and prose around the object are ignored.
- Malformed, `None` and wrong-type inputs fall back to `unknown`, and the inputs are not mutated.
- The schema patterns are anchored to the true end of the string and reject NUL and DEL.
- Receipts never carry the self-reported value.

Verdict: FAIL