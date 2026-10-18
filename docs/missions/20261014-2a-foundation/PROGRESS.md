> **FROZEN** after the T-016 refresh (2026-10-19): mission 2A is closed and this file is no longer updated. Mission 2B status is generated (docs/missions/20261018-2b-autonomy/), not written here.

# Progress

## Current status (2026-10-19)
- **Mission:** 2A Foundation, status: done (GOAL.md), owner: Zamir; Gate 0 approved 2026-10-14, Gate 1 approved 2026-10-16, Gate 2: passed (2026-10-18).
- **Release:** released as 3.1.0 (merge commit f931ba5, tag v3.1.0); PR #4 merged into main; the Release workflow published purrfect-harness-v3.1.0.zip.
- **Features:** accepted (passes: true): F001, F003, F004, F005, F006, F007, F008, F009, F010, F011, F012, F013, F014, F015, F016, F017 (16 of 16); open (passes: false): none (F002 removed at Gate 0).
- **Roles:** Front Desk = Sonnet 5.5 (Claude Pro pool); brain = claude/opus, effort high (fallback seats brain_argon, brain_codex); reviewers and escalation workers = the .premium seats; workers = the .economy seats first.
- **Fleet (fleet.json, schema_version 2, billing_classes ["included"], fast false, no_zdr forbid):** agy.economy=agy/gemini-3.8-flash-medium/medium/unknown, agy.premium=agy/gemini-4-argon-medium/medium/unknown, brain=claude/opus/high/unknown, brain_argon=agy/gemini-4-argon-high/high/unknown, brain_codex=codex/gpt-6.1-sol/high/unknown, claude.economy=claude/haiku/medium/unknown, claude.premium=claude/opus/medium/unknown, codex.economy=codex/gpt-6-luna/medium/unknown, codex.premium=codex/gpt-6.1-sol/medium/unknown, cursor.economy=cursor/composer-2.5/medium/standard, cursor.premium=cursor/grok-4.7-medium/medium/standard.
- **Routing data:** routing-data.jsonl: 251 rows, 204 with an outcome: done 157, verify-failed 17, verify-passed-review-failed 16, scope-failed 6, failed 4, baseline-stopped 2, no-change 1, seat-limit 1.
- **Archives (read-only):** progress-archive/2026-10-14_15.md, progress-archive/2026-10-15_16.md, progress-archive/2026-10-16.md, progress-archive/2026-10-18.md, progress-archive/2026-10-18b.md, progress-archive/2026-10-18c.md, progress-archive/2026-10-19.md.
- **Carried to 2B (owner decisions; full text in progress-archive/2026-10-19.md):** (1) 2B Gate 0 sign-off; (2) promote the argv-contract rule (an adapter argv change needs a new provider contract) to AGENTS.md; (3) promote or drop the 2026-10-17 lesson proposal.
