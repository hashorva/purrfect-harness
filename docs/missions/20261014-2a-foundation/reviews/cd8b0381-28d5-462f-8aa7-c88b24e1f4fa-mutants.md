# T-044 mutants (Architect run cd8b0381-28d5-462f-8aa7-c88b24e1f4fa)

Applied one at a time to `scripts/ledger.py` of the reference patch (scratch clone of 9c4c87a + patch).
"Tests" means `tests/test-ledger.py` of the reference patch; "G" means oracle G.

| # | Mutant | Tests | G |
| --- | --- | --- | --- |
| M1 | bare `(?<![\w.-])/(?:tmp|etc)\b` alternative removed | killed | killed |
| M2 | `re.I` dropped from `SENSITIVE_PATH` | killed | killed |
| M3 | `re.I` dropped from `ABSOLUTE_PATH` | killed | killed |
| M4 | `\$\{?HOME` to `\$HOME` | killed | killed |
| M5 | `~[\w.-]*/` to `~/` | killed | killed |
| M6 | `~[\w.-]*/` to `~\w*/` | killed | killed |
| M7 | Bearer `\s+` back to `[ \t]` | killed | killed |
| M8 | Bearer `\s+` to a single `\s` | killed | killed |
| M9 | `؜` removed | killed | killed |
| M10 | `؜` replaced by `؛` | killed | killed |
| M11 | bare-path lookbehind dropped (`build/tmp` refused) | killed (legitimate-values test) | killed |
| M12 | lookbehind admits `(` and `=` | killed | killed |
| M13 | `\b` dropped after `tmp|etc` | killed only by text match | survived |
| M14 | ` or SENSITIVE_PATH.search(value)` removed | killed | killed |
| M15 | Bearer ASCII-only, `(?a)(?i:Bearer)\s+\S` | killed | killed |

M13 tightens the rule (it would also refuse `/tmpfiles` or `/etcd`) and admits nothing new, so it is
an acceptable survivor. The tests catch it only because `NEAR_MISS_MUTANTS["bare"]` no longer finds
its text. No legitimate value in the measured data starts with `/tmp` or `/etc` followed by a word character.
A first M15 draft used the scoped flag `(?ai:Bearer)`, which leaves `\s` Unicode-aware outside the
group, so it behaves the same as the patch. It was dropped and replaced by the global `(?a)` form above.
Mutant runs without `.git` in the copy also fail the unrelated
`test_builder_uses_receipt_configuration_registry_doors_and_independent_tier`; copy `.git` when you
re-run mutants.
=== END FILE ===
