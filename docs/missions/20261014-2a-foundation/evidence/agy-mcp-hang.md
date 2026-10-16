# agy headless hang: an editor-installed MCP server never finished starting

Recorded 2026-10-16 from the owner's own investigation, agy 1.4.0. Supersedes the earlier "agy hangs everywhere" entry in `progress-archive/2026-10-14_15.md` (that entry's guess, folder trust, was wrong).

## Cause

- Headless `agy -p` hung because an MCP server installed by an editor extension never finished starting. This is a known bug: google-antigravity/antigravity-cli#1087.
- Print mode waits for every configured MCP server to start, then reports an empty SUCCESS with 0 tokens (0 turns), whatever the status says.
- Folder trust and `--dangerously-skip-permissions` were not the cause.

## Fix and measurement

- The owner removed those servers (GitKraken from GitLens, Google Cloud data tools).
- After that, this command returned "OK" with `num_turns` 1:
  `agy -p "Reply with OK only." --model gemini-3.8-flash-low --output-format stream-json --print-timeout 2m --dangerously-skip-permissions < /dev/null`
- Total run time went from 39 s to 7 s.

## Caveat that shapes the probe

A removed server came back once when its extension updated itself. So `probe-seat.sh` must read the CLI's MCP server list on every run, and a non-empty list for agy is reported to the owner (names only, never config contents).

## Our earlier probes (for context)

On 2026-10-15 and 2026-10-16 our probes of `agy -p` with `--mode plan` (stdin closed, 60 to 100 s caps, with and without `--model`) printed "print timeout ... turn in progress; returning partial output" and nothing else, in the repo and in a fresh folder. That is the same symptom.
