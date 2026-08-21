# Purrfect Harness — Repository Instructions

This repository distributes the Purrfect Harness: mission procedures, skills, and
safe install/update tooling for other repositories. It is not a consuming product.

## Scope and safety

- Keep distribution ownership in `harness-manifest.json`; install, update, sync, and
  release validation must consume it rather than parallel hand-maintained lists.
- Never overwrite a consuming repository's project-owned files. In particular,
  `AGENTS.md`, `AGENTS.md.template`, foreign skills, and mission instances belong to
  the consumer.
- The consumer skeleton is `docs/templates/AGENTS.md.template`. Do not put consumer
  placeholders in this harness repository's `AGENTS.md`.
- Do not commit secrets or alter Git tags/remotes without explicit user direction.

## Checks

- Run `shellcheck scripts/*.sh tests/*.sh`, JSON validation, and `bash tests/run-tests.sh`.
- A normal install/update requires the manifest's release tag on `HEAD`. Use
  `--dev` (or `--allow-untagged`) only for explicit local development/smoke work.

## Mission rules

When a mission is active, read its task, `PROGRESS.md`, and `features.json` before
editing. A worker task's allow-list is binding; never edit `features.json` as a
worker. Append the required mission progress record after completing the task.
