I couldn't run anything this time either. The sandbox needed approval for every step: copying or cloning the repo, any `python3` beyond `--version`, the focused tests, and `HOME=<fake> claude --help`. So I haven't run the tests, and everything below comes from reading HEAD `a9e1614`, which still contains R3 (`3a57fa7`).

Three of my four items look fixed at the real entry point:
- **Deletable/forgeable baseline:** fixed. `spawn-worker.sh` and `spawn-brain.sh` go through `execution_runner.py`, which holds the baseline in memory, and `finalize=True` flags a deleted or rewritten `.protected`.
- **Symlinks:** fixed. Both the link target and the content it points to are hashed.
- **Persistence locations:** fixed.
- **Hiding:** only partly fixed. `.git/info/exclude` and the skip-worktree/assume-unchanged flags are now covered. What's still open is item 3 below.

**Blocking issues**

1. **`scripts/execution_receipt.py:23`: R3 now protects `~/.claude.json`, which Claude Code rewrites constantly.**
   - **What goes wrong:** Claude Code stores live state in that file (start counts, per-project last session ID and cost, cached flags). The contract-9 `claude -p` worker rewrites it itself, and so does any interactive Claude Code session open during a run.
   - **Failing input:** any real Claude worker run, or any provider run while the orchestrator's Claude Code session is open. Either one produces `<protected:~/.claude.json>` and the scope check fails. That's the same false failure that sank T-071 attempt 1.
   - **Why the tests miss it:** the stub providers never write that file, and `tests/test-execution-spec.py:431` locks the entry in. I couldn't run `claude` under a fake HOME to show the write, so this rests on how Claude Code is known to behave.
   - **Fix:** remove it from the snapshot and keep the `Edit`/`Write(~/.claude.json)` deny entries. Or hash only the keys that matter for security (`mcpServers`, `projects.*.mcpServers`, `projects.*.allowedTools`).
   - **Related:** `scripts/execution_runner.py:328` takes a second snapshot instead of reusing `capture_before`'s. Any write landing between the two snapshots also raises the `.protected` tamper violation.

2. **`scripts/execution_receipt.py:146-147` and `:153-154`: if `~/.claude` or `~/.claude/projects` is a symlink, the allowlist is bypassed.**
   - **What goes wrong:** `_protected_digest` follows the link and hashes the whole tree, including `sessions/`, `plugins/` and transcripts.
   - **Failing input:** fake HOME where `~/.claude -> /dotfiles/claude`; write `~/.claude/sessions/1.key` during the run. Result: `<protected:~/.claude>`. With a symlinked `projects/`, the Claude worker's own transcript writes cause `<protected:~/.claude/projects>`.
   - **Fix:** for those two roots, record only the link target (`os.readlink`). The allowlisted files are already hashed through the link.

3. **`scripts/execution_receipt.py:79` (with the home file list at `:141`): ignore files can still hide work from the scope check.** This is the unfinished part of my item 4.
   - **Failing input:** with `write_scope: ["README.md"]`, the worker uses the allowed `Write` tool, so no Bash is needed. It creates `scripts/.gitignore` containing `.gitignore` and `json.py`, plus a `scripts/json.py`. That `.gitignore` hides itself, so `ls-files --others --exclude-standard` returns nothing and the scope check passes. The next `python3 scripts/*.py` run (including `execution_runner.py` itself) then imports the planted `json.py`.
   - **Same hole through git's global ignore file:** a worker can append to `~/.config/git/ignore` with Bash. Only `.config/git/config` is hashed.
   - **Fix:** compare the set of ignored untracked files before and after the run (`ls-files --others --ignored --exclude-standard`, skipping `.tasks/`). At minimum, flag any new ignored `.gitignore` and hash `~/.config/git/ignore` and `~/.config/git/attributes`.

Verdict: FAIL