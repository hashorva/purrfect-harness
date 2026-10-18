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
- Tests run in an isolated scratch tree; they never modify or depend on the live tree.
- An adapter argv change requires a new provider contract version; the golden argv test enforces it.

## Mission rules

When a mission is active, read its task, `PROGRESS.md`, and `features.json` before
editing; also inspect `git log --oneline -10` and establish a green baseline.
Complete one assigned `passes: false` feature per worker session. A worker task's
allow-list and iteration policy are binding; never edit `features.json` as a worker.
End cleanly: run the task's checks, commit the scoped change, and report the result in your final message. Workers do not write PROGRESS.md; the orchestrator records each run from its receipt.

Local CLI brain and worker runs must leave their receipt under `.tasks/receipts/`.
Before a feature is accepted or a mission gate/status is advanced, run
`bash scripts/verify-mission.sh` for the mission. Only the orchestrator may accept a
feature after that current verification; workers report evidence but have no
feature-acceptance authority.

Never write to the repository while a worker or brain run is in progress; never start a duplicate long-running check.
