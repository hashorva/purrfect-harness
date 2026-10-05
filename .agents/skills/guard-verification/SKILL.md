---
name: guard-verification
description: Prove that a check actually checks. MUST be used when adding, reviewing or accepting any guard, gate, validator, constraint, assertion or safety test — and before flipping a feature to passing on the strength of one. Catches guards that are not mounted, accept empty values, or appear red because an unrelated setup or construction failure happened first. Use whenever a test passes and you have not seen the intended guard reject the intended violation.
---

# Guard verification — a check that cannot fail correctly is not a check

## The failure this prevents

A guard is written correctly, gets unit tests, the tests pass, review approves it — and it
never runs where it matters, accepts a vacuous value, or appears proven because a negative
test failed for an unrelated reason.

A red result is not sufficient. The failure must reach the intended guard and exhibit the
expected failure signature.

Three shapes, one lesson.

### Shape 1 — the guard is never mounted

The validator is correct. The only code that ever calls it is the test.

- A language switcher was built correctly and wired into one surface; a second surface rendered a
  hardcoded control. Component tests exercised the component; the app rendered something else.
- A publication guard handled its flag correctly. The build wired that flag into four other places
  and never into the validator — the only caller passing the flag was a unit test.

### Shape 2 — the constraint is trivially satisfiable

The guard runs, but the failing case cannot occur.

- `NOT NULL` on explanatory text is satisfied by `''`.
- An extraction falls back to an empty list when its pattern does not match. The loop examines
  nothing and reports success.

A trivially satisfiable constraint is worse than none because it looks like a guarantee.

### Shape 3 — the negative fails for the wrong reason

The regression is red, but execution never reaches the guard it claims to prove.

- A mutation replaces fixture or record construction instead of the later validation expression.
- A syntax, import, setup, timeout, or earlier validation error aborts the test first.
- A bypass test treats a deliberately weakened verifier returning success as its success oracle,
  rather than making a mounted negative regression fail.

These results prove only that something broke.

## Procedure

### 1. Find the real callers

```bash
rg -n "<guardName>" \
  --glob "*.{ts,tsx,js,py,sh}" \
  --glob "!*.test.*" \
  --glob "!*.spec.*" \
  --glob "!tests/**" \
  --glob "!**/__tests__/**"
```

If that returns only tests or definitions, the guard is not mounted.

### 2. Name the real entry point

Write down the exact production or CI entry point that reaches the guard: a build command,
request handler, worker wrapper, mission audit, release validator, migration, or equivalent.

“Exported and importable” is not mounted.

### 3. Establish the positive baseline

Run the real entry point against known-good state before mutating anything. Record its successful
exit status or final success assertion.

A mutation result is uninterpretable without a known-good baseline from the same entry point.

### 4. Exercise one intended violation

Use one of these two valid proof shapes:

1. Keep the guard enabled, provide a deliberately violating input, and observe the real entry
   point reject it.
2. Temporarily bypass exactly one guard, run a mounted negative regression, and observe that
   regression fail because the real entry point admitted the violation.

Target one unique production expression. Do not mutate fixture construction, setup code, or an
earlier guard.

The failure must identify the intended invariant. Reject the result if it is caused by:

- syntax, import, name, or type errors outside the intended validation;
- fixture, record, or environment construction failure;
- missing tools, timeouts, or transport interruption;
- an earlier unrelated guard;
- a deliberately weakened implementation returning success when no mounted regression asserts
  that this is wrong.

Record the expected failure signature and confirm that it appeared.

### 5. Restore exact bytes and rerun the positive path

Restore the mutated file exactly and verify that no mutation remains:

```bash
git diff --exit-code -- <guard-file>
```

Then rerun the positive baseline from step 3. Both restoration and the final successful run are
required.

### 6. Test fallbacks and weakest values

For every `?? ''`, `|| []`, optional match, swallowed exception, or default value inside a guard,
ask:

> If this fallback fires, does the check pass?

If yes, fail loudly instead.

For every constraint, construct its weakest satisfying value:

| Constraint | Weakest satisfying value | Required protection |
| --- | --- | --- |
| `NOT NULL` text | `''` | require non-empty trimmed text |
| list is present | `[]` | require a non-empty list |
| field exists | `null` or wrong type | require value and shape |
| regex extraction | no match | fail instead of returning empty |
| identifier present | unrelated valid identifier | bind it to the authorized subject |

If the weakest satisfying value would be rejected in review, the constraint does not express the
intended policy.

### 7. Mount the regression at the real boundary

Assert on what the entry point produced or rejected: emitted files, response state, database
state, receipt, audit result, or process exit.

The regression must fail if the wiring is removed, not merely if the validator’s internal logic
changes.

When a guard revalidates persisted or immutable historical evidence, run at least one supported
historical artifact through the real audit entry point. A new isolated fixture does not prove that
existing evidence remains valid under changed policy.

## Self-verification checklist

- [ ] Non-test callers exist and the real entry point is named
- [ ] The unmodified entry point passes before mutation
- [ ] One mutation or violating input targets the intended guard
- [ ] The expected guard-specific failure signature was observed
- [ ] No syntax, setup, construction, timeout, or unrelated earlier failure caused the red result
- [ ] Every fallback fails closed
- [ ] The weakest satisfying values are genuinely acceptable
- [ ] The regression asserts against the mounted boundary
- [ ] Historical evidence was exercised when the changed policy revalidates it
- [ ] The guard was restored byte-for-byte
- [ ] The unmodified positive entry point passes again
- [ ] The observed positive and negative evidence is recorded for review

## Never

- Never accept a green suite as proof that a guard is mounted.
- Never accept “the negative is red” without checking why it is red.
- Never mutate fixture construction when claiming to test a validation guard.
- Never let a unit test calling the validator directly stand in for mounted proof.
- Never let “could not check” become “passed.”
- Never leave mutation bytes behind.
- Never mark a guard feature complete without seeing the intended violation reach the intended
  guard.
- Never fix a correctly failing guard by changing the data it was built to reject; overriding the
  policy is a separate human decision.
