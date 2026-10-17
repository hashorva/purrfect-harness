I found no input that gets the driver to answer anything other than an exact folder-trust prompt for the run's own workspace. The no-wrong-answer property held. But the "unknown prompt = stop (exit 3)" owner rule can be broken with concrete inputs. I couldn't run anything: every python3, cp and git clone call needed approval. So everything below comes from tracing the code by hand, not from executed tests.

**Blocking 1: after one trust answer, later `[y/n]` prompts are no longer treated as prompts.** `scripts/drive_cli_rules.py:288-299, 309-314`, with `scripts/drive-cli.sh:175`
- After the trust answer, `ANSWERED_TEXT` holds that pane for the rest of the run and is never reset.
- When the old trust text is no longer on screen (a TUI redraws the screen, or it has scrolled away), `_answered_residual` falls back to the longest *suffix* of the answered pane that appears anywhere. That suffix is `[y/n] ` or ` [y/n]`, so it removes the new prompt's own `[y/n]` marker before `match_pane` sees it.
- Failing input:
  - Workspace `/tmp/ws`. The answered pane is `Do you trust the files in this folder?\n/tmp/ws\n[y/n] `.
  - The CLI then clears the screen and shows `Unknown prompt? [y/n] `. This is the spec's own oracle string from T-066.
  - The leftover text `Unknown prompt? ` matches no NEVER rule, danger word or prompt pattern, so the decision is `wait`.
  - Result: exit 4 after 90 s instead of exit 3. If the CLI's screen keeps changing (a spinner or timer), it never exits.
- `Overwrite config.json? [y/n]` and `Apply patch to src/app.py? [y/n]` fail the same way.
- The tests only cover a later prompt that also contains a NEVER word (`git push`), which is why this passed.

**Blocking 2: numbered-menu prompts are never detected as unknown prompts.** `scripts/drive_cli_rules.py:35` (and the list at 23-39)
- The numbered-option pattern starts with `^` but is compiled without `re.M`. It therefore only matches at the very start of the pane, and it requires a `]`.
- There is no pattern for `1. Yes` style menus. That is the format the target provider CLIs use for their approval prompts.
- Failing inputs, all with no answer yet:
  - `Do you want to proceed?\n❯ 1. Yes\n  2. No`
  - `Choose:\n[1] Yes\n[2] No`
  - `Overwrite config.json? y/N`
- Each one is classified `no_prompt`/`wait`, giving exit 4 (or an endless run) instead of exit 3.

What I tried that did not get a wrong answer through:
- Zero-width, bidi, line-separator, control and escape characters: all rejected up front.
- Combining marks, homoglyphs, NFD paths, case changes and tabs: the allow check is an exact, case-sensitive full match of the whole pane against the template, so these only cause a stop or a wait.
- The 80-column wrap: tmux runs at 220 columns, and `capture-pane -J` rejoins any lines tmux wraps. A CLI that hard-wraps the path just fails the exact match.
- Very long workspace paths.
- Prompts that echo the answered text, a second identical trust prompt, and the earlier answer still in the pane: a second answer is always turned into a stop.
- Fake "Pane is dead" lines.
- Shell injection through the workspace path or the transcript-dir variables: all quoted, passed as argv or environment.

Verdict: FAIL