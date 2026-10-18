The release fails on four blocking issues: three install-payload gaps and one CHANGELOG omission. Two smaller doc problems in `docs/RELEASING.md` also need fixing.

This clone has no `origin/main` or local `main`, so I diffed against `v3.0.0`, the last release tag. I read files and grepped only; I did not run shellcheck or the test suite.

**Blocking issues**

1. **`harness-manifest.json:30` and `:79`**: `scripts/harness-path.sh` is missing from both `install_payload_paths` and `update_paths`. Installed consumers will get `scripts/fleet-doctor.sh`, which loads it with no fallback at `scripts/fleet-doctor.sh:8`. Under `set -euo pipefail`, the Gate 0 doctor therefore exits with an error in every consumer. The wrappers `scripts/spawn-brain.sh:13-16` and `scripts/spawn-worker.sh:32-35` skip it quietly, so they lose the PATH fix that `CHANGELOG.md:20-24` and `:77-78` describe.
2. **`harness-manifest.json:25-30` and `:79`**: `docs/missions/capabilities/` is not in the payload roots, payload paths or update paths. `scripts/probe_seat.py:26` and `:54-57` (which are shipped) look for the baselines there. With the folder missing, the baseline is empty and every `--help` flag is reported as "new". That contradicts `CHANGELOG.md:29` and `:68` ("diffs … against committed baselines").
3. **`harness-manifest.json:30` and `:79`**: `scripts/drive-cli.sh`, `scripts/drive_cli_rules.py` and `scripts/drive-cli.rules.json` are not shipped. The CHANGELOG lists them as a new capability (`CHANGELOG.md:73-76`), and the shipped `docs/missions/MODEL_ROUTING.md:197` tells consumers to use `scripts/drive-cli.sh`. `CHANGELOG.md:6` and `:11-12` also say the updater carries "the new scripts". The same gap covers `schemas/worker-output.schema.json`, which `CHANGELOG.md:63` names as validated.
4. **`CHANGELOG.md:73-76` and `:92-104`**: the drive-cli residuals are missing. Boxed menus and alternate-screen redraws are accepted residuals that end as an exit-4 stall. This is recorded in `docs/missions/MODEL_ROUTING.md:197` and in commit f28e259, but neither the drive-cli entry nor "Known limits" mentions it.

**Smaller doc problems (to fix with the above)**

- **`docs/RELEASING.md:3`, `:10-12`**: it still says "The current release is `3.0.0`" and `updated: 2026-10-14`.
- **`docs/RELEASING.md:65`**: the tag message is hard-coded as "Phase 1 execution truth", so the v3.1.0 tag would be mislabelled. The other steps in that file still match the scripts' flags and the release workflow.

**Checks that passed**

- **Version:** the manifest has `3.1.0` / `v3.1.0`, the README frontmatter has `3.1.0` updated 2026-10-17, and the top CHANGELOG heading is `3.1.0 (2026-10-17)`. No tag is on `HEAD` yet, which is expected for a candidate.
- **CHANGELOG coverage:** apart from the drive-cli residuals, all the capabilities you listed are present: fleet v2, contracts 7–9, the Claude unlock, Codex network and web search with `cua_repl`/`node_repl` off, ledger, probe-seat, watchdog, strict-mcp, model identity, harness-path, the native-only rule, effort by role, and residual risks.
- **Payload:** `.claude/agents/explorer.md` is covered by the `.claude/agents` root.
- **Secrets and local state:** no real secrets, personal paths or emails in the scoped files; the only hits are scanner regexes and fake test fixtures. No `.tasks/` or receipt files are committed.

Verdict: FAIL