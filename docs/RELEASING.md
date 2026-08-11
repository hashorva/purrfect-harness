---
title: Releasing purrfect-harness
---

<!-- markdownlint-disable MD025 -->

# Releasing (tag-driven)

Versioning is SemVer, interpreted for a harness:

- **MAJOR** (2.0.0): ownership/manifest changes — consuming repos need manual
  work beyond running the updater (e.g. a file changed owner, AGENTS.md skeleton
  restructured)
- **MINOR** (1.10.0): new skills, new templates, new capabilities — updater
  propagates them cleanly
- **PATCH** (1.9.1): fixes, typos, docs — zero behavioral change

## Release procedure

```bash
cd ~/dev/purrfect-harness   # or wherever the kit lives
# 1. Make changes on a branch, merge to main
# 2. Add a CHANGELOG.md entry at the TOP (## X.Y.Z (date) + bullets)
# 3. Bump version: in README.md frontmatter — REQUIRED. CI and
#    tests/run-tests.sh both compare README 'version:' to the top CHANGELOG
#    heading with the same extraction. Skipping this failed v2.2.4 and v2.2.5.
# 4. Run bash tests/run-tests.sh (catches the version mismatch locally)
# 5. Commit the release prep
git add -A && git commit -m "release: vX.Y.Z"
# 6. ANNOTATED tag (not lightweight — carries author/date/message)
git tag -a vX.Y.Z -m "vX.Y.Z — one-line summary"
# 7. Push commit AND tag (tags are NOT pushed by default!)
git push && git push origin vX.Y.Z
# 8. Optional, for the public showcase era:
gh release create vX.Y.Z --title "vX.Y.Z" --notes-from-tag
```

## Propagation after release

```bash
for repo in ~/Projects/finduck ~/Projects/consulenza360; do
  bash scripts/update-harness.sh "$repo"
done
# then in each repo: review git diff, merge settings.json.new if present, commit
```

## Rules

- Never move or delete a pushed tag — tags are promises.
- Never propagate from an untagged state — repos receive only blessed versions.
- `update-harness.sh` writes `.harness-version` in each repo; `git diff vA vB`
  in the harness answers "what will this repo receive".
