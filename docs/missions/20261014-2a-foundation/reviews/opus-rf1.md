I couldn't execute anything. Every `python3` call needed approval, which wasn't given, so I didn't run the tests or any real-tmux probes, and the clone is untouched. Everything below comes from tracing HEAD `3cf5e34` by hand. Two drive-cli inputs still end in exit 4 instead of exit 3. No input I traced gets a wrong answer sent.

**(1) drive-cli: blocking**

- **Boxed numbered menus are not detected** (`scripts/drive_cli_rules.py:38-39`, `:44`).
  - The menu patterns require the line to start with whitespace or one of `>❯*•-`. The `?` pattern requires `?` at the very end of the line. A box border `│` blocks both.
  - Failing input (no trust answer needed):
    ```
    ╭────────────────────────╮
    │ Do you want to proceed?│
    │ ❯ 1. Yes               │
    │   2. No                │
    ╰────────────────────────╯
    ```
  - No NEVER rule, danger word, or `allow`/`approve`/`confirm` matches. The result is `no_prompt`/`wait`, so exit 4 after 90 s. If anything inside the box keeps changing (a timer or spinner), the run never exits.
  - This is the same failure type your last Opus review failed. Older Claude Code permission prompts (Ink-style boxes) are drawn this way, with options like `2. Yes, and don't ask again…` that contain none of those words.

- **After a redraw, `new_text` hides a later prompt's lines if they match the answered prompt** (`scripts/drive_cli_rules.py:305-319`, used at `:325-328`).
  - `new_text` drops any current line that is textually equal to a line of the answered trust pane, whether or not the original line is still on screen.
  - In tmux's alternate screen there is no scrollback, so `capture-pane -S -` cannot keep the old lines. The same happens after a `\e[3J` clear.
  - Failing input, workspace `/tmp/ws`:
    1. The CLI switches to the alternate screen (`\e[?1049h`) and prints `Do you trust the files in this folder?\n/tmp/ws\n[y/n] `.
    2. It is answered `y`.
    3. The CLI clears the screen (`\e[2J\e[H`) and prints `Overwrite config.json\n[y/n] `.
  - The new `[y/n]` line is matched against the answered one and dropped. `new_text` returns only `Overwrite config.json`, which matches nothing, so the result is `wait` and exit 4 (or no exit with a spinner).
  - Same outcome for `Do you trust the files in this folder?\n/tmp/ws/other\n[y/n]` after a redraw: only `/tmp/ws/other` is left, so `wait`.
  - It also happens when the identical trust prompt is shown again after a clear. The pane then equals the answered capture (`scripts/drive-cli.sh:138`), so `wait`.
  - The new real-tmux tests only cover the normal-screen case, where the scrollback keeps the old lines.

What held up:
- A second `[y/n]` prompt in the normal screen.
- Answers with and without the `y` echo.
- The same prompt repeated without a clear.
- Unboxed `1. Yes` / `[1] Yes` / `❯ 1.` / `y/N` menus.
- A CLI that prints a prompt and exits quickly is still caught at `scripts/drive-cli.sh:183`.
- A second answer is always turned into a stop.

**(2) T-053 `resolve_v2`: no blocking issue**

The frozen family wins unless it appears in that same seat's own registry family list on the same provider (`scripts/fleet_state.py:441-448`). In that one case the seat's ranked list applies, which is the argon→nova upgrade that both the spec and the previous review intended. I traced these bindings:
- `claude.premium` with `opus` resolves to `opus`.
- `agy.premium` with `flash` resolves to `gemini-3.8-flash-high`.
- `brain` (`opus`, doors `agy` then `claude`) resolves on agy to `claude-opus-5-5-high`.

`freeze-v2` freezes what `resolve_v2` returns. Every seat in `harness-registry.json` lists a single family, so with the current registry the frozen family always wins.

Verdict: FAIL