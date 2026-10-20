# 2B fleet proposal (for Gate 0; proposal only)

Source: the 2A native-only re-freeze of 2026-10-18 (`docs/missions/20261014-2a-foundation/fleet.json`, owner items A and B), plus two mid seats for the in-vendor ladder. Gate 0 replaces "copied" with a fresh probe: run `bash scripts/fleet-doctor.sh` (no ERROR line) and `bash scripts/fleet-inventory.sh`, then freeze.

## Rules

- Native-only: every model runs only on its own vendor's quota. claude: Opus, Sonnet, Haiku. codex: Sol, Terra, Luna. agy: Argon, Flash. cursor: Composer, Grok. No agy Opus/Sonnet/GPT-OSS seat; no door resolves another vendor's family (2A T-100).
- Effort by role: brain high; reviewers medium; economy workers medium; premium and mid workers medium.
- Brain fallbacks run on their own quota: `brain_argon` on the agy-argon pool, `brain_codex` on the openai pool. A fallback is a pool decision of the quota gate, never a silent move: the run's spec records the seat.
- Premium seats are reviewers by default. They work as workers only (1) one rung up after a logic failure (F005 ladder), or (2) on a guard task where the planner writes the reason in the task's Plan tags.
- Mid seats (`claude.mid` Sonnet, `codex.mid` Terra) are frozen now so the ladder is approved at Gate 0. `spawn-worker.sh --tier` knows only `economy` and `premium` today, so mid seats become dispatchable with F005. If `validate-fleet` refuses them, freeze without them and add them in F005 by an owner-approved drift event.

## Seats

| Seat | CLI | Family | Door | Pool | Effort | Speed | Role |
| --- | --- | --- | --- | --- | --- | --- | --- |
| brain | claude | opus | claude | anthropic | high | unknown | planner, gate runs |
| brain_argon | agy | argon | agy-argon | agy-argon | high | unknown | planner fallback 1 |
| brain_codex | codex | sol | codex | openai | high | unknown | planner fallback 2 |
| claude.premium | claude | opus | claude | anthropic | medium | unknown | reviewer (guard/safety reviews), rung 3 |
| claude.mid | claude | sonnet | claude | anthropic | medium | unknown | rung 2 worker |
| claude.economy | claude | haiku | claude | anthropic | medium | unknown | economy worker |
| codex.premium | codex | sol | codex | openai | medium | unknown | reviewer, rung 3 |
| codex.mid | codex | terra | codex | openai | medium | unknown | rung 2 worker |
| codex.economy | codex | luna | codex | openai | medium | unknown | economy worker |
| cursor.premium | cursor-agent | grok | cursor-grok | cursor | medium | standard | reviewer, rung 2 |
| cursor.economy | cursor-agent | composer | cursor-composer | cursor | medium | standard | economy worker |
| agy.premium | agy | argon | agy-argon | agy-argon | medium | unknown | reviewer, rung 2 |
| agy.economy | agy | flash | agy | google | medium | unknown | economy worker |

## Bindings JSON for `freeze-v2` (`.tasks/gate0-2b-bindings.json`)

```json
{
  "brain": {"family": "opus", "effort": "high", "doors": ["claude"], "speed": "unknown"},
  "brain_argon": {"family": "argon", "effort": "high", "doors": ["agy-argon"], "speed": "unknown"},
  "brain_codex": {"family": "sol", "effort": "high", "doors": ["codex"], "speed": "unknown"},
  "claude.premium": {"family": "opus", "effort": "medium", "doors": ["claude"], "speed": "unknown"},
  "claude.mid": {"family": "sonnet", "effort": "medium", "doors": ["claude"], "speed": "unknown"},
  "claude.economy": {"family": "haiku", "effort": "medium", "doors": ["claude"], "speed": "unknown"},
  "codex.premium": {"family": "sol", "effort": "medium", "doors": ["codex"], "speed": "unknown"},
  "codex.mid": {"family": "terra", "effort": "medium", "doors": ["codex"], "speed": "unknown"},
  "codex.economy": {"family": "luna", "effort": "medium", "doors": ["codex"], "speed": "unknown"},
  "cursor.premium": {"family": "grok", "effort": "medium", "doors": ["cursor-grok"], "speed": "standard"},
  "cursor.economy": {"family": "composer", "effort": "medium", "doors": ["cursor-composer"], "speed": "standard"},
  "agy.premium": {"family": "argon", "effort": "medium", "doors": ["agy-argon"], "speed": "unknown"},
  "agy.economy": {"family": "flash", "effort": "medium", "doors": ["agy"], "speed": "unknown"}
}
```

## Policy JSON (`.tasks/gate0-2b-policy.json`)

```json
{"billing_classes": ["included"], "fast": false, "no_zdr": "forbid"}
```

## Freeze command (after the owner approves, mission status `approved`)

```bash
bash scripts/fleet-doctor.sh
bash scripts/fleet-inventory.sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/fleet_state.py freeze-v2 \
  --mission-dir docs/missions/20261018-2b-autonomy \
  --inventory .tasks/fleet-inventory.json \
  --bindings .tasks/gate0-2b-bindings.json \
  --policy .tasks/gate0-2b-policy.json \
  --approved-by Zamir --approved-at "<UTC RFC3339 of the approval>"
```

Then `validate-fleet` must exit 0, and every seat's `approved_resolution` must name its own vendor (no cross-vendor resolution).

## Review pairing: a different vendor than the worker

| Worker vendor (seats) | Allowed reviewers (all medium) | Default |
| --- | --- | --- |
| claude (Haiku, Sonnet, Opus) | Sol (codex.premium), Grok (cursor.premium), Argon (agy.premium) | Sol |
| codex (Luna, Terra, Sol) | Opus (claude.premium), Grok, Argon | Grok |
| cursor (Composer, Grok) | Opus, Sol, Argon | Argon |
| agy (Flash, Argon) | Opus, Sol, Grok | Sol |

- Guard and safety code (dispatch policy, verifier, receipts, sandbox profile, lane admission, merge) is reviewed by Claude Opus. Such a task is therefore never given to a Claude worker; the planner marks it `guard` in Plan tags.
- When a reviewer's pool is refused by the quota gate, the next allowed reviewer in the row is chosen. If none is allowed, the task waits; it is never reviewed by its own vendor.

## Planner and worker vendors

- The planner (brain, Opus) and a Claude worker share a vendor. That is allowed: the planner writes the task and the oracle but does not review the run. The rule applies to reviewer versus worker.
- When `brain_argon` or `brain_codex` plans, the same reviewer table applies.
- Pairs that pass the rule by construction: Opus review of codex, cursor or agy work; Sol review of claude, cursor or agy work; Grok review of claude, codex or agy work; Argon review of claude, codex or cursor work. Forbidden pairs (same vendor): Opus on Haiku/Sonnet work, Sol on Luna/Terra work, Grok on Composer work, Argon on Flash work.
