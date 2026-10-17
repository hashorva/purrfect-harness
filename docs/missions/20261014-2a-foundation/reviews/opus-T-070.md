Verdict below is **FAIL**. Two limits first: the sandbox wouldn't let me make the scratch clone or run any checks, and I was limited to `claude --help`. So nothing here was run. It all comes from reading the code and the CLI help text.

**Exact argv (v8; worker and brain are identical):**
`claude -p <prompt> --output-format stream-json --verbose --strict-mcp-config --permission-mode bypassPermissions --disallowedTools "Bash(rm -rf *),Bash(git push*),Bash(git reset --hard*),Bash(git checkout -- *),Bash(git clean -f*)" --model <m> --effort <e>`

There are no credits or fast flags. The prompt comes before the two flags that take a list of values (`--disallowedTools`, `--mcp-config`). `claude --help` confirms that `--disallowedTools` takes a comma- or space-separated list and that spaces inside parentheses are fine, as in its own example `"Bash(git *) Edit"`. So the pattern syntax is accepted.

**Blocking issues**

1. **`scripts/execute_provider.py:13`: the deny-list misses most of what the owner required.** The commit matches T-070's five patterns exactly, but these get through:
   - **`rm`:** `rm -fr /x`, `rm -Rf /x`, `rm -r -f /x` and `rm --recursive --force /x` all miss `Bash(rm -rf *)`.
   - **`git push` to main:** `git -C . push origin HEAD:main` misses `Bash(git push*)`, because the command doesn't start with `git push`. So does `git -c x=y push --force origin main`.
   - **`git reset --hard`:** `git -C . reset --hard` misses.
   - **`git clean`:** `git clean -df` and `git clean -xdf` miss `Bash(git clean -f*)`.
   - **Other force flags:** `git checkout -f`, `git branch -D main` and `git stash clear` have no pattern.
   - **`chmod -R`, `sudo`, `curl … | sh`:** no pattern exists for any of them.

2. **`scripts/execute_provider.py:64` with `scripts/execution_receipt.py:69-72`: writes outside the workspace are allowed and the scope check can't see them.**
   - `bypassPermissions` removes the CLI's working-directory limit on file tools, and there is no `Edit(...)` or `Write(...)` deny rule.
   - The scope check only sees git-visible files: the tracked diff plus untracked files that aren't ignored.
   - So writes to `~/.claude/settings.json`, `~/.zshrc`, `.git/hooks/pre-commit` or `.git/config` all pass with no scope violation. For example, a `git config alias.p push` written into `.git/config` makes `git p origin main` get past the deny-list.

3. **`scripts/execute_provider.py:62-65`: older contract versions now get `bypassPermissions` without `--strict-mcp-config`.**
   - The validator still accepts schema v1/v2 specs and v3 specs with contract 2–6 (`scripts/execution_spec.py:25,127`).
   - Such a spec, saved with `execution_spec.py persist --input` and launched with `execute_provider.py`, produces `claude -p … --output-format json --permission-mode bypassPermissions --disallowedTools …`.
   - That run has every personal MCP connector loaded (Gmail, Drive, Calendar, Notion) and auto-approved.
   - The tests lock this in at `tests/test-execution-spec.py:181` (contract 1) and `:350-353` (contract 6).
   - It also changes the argv of frozen historical contracts without a version bump.

4. **The deny-list tests don't actually guard its contents.**
   - `tests/test-execution-spec.py` and `tests/test-execution-integration.py` compare against the imported `CLAUDE_DISALLOWED_TOOLS`, so they always agree with whatever the constant says.
   - `tests/run-tests.sh:404` only greps for `Bash(rm -rf`.
   - Replacing the constant with `"Bash(rm -rf *)"` would keep the whole suite green. Only T-070's one-off check command checks all five patterns, and it isn't part of the suite.

**Unverified:** I couldn't test whether this CLI version (2.1.301) still applies `--disallowedTools` under `bypassPermissions`.

**Checked and fine:** a task field can't drop `--strict-mcp-config` or inject `--mcp-config`. `validate()` requires the spec's fields to match the schema exactly (`scripts/execution_spec.py:98-104`), so `mcp_config` can't get into a saved spec.

Verdict: FAIL