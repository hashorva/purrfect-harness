---
name: guard-verification
description: Prove that a check actually checks. MUST be used when adding, reviewing or accepting any guard, gate, validator, constraint, assertion or safety test — and before flipping a feature to passing on the strength of one. Catches the two ways a guard silently does nothing: it is never called from the real entry point, or it is satisfiable by an empty value. Use whenever a test passes and you have not seen the guard fail.
---

# Guard verification — a check that cannot fail is not a check

## The failure this prevents

A guard is written correctly, gets unit tests, the tests pass, review approves it — and it
**never runs where it matters**, or it **runs but nothing can violate it**. The suite is green,
the feature is marked done, and the protection does not exist. This is not a hypothetical: it has
shipped three times in this studio, each time behind a fully green test run.

Two shapes, one lesson.

### Shape 1 — the guard is never mounted

The validator is correct. The only code that ever calls it is the test.

- A language switcher was built correctly and wired into one surface; a second surface rendered a
  hardcoded control. Component tests exercised the component; the app rendered something else.
- A publication guard handled its flag correctly. The build wired that flag into four other places
  and never into the validator — **the only caller passing the flag was a unit test.** Flipping the
  flag published documents the guard existed to block.

### Shape 2 — the constraint is trivially satisfiable

The guard runs, but the failing case cannot occur.

- `NOT NULL` on an explanatory text column: satisfied by `''`. The schema *looks* like it
  guarantees an explanation exists.
- An extraction that falls back to empty when its pattern does not match: `const body = m ? m[0] : ''`.
  When the markup changes, zero items are found, **the loop over them passes**, and the gate reports
  success having examined nothing.

**A trivially satisfiable constraint is worse than none**, because the code now looks like it
guarantees something and reviewers stop asking.

## Procedure

### 1. Find the real callers

```bash
# replace <guardName> with the exported function / flag / option
grep -rn "<guardName>" --include="*.ts" --include="*.tsx" --include="*.js" . \
  | grep -v -E "\.(test|spec)\.|__tests__|/tests?/"
```

**If that returns nothing, the guard is not mounted.** If it returns only definitions and no call
from a build script, request handler, CI step or migration, it is not mounted either.

### 2. Trace to the entry point

Name the exact thing that runs in production or CI — `npm run build`, the route handler, the
workflow step. "It's exported and importable" is not mounted. **Write the entry point down**; you
will run it in step 3.

### 3. Break it and watch the real path fail

The only proof. Temporarily disable the guard — comment the condition, invert it, or feed a
deliberately violating fixture — then run **the entry point from step 2**, not the unit test.

- The entry point must **fail**. If it still succeeds, the guard is not protecting that path.
- Restore the guard exactly. **`git diff <guard file>` must be empty** before you commit.
- Put the observed failure output in the PR or progress entry. An assertion nobody has seen fail is
  an assumption.

### 4. Ask what happens when the fallback fires

For every `?? ''`, `|| []`, `? x : ''`, `.catch(() => null)`, optional match or default value inside
a guard:

> If this fallback fires, does the check **pass**?

If yes, it is a no-op wearing a guard's clothes. Make it throw, naming what it could not parse.

### 5. Ask what the weakest satisfying value is

For every constraint, construct the laziest input that satisfies it.

| Constraint | Weakest satisfying value | Fix |
| --- | --- | --- |
| `NOT NULL` on text | `''` | add `length(trim(x)) > 0` |
| "list is present" | `[]` | require non-empty |
| "field exists" | `null` / `undefined` | require a value and a shape |
| regex extraction | no match → empty | fail loudly instead of returning empty |

If the weakest satisfying value is something you would reject in review, the constraint does not
express your intent.

### 6. Write the regression test against the mount point

Assert on **what the entry point produced** — emitted files, response body, database state — not on
the validator's return value.

**The test must fail if the wiring is removed**, not only if the logic is wrong. A test that calls
the validator directly still passes when nobody calls the validator, which is exactly how shape 1
survives review.

## Self-verification checklist

- [ ] Non-test callers of the guard exist, and I named the entry point that reaches it
- [ ] I disabled the guard, ran the **entry point**, and **saw it fail**
- [ ] The guard is restored — `git diff` on its file is empty
- [ ] Every fallback inside the guard fails loudly rather than passing
- [ ] I constructed the weakest satisfying value and it is genuinely acceptable
- [ ] A regression test asserts against the mount point and would fail if the wiring were removed
- [ ] The observed failure output is recorded where a reviewer will read it

## Never

- Never accept a green suite as evidence a guard works. It is evidence the guard's *logic* works.
- Never let a unit test that calls the validator directly stand in for proof of wiring.
- Never leave a fallback that turns "could not check" into "passed".
- Never mark a guard feature done without having seen it fail once.
- Never "fix" a failing guard by changing the data it was built to reject — that is the guard
  working. Removing the blocker is a separate, human decision.
