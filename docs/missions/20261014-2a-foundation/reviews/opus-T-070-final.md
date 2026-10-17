I'm reporting one blocking issue. I couldn't run the proof-of-concept or the focused tests: every `python3 <script>`, `git clone` and `cp` needed approval in this mode, and only `python3 --version` ran. So the finding below comes from reading the code, not from a run. The unrun proof-of-concept is at `/private/tmp/claude-501/-private-var-folders-nz-r359d1z15512kjwfjl14ypv00000gn-T-tmp-ibomIAf4ja-repo/09d43ca8-e1be-460e-832f-20a8e29a4cf2/scratchpad/poc/drive.py` if you want to approve it.

**Blocking: the new module-shadowing guard (item 3) can be bypassed by switching to compiled Python files**

- **Where:** `scripts/execution_receipt.py:96-103` (`_is_stdlib_shadow`) and `scripts/execution_receipt.py:122` (`_is_harness_ignored`).
- **Cause:**
  - The guard only matches names ending in exactly `.py`, and only under `scripts/` and `tests/`.
  - Line 122 then always drops `*.pyc` files and anything in `__pycache__` from the change list, so they never show up as changes or violations.
  - Python still loads those files. Setting `PYTHONDONTWRITEBYTECODE=1` stops Python writing them, not reading them. `routing-data.jsonl:71` records a stray `scripts/__pycache__/ledger.cpython-314.pyc` actually being loaded.
- **Failing inputs** (worker scope `scripts/**`):
  1. **`scripts/json.pyc`:** the worker compiles any module to that name. Line 122 drops it, so the receipt shows no changes and scope passes. The next `spawn-worker.sh:246` run (`python3 scripts/execution_runner.py`) hits `import json` at `execution_runner.py:4`, with `scripts/` first on the import path, and runs the worker's code inside the orchestrator.
  2. **`uuid.pyc` at the repo root:** the guard never looks at the root. `spawn-worker.sh:228` runs `python3 -c 'import uuid; print(uuid.uuid4())'` from the repo root, where the current directory is first on the import path. The worker's code runs and chooses the RUN_ID. The same applies to the `import json` one-liners at `spawn-worker.sh:204-234` and in `spawn-brain.sh`.
  3. **Poisoned cached bytecode:** the worker plants `scripts/__pycache__/execution_receipt.cpython-314.pyc` with a header copying the source file's timestamp and size. It is hidden, and the next run loads it in place of the real receipt code, so later receipts can be forged.
  4. **`scripts/json.cpython-314-darwin.so`:** this one does appear in the changed paths, but the guard doesn't match it, so the `scripts/**` scope passes. Python loads compiled extension modules before `.py` files, so it shadows `json`.
- **Fix:** treat any untracked `.pyc`, `__pycache__` or extension-module file outside `.tasks/` as a violation. This matches the repo's existing standing check `test ! -e scripts/__pycache__ && test ! -e tests/__pycache__`. Also make `_is_stdlib_shadow` match every suffix in `importlib.machinery.all_suffixes()` and include the repo root.

**Fixed at the real entry points (from reading the code)**
- **Baseline can't be deleted or forged:** in the normal runner path, `capture_before` keeps the baseline in memory and the receipt check at `:330-339` uses it. Deleting or rewriting the `.protected` file is flagged as tampering. Only the standalone `write-receipt.sh write` command still trusts the file on disk, and no spawn script uses it.
- **Symlinks:** handled at `:287-295` for symlinked `~/.claude` and `~/.claude/projects`.
- **Persistence locations:** the extended list of protected home files and `~/.claude` config is checked.
- **Hiding through ignore rules and index flags:**
  - Untracked files are now listed without honouring local ignore files, so `.git/info/exclude` and `core.excludesFile` can't hide anything (`:138`).
  - Any new or edited `.gitignore` is a violation (`:92`, `:262-268`, `:422`).
  - Skip-worktree and assume-unchanged flags are compared (`:252-259`).
- **Live noise:** `sessions/`, `plugins/` and project transcripts are never read; only `projects/*/memory` is hashed. In `~/.claude.json`, only the MCP and hooks settings are hashed (`:194-225`).

Not blocking: `evidence/claude-unlock-residual-risk.md:5` is out of date. It still says the runner passes `protected_before`, and that a symlinked `~/.claude` root is hashed by its content, when R8 now hashes only where the link points.

Verdict: FAIL