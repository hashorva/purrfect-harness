---
title: Publishing & Releasing on GitHub
updated: 2026-07-19
---

<!-- markdownlint-disable MD025 -->

# Publishing the harness (first time) and releasing (every version)

Prereqs: `gh` installed and authenticated (`gh auth status`), macOS.

## A. First publish (once)

```bash
# 1. Make the kit a git repo (kit files at the ROOT — no wrapper folder)
cd ~/dev/purrfect-harness          # wherever you unzipped/keep the kit
git init
git add -A
git commit -m "feat: agent harness kit v1.11.0"

# 2. Run the tests locally BEFORE publishing anything
bash tests/run-tests.sh            # must end with ALL TESTS PASSED
brew install shellcheck            # if missing
shellcheck scripts/*.sh tests/*.sh

# 3a. If the GitHub repo does NOT exist yet:
gh repo create purrfect-harness --public --source=. --remote=origin --push

# 3b. If you already created an EMPTY repo named purrfect-harness on github.com:
git remote add origin "https://github.com/$(gh api user -q .login)/purrfect-harness.git"
git branch -M main
git push -u origin main

# 4. Watch CI go green
gh run watch
```

## B. Release a version (every time — matches docs/RELEASING.md)

```bash
# 0. CHANGELOG.md top entry == the version you are about to tag (CI enforces it)
# 1. Annotated tag, prefixed with v
git tag -a v1.11.0 -m "v1.11.0 — model routing, dual-brand orchestrator, CI/CD"
git push origin main --follow-tags

# 2. The Release workflow now: guards tag==CHANGELOG, builds the zip,
#    publishes a GitHub Release with notes extracted from CHANGELOG.
gh run watch
gh release view v1.11.0
```

## C. Recommended repo settings (once, optional)

```bash
# Protect main: PRs + green CI required (solo-friendly: no review requirement)
gh api -X PUT "repos/{owner}/purrfect-harness/branches/main/protection" \
  -F required_status_checks[strict]=true \
  -F "required_status_checks[contexts][]=lint-and-test" \
  -F enforce_admins=false \
  -F required_pull_request_reviews=null \
  -F restrictions=null
```

If the API call syntax fights you, set it in the UI instead:
Settings → Branches → Add rule → `main` → require status checks → lint-and-test.

## D. Day-to-day flow after publishing

1. Change kit files on a branch → PR → CI green → merge (or push to main
   directly if you skip protection; CI still runs).
2. Add a CHANGELOG entry per RELEASING.md (MAJOR/MINOR/PATCH semantics).
3. Tag + push (section B) → Release appears automatically.
4. Propagate to products: `bash scripts/update-harness.sh /path/to/repo`.

## Failure modes

- Release workflow fails "Tag != CHANGELOG": you tagged before updating
  CHANGELOG.md. Fix CHANGELOG, `git tag -d vX.Y.Z`, `git push origin
:refs/tags/vX.Y.Z`, re-tag.
- CI fails on shellcheck after editing a script: read the SC code it prints;
  they are almost always real bugs (unquoted vars, word-splitting).
- `gh repo create` says name exists: you are in case 3b — add the remote.
