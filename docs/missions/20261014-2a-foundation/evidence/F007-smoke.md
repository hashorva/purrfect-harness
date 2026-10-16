# Evidence: F007 real Mac smoke (2026-10-16)

On 2026-10-16, `bash scripts/fleet-doctor.sh --smoke --f007 --keep --dest .tasks/smoke/f007` exited 0 on this Mac. The kept scratch clone lives under `.tasks/smoke/f007/repo/`; runner summaries are in `.tasks/smoke/f007/*.out`, with per-worker reconstruct detail repeated in `.tasks/smoke/f007/reconstruct.out` and mission audit output in `.tasks/smoke/f007/audit.out`.

**Smoke mission:** `docs/missions/00000000-f007-smoke`  
**Clone base commit:** `7088dfecfe087ef13fc12c46224f1c94779d1025`  
**Doors exercised:** three (`claude`, `codex`, `cursor-agent` via provider `agent`) — four worker runs, one brain review run. **agy.economy was dropped** from this mission by the owner (2026-10-16); it was not dispatched and has no smoke receipt here.

## Worker runs

| Run ID | Seat | Provider | Model requested | Observed model (source) | Outcome | VerificationRecord | Ledger valid |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `590fbfeb-a989-4068-b91e-96841b69c2b9` | claude.economy | claude | haiku | claude-haiku-5-5 (observed) | completed | pass `206cb259b51143df98f83519adc9b5ba2f7a834ed4a21b2cc5961180e2091ea4` | yes |
| `61bc501b-c9fe-48f8-8d05-07c89c47ba97` | codex.economy | codex | gpt-6-luna | **unknown** (unknown) | completed | pass `cab8347e1e0f0d92e3a16c3e5a6abd5134d255d4cfe7126e942ee2691a00858e` | yes |
| `8030f5d4-5c6e-4f3e-a1fa-7585a02083b9` | cursor.economy | agent | composer-2.5 | Composer 2.5 (observed) | completed | pass `f99971b170b7c7c4658ff2863bd05a6f423c177750829ac40dee5ab2fa8c9d37` | yes |
| `714879f5-1a3c-4363-ae3c-5934736b5ccb` | cursor.premium | agent | grok-4.7-high (speed standard) | Grok 4.7 256K High (observed) | completed | pass `fa86abfdce4a00121f9e265fb065511d1e04442f8efff94253256467ca640332` | yes |

**Codex observed model:** The Codex worker's observed model is `unknown`. Its JSON output carries usage but no model name, so the receipt records `observed_model` with source `unknown` and value null. **F007 step 2** ("each has a non-unknown observed model, except cursor-agent runs") is **therefore NOT met for Codex as written** — the Codex exception in step 2 applies only to cursor-agent runs, not to Codex.

## Brain run

Brain review run id: `70f7ce27-cc1b-4d2c-a1c1-3d5dbc89dee5` (claude / opus, action review on the smoke mission). The brain receipt is under `.tasks/smoke/f007/repo/.tasks/receipts/`; it has no VerificationRecord (expected for this smoke).

## Mission audit

`bash scripts/verify-mission.sh docs/missions/00000000-f007-smoke` on the kept clone: **pass** (see `.tasks/smoke/f007/audit.out`: `VERIFY OK: docs/missions/00000000-f007-smoke`).

## What the human checks at Gate 2

1. Read `.tasks/smoke/f007/reconstruct.out` (or re-run `scripts/reconstruct-run.sh` on the kept clone with the four worker run ids above) and confirm spec, receipt, VerificationRecord, and ledger row for each worker run.
2. Compare observed models across the four workers against what each CLI is expected to report (see also `docs/missions/20261014-2a-foundation/evidence/cli-json-observation.md`).
3. Confirm no run used a `-fast` model and no **credits** billing door was used (resolved models are haiku, gpt-6-luna, composer-2.5, grok-4.7-high with speed standard where applicable).
4. Note that **agy is out of this mission** — only the three doors above were smoked.
5. Decide whether F007 step 2 should be amended or accepted with the documented Codex `unknown` observed model.
