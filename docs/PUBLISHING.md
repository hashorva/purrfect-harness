---
title: Publishing & Releasing on GitHub
updated: 2026-10-14
---

<!-- markdownlint-disable MD025 -->

# Publishing and releasing on GitHub

[RELEASING.md](RELEASING.md) is the versioning, preparation, tag, and consumer
adoption procedure. This document covers GitHub publication. The current
release is `3.0.0`. The `2.3.1` and `2.3.2` numbers were untagged development
baselines and were never published.

Prerequisites: Git, GitHub CLI, and an authenticated account authorized for the
target repository. Run `gh auth status` before publication.

## First publication

Only create a remote or repository when explicitly requested. In an existing
Git repository with no GitHub remote:

```bash
gh repo create purrfect-harness --public --source=. --remote=origin --push
```

If the remote already exists, inspect it and publish to that repository rather
than adding or replacing it. Repository visibility is a human choice.

## Release an existing repository

1. Follow RELEASING.md: select the version, prepare the changelog/manifest/README,
   run checks, commit, and create the authorized annotated tag.
2. Validate the clean tagged source with
   `bash scripts/install-harness.sh --validate-release`.
3. Push the reviewed main branch and that exact tag.
4. Confirm the main CI and tag-triggered Release workflow both succeed.
5. Inspect the release notes and download link for the generated ZIP.

The Release workflow runs the shared manifest validator with
`--require-release --trigger-tag "$GITHUB_REF_NAME"`, so an unrelated second
tag on HEAD cannot authorize a release. It then uses the first CHANGELOG entry
for notes and creates the GitHub Release itself.

Use GitHub CLI to inspect results after pushing:

```bash
gh run list --workflow ci.yml --limit 5
gh run list --workflow release.yml --limit 5
# Substitute the actual run id and approved version.
gh run watch RUN_ID
gh release view vX.Y.Z
```

## Failure handling

- Version/tag/manifest mismatch: inspect the failing shared validator output.
  Preserve every published tag. Prepare a corrected new version instead of
  deleting and reusing a pushed tag.
- CI failure: fix the reported check, rerun it locally, and publish the reviewed
  correction under the release procedure.
- An incomplete release job: inspect its logs and existing release assets before
  retrying. Do not create a second release or replace published evidence blindly.

## Consumer propagation

After the release succeeds, use the updater from its clean tagged source:

```bash
bash scripts/update-harness.sh /absolute/path/to/consumer
```

Review and qualify the consumer change before merging. The updater preserves
project-owned instructions and mission instances; the migration review in
RELEASING.md remains necessary.
