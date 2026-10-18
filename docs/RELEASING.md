---
title: Releasing purrfect-harness
updated: 2026-10-18
---

<!-- markdownlint-disable MD025 -->

# Releasing (tag-driven)

The current release is `3.1.0`: Phase 2A Foundation (fleet v2, provider
contracts 7–9, ledger v2, seat probes and the native-only fleet), after `3.0.0`
(Phase 1, Execution Truth). Before `3.0.0`, `2.3.1` and `2.3.2` were untagged
development baselines; they were never published. Choose each new version with
the rules below.

Versioning is SemVer, interpreted for a harness:

- **MAJOR:** ownership or protocol changes requiring manual consumer work beyond
  running the updater, such as migrating mission evidence or project instructions.
- **MINOR:** new skills, templates, or capabilities that the updater propagates cleanly.
- **PATCH:** fixes, typos, and documentation with no behavioral change.

Choose the Phase 1 version from actual downstream compatibility. Cross-repository
dispatch is disabled, legacy evidence cannot substitute for the current acceptance
chain, and existing project-owned AGENTS.md files require manual review. These
changes require a migration assessment; do not assume the development number is
the release number.

## Prepare the candidate

1. Review downstream usage and choose the release version.
2. Update README frontmatter, the top CHANGELOG heading/date, and
   `harness-manifest.json` version/required_tag together.
3. Include immutable specs, frozen fleet, same-repository dispatch, terminal
   receipts, run-specific verification, separate acceptance, and migration notes
   in the release notes.
4. Complete required checks and the explicit development-mode release validator:

```bash
shellcheck scripts/*.sh tests/*.sh
git ls-files -z '*.json' | xargs -0 -n 1 sh -c 'python3 -m json.tool "$1" >/dev/null' sh
PYTHONDONTWRITEBYTECODE=1 bash tests/run-tests.sh
bash scripts/install-harness.sh --dev --validate-release
git diff --check
```

The test suite must reach `ALL TESTS PASSED`. Commit the reviewed release
preparation and require a clean tree. Check the archived Phase 1 smoke evidence:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 docs/missions/20260821-execution-truth/evidence/f007/reconstruct.py
PYTHONDONTWRITEBYTECODE=1 bash docs/missions/20260821-execution-truth/evidence/f007/test-reconstruct.sh
```

For the mission audit, retain the local `.tasks/` specs/receipts/logs:
`bash scripts/verify-mission.sh --require-workers docs/missions/20260821-execution-truth`.
A fresh clone uses the self-contained archive; ordinary local receipts are
machine-local and are not reconstructed from chat claims.

## Tag and publish the approved release

Tag creation and publication require explicit human direction. After that
authorization, replace `X.Y.Z` below with the chosen version:

```bash
RELEASE_VERSION=X.Y.Z
git tag -a "v$RELEASE_VERSION" -m "v$RELEASE_VERSION"
bash scripts/install-harness.sh --validate-release
git push origin main
git push origin "v$RELEASE_VERSION"
```

Normal validation requires the exact clean annotated manifest tag on HEAD.
The tag-triggered GitHub Release workflow validates that same tag, extracts the
top CHANGELOG entry, builds the ZIP, and creates the release automatically.
Confirm both main CI and the tag release job succeed and inspect the published
asset. Do not also create a duplicate release manually.

Never move or delete a published tag. If it is wrong, preserve it and publish a
corrected new version with an explanatory changelog entry.

## Adopt in consuming repositories

Use a published clean tagged source and a clean managed target:

```bash
bash scripts/update-harness.sh /absolute/path/to/consumer
```

The updater creates a branch and records `.harness-version`; it does not commit.
Review the diff and any `settings.json.new`, run consumer checks, and commit/merge
according to that project's deployment rules.

Review project-owned AGENTS.md and mission instructions manually against the new
consumer skeleton. Preserve historical mission evidence; do not invent UUIDs or
acceptance metadata for old runs. A legacy mission lacking current evidence may
fail the strict audit. Start new work with approved frozen fleet state and the
current templates, then qualify a small real mission in the selected consumer.

`--dev`/`--allow-untagged` is only for explicit local development or smoke work.
Never use it for normal consumer propagation.
