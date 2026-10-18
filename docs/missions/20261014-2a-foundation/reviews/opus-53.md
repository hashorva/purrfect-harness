I couldn't run the Python tests. Cloning, copying and running `python3` all hit permission prompts that weren't approved, so I left the original untouched. Everything below comes from reading the code and tracing inputs by hand, with no executed evidence.

**Blocking**

1. **`scripts/fleet_state.py:441-442`: `resolve_v2` ignores the seat's frozen family when the seat key matches a registry seat.** The family check in `validate_fleet_v2_seat` (`fleet_state.py:295-296`) accepts any family that some seat of the door's provider has. But if the fleet seat's name matches a registry seat on the same provider, resolution uses that registry seat's families and never looks at `spec["family"]`.
   - **Failing input:** a v2 binding `"claude.premium": {"family":"opus","effort":"high","doors":["claude"],"speed":"unknown"}` with Claude aliases `[opus,sonnet,haiku,fable]`.
   - **What happens:** validation passes, because `(claude, opus)` comes from `brain`. Resolution then uses `("sonnet",)` from the registry's `claude.premium` and returns `sonnet`. Before T-053 it returned `opus`.
   - **Second example:** `"agy.premium": {"family":"flash","doors":["agy"]}` resolves to `gemini-4-argon-high` through the Flash-pool door.
   - **Effect on frozen fleets:** a v2 fleet frozen before this change with such a seat now drifts to a different family than the one approved. `freeze-v2` also pins a resolution that contradicts the seat's own `family`.
   - **Current fleet:** `docs/missions/20261014-2a-foundation/fleet.json` is not affected today, because every seat key there has the same family as its registry seat.
   - **Fix:** take the registry tuple only when `spec["family"]` is in it. Otherwise fall through to the existing `next(...)` branch. The intended case still works: a frozen `argon` seat moves to `nova` when the registry lists `["agy","nova","argon"]`.

2. **`schemas/fleet-inventory.schema.json:9`: the family pattern ends in `\Z`, which only Python understands.** Draft 2020-12 patterns use ECMA-262 regex. In ECMA-262, `\Z` either fails to compile in `u` mode (ajv's default), so the schema won't load, or it means a literal `Z`.
   - **Failing input:** in a non-`u` ECMA validator, family `"argon"` fails, so every real inventory is rejected, while `"argonZ"` passes.
   - **Scope:** `harness-manifest.json:67,118` ship this schema to consuming repositories, so it isn't only checked by the in-repo Python validator.
   - **Fix:** the repo already has a portable idiom that also blocks a trailing newline: `(?![\s\S])` in `schemas/worker-output.schema.json:13`. The test in `tests/test-fleet-state.py` that pins the pattern string would need to change along with it.

**Inputs that held up:**
- **Name tricks:** `not-`, `-not-` and `NOT-` prefixes; `argonx`; Cyrillic look-alike letters.
- **Lookalike separators:** `:`, `/` and `+` used where a dash would go.
- **Case and fast variants:** uppercase ids, and `-fast`/`-FAST` variants, which stay excluded but still count as listed.
- **Family ranking:** a lower-ranked family can't beat a higher one.
- **Unlisted models:** an `unlisted` model can't be chosen for its own seat.
- **Ties:** ties are decided by the provider's own list order, which R1 kept on purpose.
- **Existing seats:** they resolve exactly as before, including `brain` on the agy door to `claude-opus-5-5-high`.
- **Secret-shaped names:** both the registry regex and the Python validator reject secret-shaped family names and a trailing newline.

**Not blocking, all present before T-053:**
- **Vendor prefixes:** any vendor prefix plus the family token matches, so `evil-argon-99-high` would outrank `gemini-4-argon-high`.
- **Unicode digits:** `model_rank` crashes on a digit like `²` (`int()` raises). Only the Codex cache can supply such an id.
- **Mismatch in hand-edited files:** `validate_inventory` doesn't check that a seat's model actually belongs to its family.

Verdict: FAIL