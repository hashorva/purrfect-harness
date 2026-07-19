---
title: Releasing purrfect-harness
---

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
cd ~/Projects/purrfect-harness
# 1. Make changes on a branch, merge to main
# 2. Add a CHANGELOG.md entry at the TOP (## X.Y.Z (date) + bullets)
# 3. Bump version: in README.md frontmatter
# 4. Commit the release prep
git add -A && git commit -m "release: vX.Y.Z"
# 5. ANNOTATED tag (not lightweight — carries author/date/message)
git tag -a vX.Y.Z -m "vX.Y.Z — one-line summary"
# 6. Push commit AND tag (tags are NOT pushed by default!)
git push && git push origin vX.Y.Z
# 7. Optional, for the public showcase era:
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
