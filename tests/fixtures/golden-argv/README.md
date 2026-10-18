# Golden provider argv

Recorded files are immutable: an argv change adds contract N+1 and four new provider files, then bumps `PROVIDER_CONTRACTS_V3` and `CURRENT_PROVIDER_CONTRACT`.
`MANIFEST.json` pins each file's sha256 and contract; `scripts/check-golden-argv.py` (CI, against `origin/main`) refuses any modified, deleted or renamed recorded file and allows only new `<provider>-v<N>.json` files above the newest recorded contract.

Fixture specs use repo `/golden/repo`, prompt `GOLDEN PROMPT`, and write scope `scripts/*`; versions 2–9 use schema 3 and contract N, while v1 uses schema 2 without a contract field. Codex also has a case with `.agents/skills/*` in scope. Provider models are `gpt-5.5`, `golden-claude`, `golden-agy-high`, and `golden-agent-high`; effort is high and speed is unknown except agent standard.

Historical-equals-current: all 34 files except `claude-v9.json` and `codex-v9.json`, which differ.

Historical forms: Claude v8 at `98d628a`; Claude v9 and Codex v9 at `ed1fa71`.

Temporary drift windows: Codex contracts 2–8 in `6ec695c..cccdb43` (T-071/T-115), and Claude contracts 1–7 in `98d628a..ed1fa71`.
