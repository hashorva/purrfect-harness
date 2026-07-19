---
title: Model Routing Policy
version: 1.0.0
updated: 2026-07-19
---

# Model Routing — the right brain for each task

The whole point: match model quality to task complexity, so every mission gets
the highest quality at the lowest price. Criteria are durable; prices are not.
Prices live ONLY in the dated appendix. When they change, bump the appendix
date — never let a stale number pose as current.

## The four routing criteria (apply in order)

1. **Task horizon.** How many steps before a human checks the output?
   Short + well-scoped → models are interchangeable, cheapest wins.
   Long autonomous chains → capability gaps widen; premium earns its price.
2. **Cost of a silent error.** Caught immediately in review → cheap is fine.
   Ships unattended to a live product → calibrated caution beats raw IQ.
3. **Verifiability.** Tests/steps exist → cheap model + verification beats
   expensive model without it. No test possible (architecture, ambiguity) →
   raw intelligence matters most; this is premium territory.
4. **Volume.** Run hundreds of times → per-token price dominates, quality
   differences wash out. Always economy tier.

Rule of thumb stays: **judgment up, volume down.**

## Orchestrator policy

**Primary (choose ONE per mission, at GATE 0):**

| Brand | Invocation | Notes |
|---|---|---|
| Anthropic | `claude --model opus` — effort high/extra | Alias resolves to the latest Opus on the plan (today: Opus 4.8). Carries the ENFORCED layer (.claude/settings.json, rules, code-reviewer subagent). |
| OpenAI | `codex -m gpt-5.6-sol -c model_reasoning_effort="high"` | Verify flags with `codex --help` first (CLIs change fast). Meets the orchestrator contract in GUIDANCE-ONLY mode — no enforcement layer binds it. |

Both are best-in-class per brand and included in current subscriptions.
**Alias doctrine:** invocations use aliases where the CLI supports them, so a
new flagship (e.g. Opus 5) is picked up automatically. The orchestrator MUST
resolve and log the concrete model + version in PROGRESS.md at GATE 0. A model
alias is never allowed to change resolution MID-mission: if the vendor ships a
new flagship while a mission is open, finish on the pinned resolution, adopt
the new one at the next GATE 0. Between missions, a deliberate bump of a
pinned name in this file is a PATCH release of the harness.

**Escalation to Fable 5 (API credits — costs real money):**

Self-reported confidence is NOT a trigger — models are poorly calibrated about
their own uncertainty. Fable engages only on observable evidence or explicit
declaration:

- **Evidence triggers** (any one, noted in PROGRESS.md):
  - orchestrator plan or diff failed human/gate review twice on the same feature
  - mission stalled: same feature `passes: false` after 2 escalated worker attempts
  - features.json churn: orchestrator restructured the list twice in one mission
- **Task-class triggers** (declared at GATE 0 in GOAL.md):
  - architecture decisions on a LIVE product (payments, auth, data model)
  - cross-repo or cross-product migrations
- **Manual override:** the human may start any mission directly on Fable
  (CLI `claude --model fable` or VS Code extension). Record `orchestrator:
  fable (manual)` in GOAL.md — it is a fleet decision like any other.

Escalation is one mission-scope decision, not per-message; de-escalate at the
next GATE 0 unless triggers persist.

## Worker tiers (defaults; Fleet table in GOAL.md wins)

- **Economy (default):** Cursor Composer (`--model composer`), Codex worker
  profile, Gemini Flash tier, `claude --model haiku`.
- **Premium workers:** `claude --model sonnet` (latest Sonnet — today Sonnet 5:
  near-flagship agentic coding at mid-tier price), Codex `-m` flagship high
  effort, Gemini Pro tier.
- Escalation between worker tiers: per dispatch-worker skill — only after a
  CAPABILITY failure, one tier at a time, `escalated: true` in frontmatter.

## Appendix — price snapshot (verified 2026-07-19, DECAYS FAST)

API list $/Mtok in/out: Composer 2.5 0.50/2.50 · Grok 4.5 2/6 · Gemini 3.5
Flash 1.5/9 · Sonnet 5 2/10 intro (3/15 from Sep 1) · Gemini 3.1 Pro 2/12 ·
GPT-5.6 Terra 2.5/15 · Opus 4.8 5/25 · GPT-5.6 Sol 5/30 · Fable 5 10/50.
Subscriptions: Opus+Sonnet in Claude Pro; Sol (medium effort) in ChatGPT Plus;
Fable = Max-only since 2026-07-20, Pro gets one-time $100 credit then API
rates. Tokenizer caveat: Sonnet 5 emits ~30% more tokens; Anthropic tokens run
~15% smaller than OpenAI's — sticker prices are not directly comparable.
