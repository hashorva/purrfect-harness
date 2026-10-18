Nothing blocks the 3.1.0 release. One caveat: the permission prompts stopped me from running the release validator (`install-harness.sh --dev --validate-release`), shellcheck and `tests/run-tests.sh`, so this pass checks the content but nothing was executed. This clone also has no `origin/main` or local `main`, so I compared against the `v3.0.0` tag.

**What T-124 fixed**
- **Version consistency:** the manifest has `release.version` 3.1.0 and `release.required_tag` v3.1.0. The README frontmatter says 3.1.0, updated 2026-10-17, and the top CHANGELOG heading is `3.1.0 (2026-10-17)`. They all match.
- **Install payload:** every tracked file under `scripts/` and `schemas/` is in `install_payload_paths`. The new ones include `harness-path.sh`, `drive-cli.sh`, `drive_cli_rules.py`, `drive-cli.rules.json`, `probe-seat.sh`, `probe_seat.py`, `ledger.py`, `model_id.py`, `validate_verdict.py`, `worker-output.schema.json` and `ledger-row.schema.json`. The only two left out, `install-harness.sh` and `update-harness.sh`, are handled the same way as in v3.0.0. The payload roots include `.claude/agents` (so `explorer.md` ships) and `docs/missions/capabilities`, which holds the four CLI baselines. No payload entry points at a missing file.
- **CHANGELOG:** it covers everything on your list: fleet v2, provider contracts 7–9, the Claude unlock, Codex network and web search, the ledger, probe-seat, the watchdog, model identity, drive-cli, harness-path, the native-only rule, effort by role, and residual risks.
  - The Claude unlock entry includes the deny-list (73 patterns, matching `scripts/execute_provider.py:28-102`) and the protected-path guard.
  - The Codex entry says `cua_repl`/`node_repl` are off.
  - The drive-cli residuals appear at `CHANGELOG.md:76-77` and `:106`.
  - The migration notes are at `:9-42`.
  - The "Known limits" section is honest about `bypassPermissions` plus Bash being a net, not a wall.
- **docs/RELEASING.md:** it names 3.1.0 as the current release. The scripts and evidence it points to exist (`install-harness.sh --dev --validate-release`, the f007 `reconstruct.py` and `test-reconstruct.sh`). `release.yml` exists.
- **Local state and secrets:** no `.tasks/` files are tracked, and `.tasks/` is in `.gitignore`. A wide scan by a cheap subagent found no real secrets. Every secret-shaped string is a test fixture, a deny-list pattern or a privacy-grep pattern.

**Not blocking, worth cleaning up later**
- Your personal email is quoted as example text at `docs/missions/20261014-2a-foundation/progress-archive/2026-10-14_15.md:796`.
- Some committed mission records contain session scratch paths under `/private/tmp/claude-501/-Users-zamirhashorva-…` (for example `reviews/entry-75bbda63.md:6`) and `/var/folders/...` clone paths (`reviews/argon-T-057.md`). These are mission records, not install payload. v3.0.0 already published the same username in its paths.
- `tests/test-execution-spec.py:269-271` pins receipt hashes that include the repo's own absolute path. That is the repo itself, so it is allowed.
- `docs/RELEASING.md:23-36` and `:55-56` still talk about Phase 1. The steps still work, but there's no audit step for the 2A mission.

Verdict: PASS