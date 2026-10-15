# Evidence: Codex --add-dir for .agents/ (probe P-1, 2026-10-15)

Question: does adding `--add-dir <repo>/.agents` let a Codex `workspace-write` worker write under
`.agents/`, the same way `--add-dir <repo>/.git` lets it commit? (Limit found at T-006 attempt 2.)

Method: two fresh `git clone --no-hardlinks` copies of the live repository under `mktemp -d`
(outside the repository), one tiny `codex.economy` call each (gpt-6-luna, effort low, included quota):

- **a (with the flag):** `codex exec -C $P/a -s workspace-write --add-dir $P/a/.git --add-dir $P/a/.agents -m gpt-6-luna -c 'model_reasoning_effort="low"' "Create .agents/probe.txt containing the line probe, then run: git add .agents/probe.txt && git commit -m probe. Reply DONE or the exact error."`
- **b (control, no `--add-dir .agents`):** the same command with only `--add-dir $P/b/.git`.

Results (verbatim where quoted):

- a: exit 0; the worker replied `DONE`; `git log --oneline -1 -- .agents/probe.txt` shows commit `a40b0c8` `probe`.
- b: exit 0 (the CLI ran); the worker replied `zsh:1: operation not permitted: .agents/probe.txt`; no commit touches `.agents/probe.txt` (empty log).

Conclusion: **PASS.** The `.agents/` write limit of the Codex `workspace-write` sandbox is lifted by
`--add-dir <repo>/.agents`. Task T-013 (adapter adds that flag only when the allow-list includes
`.agents/`) can proceed. Not tested: other protected paths (`.codex`, `.claude`), or whether the flag
widens anything beyond `.agents/` (T-013's Architect review must check the argv).
