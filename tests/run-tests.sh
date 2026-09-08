#!/usr/bin/env bash
# run-tests.sh — end-to-end test of the harness contracts.
# Creates a throwaway git repo, installs the harness into it, asserts the
# collision rules, then exercises the update path. Run from the kit root.

set -euo pipefail

HARNESS="$(pwd)"
[ -f "$HARNESS/CHANGELOG.md" ] || { echo "Run from the kit root."; exit 1; }

FAIL=0
check() { # check <description> <command...>
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "  ok   : $desc"
  else echo "  FAIL : $desc"; FAIL=1; fi
}

# Documentation is a public entry point for the harness protocol. Keep these checks
# deliberately narrow: each catches a previously reproduced false operational claim.
check_documentation_truth() { # check_documentation_truth <repository-root>
  local root="$1"

  grep -Fq 'orchestrator may accept a' "$root/AGENTS.md" &&
    grep -Fq 'bash scripts/verify-mission.sh' "$root/AGENTS.md" &&
    grep -Fq 'Workers never edit it. Only the orchestrator' "$root/docs/templates/AGENTS.md.template" &&
    grep -Fq 'current verification evidence' "$root/docs/missions/ORCHESTRATION.md" &&
    grep -Fq 'client permission configuration' "$root/README.md" &&
    grep -Eq 'client permission[[:space:]]+configuration' "$root/docs/missions/ORCHESTRATION.md" &&
    ! grep -Fqi 'ENFORCED layer' "$root/README.md" "$root/docs/missions/ORCHESTRATION.md" &&
    grep -Fq 'legacy parent link such as' "$root/README.md" &&
    ! grep -Fq 'existing symlinks are left alone' "$root/README.md" &&
    grep -Fq 'untagged development baseline' "$root/CHANGELOG.md" "$root/docs/PUBLISHING.md" "$root/docs/RELEASING.md"
}

documentation_truth_negative() { # documentation_truth_negative <repository-root>
  local root="$1" fixture
  fixture="$(mktemp -d)"
  mkdir -p "$fixture/docs/missions" "$fixture/docs/templates"
  cp "$root/AGENTS.md" "$fixture/AGENTS.md"
  cp "$root/README.md" "$fixture/README.md"
  cp "$root/CHANGELOG.md" "$fixture/CHANGELOG.md"
  cp "$root/docs/PUBLISHING.md" "$fixture/docs/PUBLISHING.md"
  cp "$root/docs/RELEASING.md" "$fixture/docs/RELEASING.md"
  cp "$root/docs/missions/ORCHESTRATION.md" "$fixture/docs/missions/ORCHESTRATION.md"
  cp "$root/docs/templates/AGENTS.md.template" "$fixture/docs/templates/AGENTS.md.template"
  perl -0pi -e 's/client permission configuration/ENFORCED layer/' "$fixture/README.md"
  if check_documentation_truth "$fixture"; then
    rm -rf "$fixture"
    return 1
  fi
  rm -rf "$fixture"
}

# ---- kit version consistency (same extraction as .github/workflows/ci.yml) ----
# Catch README/CHANGELOG drift before push. CI remains the backstop; this fails in
# seconds locally. Forgotten twice at v2.2.4 and v2.2.5 — that is the bar.
echo "== kit version consistency (README vs CHANGELOG)"
README_V="$(grep -m1 '^version:' README.md | awk '{print $2}')"
CHANGELOG_V="$(grep -m1 '^## ' CHANGELOG.md | sed 's/## //;s/ .*//')"
check "README version matches CHANGELOG head" test "$README_V" = "$CHANGELOG_V"
# Non-vacuous: identical extraction against deliberately mismatched files must fail.
VERSION_MISMATCH="$(mktemp -d)"
printf '%s\n' '---' 'version: 0.0.0' '---' > "$VERSION_MISMATCH/README.md"
printf '%s\n' '## 9.9.9 (2099-01-01)' '- drift' > "$VERSION_MISMATCH/CHANGELOG.md"
check "version mismatch fails the same extraction CI uses" sh -c "
  RV=\$(grep -m1 '^version:' '$VERSION_MISMATCH/README.md' | awk '{print \$2}')
  CV=\$(grep -m1 '^## ' '$VERSION_MISMATCH/CHANGELOG.md' | sed 's/## //;s/ .*//')
  ! [ \"\$RV\" = \"\$CV\" ]
"
rm -rf "$VERSION_MISMATCH"

echo "== documentation truth"
check "documentation matches instruction and ownership truth" check_documentation_truth "$HARNESS"
check "documentation guard rejects an enforced-permissions claim" documentation_truth_negative "$HARNESS"

echo "== immutable execution spec and provider adapter"
check "ExecutionSpec and provider adapter contracts" python3 tests/test-execution-spec.py
check "immutable spec integration through real wrappers" python3 tests/test-execution-integration.py
check "VerificationRecord and acceptance real-entry contracts" python3 tests/test-verification-record.py
check "ExecutionSpec focused test leaves no scripts bytecode" test ! -e "$HARNESS/scripts/__pycache__"

echo "== frozen fleet policy"
check "fleet inventory retention and frozen resolution" python3 tests/test-fleet-state.py

# F006 regressions must use the public propagation/release entry points. Tagged
# and untagged source state is always isolated so this suite is independent of
# the checkout from which it was invoked.
echo "== manifest and release truth"
check "manifest declares every canonical skill" sh -c "python3 - '$HARNESS/harness-manifest.json' <<'PY'
import json, pathlib, sys
m = json.load(open(sys.argv[1]))
actual = sorted(p.name for p in pathlib.Path('.agents/skills').iterdir() if p.is_dir())
assert m['ownership']['canonical_skills'] == actual
PY"
RELEASE_FIXTURE="$(mktemp -d)"
UNTAGGED_FIXTURE="$(mktemp -d)"
trap 'rm -rf "$RELEASE_FIXTURE" "$UNTAGGED_FIXTURE"' EXIT
cp -R "$HARNESS/." "$RELEASE_FIXTURE"
rm -rf "$RELEASE_FIXTURE/.git"
git -C "$RELEASE_FIXTURE" init -q
git -C "$RELEASE_FIXTURE" config user.email ci@test && git -C "$RELEASE_FIXTURE" config user.name CI
git -C "$RELEASE_FIXTURE" add -A && git -C "$RELEASE_FIXTURE" commit -qm fixture
git -C "$RELEASE_FIXTURE" tag -a v2.3.1 -m fixture
cp -R "$RELEASE_FIXTURE/." "$UNTAGGED_FIXTURE"
rm -rf "$UNTAGGED_FIXTURE/.git"
git -C "$UNTAGGED_FIXTURE" init -q
git -C "$UNTAGGED_FIXTURE" config user.email ci@test && git -C "$UNTAGGED_FIXTURE" config user.name CI
git -C "$UNTAGGED_FIXTURE" add -A && git -C "$UNTAGGED_FIXTURE" commit -qm fixture
check "manifest omission of guard-verification fails release entry point" sh -c "
  python3 -c \"import json; p='$RELEASE_FIXTURE/harness-manifest.json'; d=json.load(open(p)); d['ownership']['canonical_skills'].remove('guard-verification'); open(p, 'w').write(json.dumps(d))\"
  cd '$RELEASE_FIXTURE' && ! bash scripts/install-harness.sh --dev --validate-release
"
git -C "$RELEASE_FIXTURE" checkout -q -- harness-manifest.json
check "tagged annotated release source validates" sh -c "cd '$RELEASE_FIXTURE' && bash scripts/install-harness.sh --validate-release"
check "wrong release trigger tag fails at shared release entry point" sh -c "cd '$RELEASE_FIXTURE' && ! python3 scripts/harness-manifest.py --root . --require-release --trigger-tag v9.9.9 validate"
git -C "$RELEASE_FIXTURE" tag -a v9.9.9 -m wrong-trigger
check "second tag at HEAD does not authorize wrong release trigger" sh -c "cd '$RELEASE_FIXTURE' && ! python3 scripts/harness-manifest.py --root . --require-release --trigger-tag v9.9.9 validate"
git -C "$RELEASE_FIXTURE" tag -d v9.9.9 >/dev/null
python3 -c "import json; p='$RELEASE_FIXTURE/harness-manifest.json'; d=json.load(open(p)); d['release']['version']='banana'; d['release']['required_tag']='vbanana'; open(p, 'w').write(json.dumps(d))"
check "non-SemVer source version fails real install validation" sh -c "cd '$RELEASE_FIXTURE' && ! bash scripts/install-harness.sh --dev --validate-release"
git -C "$RELEASE_FIXTURE" checkout -q -- harness-manifest.json
python3 -c "import json; p='$RELEASE_FIXTURE/harness-manifest.json'; d=json.load(open(p)); d['ownership']['canonical_skills']=[]; open(p, 'w').write(json.dumps(d))"
check "empty ownership array fails real install validation" sh -c "cd '$RELEASE_FIXTURE' && ! bash scripts/install-harness.sh --dev --validate-release"
git -C "$RELEASE_FIXTURE" checkout -q -- harness-manifest.json
python3 -c "import json; p='$RELEASE_FIXTURE/harness-manifest.json'; d=json.load(open(p)); d['ownership']['install_payload_paths'][0]='../escape'; open(p, 'w').write(json.dumps(d))"
check "traversing ownership path fails real install validation" sh -c "cd '$RELEASE_FIXTURE' && ! bash scripts/install-harness.sh --dev --validate-release"
git -C "$RELEASE_FIXTURE" checkout -q -- harness-manifest.json
echo dirty >> "$RELEASE_FIXTURE/README.md"
DIRTY_INSTALL_TARGET="$(mktemp -d)"
git -C "$DIRTY_INSTALL_TARGET" init -q
git -C "$DIRTY_INSTALL_TARGET" config user.email ci@test && git -C "$DIRTY_INSTALL_TARGET" config user.name CI
echo consumer > "$DIRTY_INSTALL_TARGET/README.md"
git -C "$DIRTY_INSTALL_TARGET" add -A && git -C "$DIRTY_INSTALL_TARGET" commit -qm baseline
DIRTY_INSTALL_BRANCH="$(git -C "$DIRTY_INSTALL_TARGET" branch --show-current)"
check "dirty tagged install source rejects before target mutation" sh -c "cd '$RELEASE_FIXTURE' && ! bash scripts/install-harness.sh '$DIRTY_INSTALL_TARGET' && test \"\$(git -C '$DIRTY_INSTALL_TARGET' branch --show-current)\" = '$DIRTY_INSTALL_BRANCH' && test -z \"\$(git -C '$DIRTY_INSTALL_TARGET' status --porcelain)\" && ! test -e '$DIRTY_INSTALL_TARGET/.harness-version'"
rm -rf "$DIRTY_INSTALL_TARGET"
git -C "$RELEASE_FIXTURE" checkout -q -- README.md
check "default release validation rejects isolated untagged source" sh -c "cd '$UNTAGGED_FIXTURE' && ! bash scripts/install-harness.sh --validate-release"
check "default install rejects isolated untagged source" sh -c "cd '$UNTAGGED_FIXTURE' && ! bash scripts/install-harness.sh '$UNTAGGED_FIXTURE'"
check "explicit development release validation succeeds" sh -c "cd '$UNTAGGED_FIXTURE' && bash scripts/install-harness.sh --dev --validate-release"

TEMPLATE_TARGET="$(mktemp -d)"
git -C "$TEMPLATE_TARGET" init -q
git -C "$TEMPLATE_TARGET" config user.email ci@test && git -C "$TEMPLATE_TARGET" config user.name CI
echo consumer > "$TEMPLATE_TARGET/README.md"
git -C "$TEMPLATE_TARGET" add -A && git -C "$TEMPLATE_TARGET" commit -qm baseline
mkdir -p "$RELEASE_FIXTURE/docs/templates"
printf '%s\n' 'manifest-selected consumer template' > "$RELEASE_FIXTURE/docs/templates/selected.template"
python3 -c "import json; p='$RELEASE_FIXTURE/harness-manifest.json'; d=json.load(open(p)); d['ownership']['consumer_agents_template']='docs/templates/selected.template'; open(p, 'w').write(json.dumps(d))"
( cd "$RELEASE_FIXTURE" && bash scripts/install-harness.sh --dev "$TEMPLATE_TARGET" ) >/dev/null
check "installer uses manifest-selected consumer template" grep -qx "manifest-selected consumer template" "$TEMPLATE_TARGET/AGENTS.md"
rm -rf "$TEMPLATE_TARGET"
git -C "$RELEASE_FIXTURE" checkout -q -- harness-manifest.json
rm -f "$RELEASE_FIXTURE/docs/templates/selected.template"

TARGET="$(mktemp -d)"
trap 'rm -rf "$TARGET" "$RELEASE_FIXTURE"' EXIT
TARGET_CANONICAL="$(cd "$TARGET" && pwd -P)"

# ---- fixture: a target repo with one pre-existing conflicting file ----
git -C "$TARGET" init -q
git -C "$TARGET" config user.email ci@test && git -C "$TARGET" config user.name CI
echo "# my project readme" > "$TARGET/README.md"
echo "my own claude notes" > "$TARGET/CLAUDE.md"   # will conflict with kit CLAUDE.md
echo "project-owned agent rules" > "$TARGET/AGENTS.md"
echo "project-owned consumer skeleton" > "$TARGET/AGENTS.md.template"
git -C "$TARGET" add -A && git -C "$TARGET" commit -qm baseline

COLLISION_TARGET="$(mktemp -d)"
git -C "$COLLISION_TARGET" init -q
git -C "$COLLISION_TARGET" config user.email ci@test && git -C "$COLLISION_TARGET" config user.name CI
mkdir -p "$COLLISION_TARGET/scripts"
printf '%s\n' '#!/usr/bin/env bash' 'touch .consumer-sync-executed' > "$COLLISION_TARGET/scripts/sync-skills.sh"
printf '%s\n' 'consumer validator' > "$COLLISION_TARGET/scripts/harness-manifest.py"
printf '%s\n' '{"consumer":"manifest"}' > "$COLLISION_TARGET/harness-manifest.json"
echo consumer > "$COLLISION_TARGET/README.md"
git -C "$COLLISION_TARGET" add -A && git -C "$COLLISION_TARGET" commit -qm baseline
check "install rejects conflicting consumer controls before writes or execution" sh -c "! bash scripts/install-harness.sh --dev '$COLLISION_TARGET' && ! test -e '$COLLISION_TARGET/.consumer-sync-executed' && test -z \"\$(git -C '$COLLISION_TARGET' status --porcelain)\""
rm -rf "$COLLISION_TARGET"

DANGLING_TARGET="$(mktemp -d)"
DANGLING_EXTERNAL="$DANGLING_TARGET.harness-manifest-outside"
git -C "$DANGLING_TARGET" init -q
git -C "$DANGLING_TARGET" config user.email ci@test && git -C "$DANGLING_TARGET" config user.name CI
echo consumer > "$DANGLING_TARGET/README.md"
ln -s "$DANGLING_EXTERNAL" "$DANGLING_TARGET/harness-manifest.json"
git -C "$DANGLING_TARGET" add -A && git -C "$DANGLING_TARGET" commit -qm baseline
DANGLING_BRANCH="$(git -C "$DANGLING_TARGET" branch --show-current)"
check "install rejects dangling consumer manifest symlink before writes" sh -c "! bash scripts/install-harness.sh --dev '$DANGLING_TARGET' && test \"\$(git -C '$DANGLING_TARGET' branch --show-current)\" = '$DANGLING_BRANCH' && test -z \"\$(git -C '$DANGLING_TARGET' status --porcelain)\" && test -L '$DANGLING_TARGET/harness-manifest.json' && ! test -e '$DANGLING_EXTERNAL'"
rm -rf "$DANGLING_TARGET" "$DANGLING_EXTERNAL"

# ---- install ----
echo "== install-harness.sh"
check "default install rejects isolated untagged source" sh -c "cd '$UNTAGGED_FIXTURE' && ! bash scripts/install-harness.sh '$TARGET'"
bash scripts/install-harness.sh --dev "$TARGET"

VERSION="$(grep -m1 '^## ' CHANGELOG.md | sed 's/## //;s/ .*//' )"
check "records .harness-version = $VERSION" grep -qx "$VERSION" "$TARGET/.harness-version"
check "project AGENTS.md untouched"          grep -qx "project-owned agent rules" "$TARGET/AGENTS.md"
check "project AGENTS.md.template untouched" grep -qx "project-owned consumer skeleton" "$TARGET/AGENTS.md.template"
check "conflict -> CLAUDE.md.harness-new"    test -f "$TARGET/CLAUDE.md.harness-new"
check "existing CLAUDE.md untouched"         grep -q "my own claude notes" "$TARGET/CLAUDE.md"
check "skills copied"                        test -f "$TARGET/.agents/skills/dispatch-worker/SKILL.md"
check "missions ORCHESTRATION installed"     test -f "$TARGET/docs/missions/ORCHESTRATION.md"
check "missions MODEL_ROUTING installed"     test -f "$TARGET/docs/missions/MODEL_ROUTING.md"
check "missions templates installed"         test -f "$TARGET/docs/missions/templates/GOAL.template.md"
# 2.2.4: every template feature must ship the bootstrap field, and the rules string must
# explain it. verify-mission requires a worker receipt unless bootstrap is true, so a
# template that stops carrying the field lets orchestrator-only features go green on
# another feature's receipt with only a WARN.
check "template features all carry bootstrap" sh -c "python3 -c \"import json,sys; d=json.load(open('$TARGET/docs/missions/templates/features.template.json')); sys.exit(0 if all('bootstrap' in f for f in d['features']) else 1)\""
check "template rules explain bootstrap"      sh -c "python3 -c \"import json,sys; d=json.load(open('$TARGET/docs/missions/templates/features.template.json')); sys.exit(0 if 'bootstrap' in d['rules'] else 1)\""
# grep for the flag literal, not the word: the skill's own description already contains
# "bootstrap the loop", so a bare word match would pass without any guidance present.
check "mission-init skill documents bootstrap" sh -c "grep -q '\"bootstrap\": true' '$TARGET/.agents/skills/mission-init/SKILL.md'"
check "stub ORCHESTRATION at old path"       test -f "$TARGET/docs/ORCHESTRATION.md"
check "spawn-worker.sh installed +x"         test -x "$TARGET/scripts/spawn-worker.sh"
check "execution spec tool installed"        test -f "$TARGET/scripts/execution_spec.py"
check "execution receipt tool installed"     test -f "$TARGET/scripts/execution_receipt.py"
check "execution lifecycle runner installed" test -f "$TARGET/scripts/execution_runner.py"
check "provider adapter installed"           test -f "$TARGET/scripts/execute_provider.py"
check "dispatch policy installed"            test -f "$TARGET/scripts/dispatch_policy.py"
check "execution spec schema installed"      test -f "$TARGET/schemas/execution-spec.schema.json"
check "execution receipt schema installed"   test -f "$TARGET/schemas/execution-receipt.schema.json"
check "active-mission.sh installed +x"       test -x "$TARGET/scripts/active-mission.sh"
check "fleet-inventory.sh installed +x"      test -x "$TARGET/scripts/fleet-inventory.sh"
check "fleet policy module installed"        test -f "$TARGET/scripts/fleet_state.py"
check "fleet inventory schema installed"     test -f "$TARGET/schemas/fleet-inventory.schema.json"
check "mission fleet schema installed"       test -f "$TARGET/schemas/mission-fleet.schema.json"
check ".claude/skills is a real directory"   sh -c "[ ! -L '$TARGET/.claude/skills' ] && [ -d '$TARGET/.claude/skills' ]"
check "per-skill link under .claude/skills"  test -L "$TARGET/.claude/skills/dispatch-worker"
check "per-skill link under .cursor/skills"  test -L "$TARGET/.cursor/skills/dispatch-worker"
check "canonical skill is a real directory"  sh -c "[ ! -L '$TARGET/.agents/skills/dispatch-worker' ] && [ -f '$TARGET/.agents/skills/dispatch-worker/SKILL.md' ]"
check "install stayed on a branch"           sh -c "git -C '$TARGET' branch --show-current | grep -q chore/harness-install"
check "install did not commit"               sh -c "[ -n \"\$(git -C '$TARGET' status --porcelain)\" ]"

# ---- mission layout helpers ----
echo "== active-mission / spawn dry checks"
mkdir -p "$TARGET/docs/missions/20990101-fixture/tasks"
printf '%s\n' '---' 'status: in-progress' '---' '# Goal' > "$TARGET/docs/missions/20990101-fixture/GOAL.md"
# shellcheck disable=SC2016  # task fixture requires literal Markdown backticks
printf '%s\n' '---' 'task_id: T-001' 'feature: F001' '---' '# Task' '' '## Files you MAY touch' '- `proof.txt`' > "$TARGET/docs/missions/20990101-fixture/tasks/T-001.md"
# shellcheck disable=SC2016  # task fixture requires literal Markdown backticks
printf '%s\n' '---' 'task_id: T-002' 'feature: F002' '---' '# Task' '' '## Files you MAY touch' '- `proof.txt`' '' '## Verification commands' '' '- `["git","status","--porcelain"]`' > "$TARGET/docs/missions/20990101-fixture/tasks/T-002.md"
echo '{}' > "$TARGET/docs/missions/20990101-fixture/features.json"
check "active-mission finds fixture" sh -c "cd '$TARGET' && bash scripts/active-mission.sh | grep -q 20990101-fixture"
check "spawn-worker rejects unknown worker" sh -c "cd '$TARGET' && ! bash scripts/spawn-worker.sh nope docs/missions/20990101-fixture/GOAL.md"
check "fleet-inventory writes json" sh -c "cd '$TARGET' && bash scripts/fleet-inventory.sh --json >/dev/null && test -f .tasks/fleet-inventory.json"
check "inventory binds cursor.premium grok-family" sh -c "cd '$TARGET' && python3 -c \"import json; s=json.load(open('.tasks/fleet-inventory.json'))['seats']['cursor.premium']; assert 'grok' in (s.get('family') or '') or 'grok' in (s.get('model') or '').lower()\""
check "inventory binds brain opus" sh -c "cd '$TARGET' && python3 -c \"import json; assert json.load(open('.tasks/fleet-inventory.json'))['seats']['brain']['family']=='opus'\""
check "inventory has agy seats when CLI present" sh -c "cd '$TARGET' && python3 -c \"import json; d=json.load(open('.tasks/fleet-inventory.json'));
import shutil; 
assert 'agy.premium' in d['seats'] and 'agy.economy' in d['seats']\""
check "spawn-brain.sh installed +x" test -x "$TARGET/scripts/spawn-brain.sh"
check "verify-mission.sh installed +x" test -x "$TARGET/scripts/verify-mission.sh"
check "VerificationRecord policy installed" test -f "$TARGET/scripts/verification_record.py"
check "accept-feature.sh installed +x" test -x "$TARGET/scripts/accept-feature.sh"
check "VerificationRecord schema installed" test -f "$TARGET/schemas/verification-record.schema.json"
# receipt greenlight
echo "== verify-mission receipts"
FEAT="$TARGET/docs/missions/20990101-fixture"
printf '%s\n' '{"goal":"t","features":[{"id":"F001","description":"Mission folder active","bootstrap":true,"steps":[],"passes":true,"priority":1},{"id":"F002","description":"Real work mentions mission files in prose only","bootstrap":false,"steps":[],"passes":false,"priority":2}]}' > "$FEAT/features.json"
python3 - "$FEAT/fleet.json" <<'PY'
import json, sys
caps = {
    "agent": {"efforts": ["low", "medium", "high", "xhigh"], "speeds": ["standard", "fast"]},
    "codex": {"efforts": ["low", "medium", "high", "xhigh"], "speeds": ["unknown"]},
    "agy": {"efforts": ["low", "medium", "high"], "speeds": ["unknown"]},
    "claude": {"efforts": ["low", "medium", "high", "xhigh", "max"], "speeds": ["unknown"]},
}
def seat(provider, model, family, effort, speed):
    return {"provider": provider, "model": model, "family": family, "effort": effort,
            "speed": speed, "health": "healthy", "source": "alias" if provider == "claude" else "observed",
            "capabilities": caps[provider]}
doc = {
    "schema_version": 1,
    "mission": {"path": "docs/missions/20990101-fixture"},
    "inventory": {"sha256": "0" * 64, "probed_at": "2026-08-21T00:00:00Z"},
    "approval": {"status": "approved", "approved_by": "human", "approved_at": "2026-08-21T00:00:00Z"},
    "seats": {
        "brain": seat("codex", "gpt-5.6-sol", "sol", "high", "unknown"),
        "agy.premium": seat("agy", "agy-test-model", "pro", "high", "unknown"),
        "claude.premium": seat("claude", "claude-test-model", "sonnet", "xhigh", "unknown"),
        "codex.economy": seat("codex", "codex-test-model", "luna", "medium", "unknown"),
        "codex.premium": seat("codex", "codex-test-model", "terra", "xhigh", "unknown"),
        "cursor.economy": seat("agent", "agent-test-model", "composer", "xhigh", "standard"),
    },
}
open(sys.argv[1], "w").write(json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n")
PY
chmod 444 "$FEAT/fleet.json"
check "verify fails without receipts" sh -c "cd '$TARGET' && ! bash scripts/verify-mission.sh docs/missions/20990101-fixture"
printf '%s\n' '.tasks/' '.verifybin/' > "$TARGET/.git/info/exclude"
VERIFY_BIN="$TARGET/.verifybin"; mkdir -p "$VERIFY_BIN"
# shellcheck disable=SC2016  # generated stub must expand VERIFY_WRITE at runtime
printf '%s\n' '#!/usr/bin/env bash' '[ "${VERIFY_WRITE:-0}" != 1 ] || printf "%s\n" verified > proof.txt' 'exit 0' > "$VERIFY_BIN/codex"
chmod +x "$VERIFY_BIN/codex"
git -C "$TARGET" add -A && git -C "$TARGET" commit -qm "strict receipt fixture"
( cd "$TARGET" && PATH="$VERIFY_BIN:$PATH" SPAWN_BRAIN_TIMEOUT_SECS=0 \
    bash scripts/spawn-brain.sh docs/missions/20990101-fixture review ) >/dev/null
( cd "$TARGET" && PATH="$VERIFY_BIN:$PATH" VERIFY_WRITE=1 SPAWN_WORKER_TIMEOUT_SECS=0 \
    bash scripts/spawn-worker.sh codex docs/missions/20990101-fixture/tasks/T-002.md \
      --tier economy --model codex-test-model --feature F002 ) >/dev/null
VERIFY_RUN_ID="$(python3 - "$TARGET/.tasks/receipts" <<'PY'
import json, pathlib, sys
for path in pathlib.Path(sys.argv[1]).glob('*.json'):
    doc = json.loads(path.read_text())
    if doc['role'] == 'worker' and doc['feature'] == 'F002':
        print(doc['run_id'])
        break
else:
    raise SystemExit(1)
PY
)"
( cd "$TARGET" && bash scripts/verify-mission.sh --run-id "$VERIFY_RUN_ID" docs/missions/20990101-fixture ) >/dev/null
VERIFY_HASH="$(python3 - "$FEAT/verification/$VERIFY_RUN_ID.json" <<'PY'
import hashlib, pathlib, sys
print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"
( cd "$TARGET" && env -u PURRFECT_DISPATCH_LOCK_PATH bash scripts/accept-feature.sh --run-id "$VERIFY_RUN_ID" --verification-sha256 "$VERIFY_HASH" --accepted-by test docs/missions/20990101-fixture ) >/dev/null
git -C "$TARGET" add -A && git -C "$TARGET" commit -qm "accept strict verification fixture"
check "verify passes with brain+worker receipts" sh -c "cd '$TARGET' && bash scripts/verify-mission.sh docs/missions/20990101-fixture"
check "spawn-worker --repo rejects missing path" sh -c "cd '$TARGET' && bash scripts/spawn-worker.sh agent docs/missions/20990101-fixture/GOAL.md --repo /nope/does/not/exist; test \$? -eq 1"

# Successful dispatches below exercise the Phase 1 clean-workspace gate. Preserve
# machine-local harness evidence and test sentinels outside Git truth, make F001
# pending again after the receipt-verification fixture, then commit the baseline.
printf '%s\n' '.tasks/' '.stubbin/' '.agy-args' '.claude-args' '.codex-*' '.agent-*' >> "$TARGET/.git/info/exclude"
printf '%s\n' '{"goal":"t","features":[{"id":"F001","description":"Provider wrapper contract","bootstrap":false,"steps":[],"passes":false,"priority":1},{"id":"F002","description":"Other pending work","bootstrap":false,"steps":[],"passes":false,"priority":2}]}' > "$FEAT/features.json"
git -C "$TARGET" add -A && git -C "$TARGET" commit -qm "installed harness dispatch fixture"

# ---- agy prompt-flag regression (2.2.3) ----
# Antigravity's CLI uses a Go flag parser: -p/--print/--prompt takes the PROMPT AS
# ITS VALUE. `agy -p --dangerously-skip-permissions ... "$PROMPT"` set
# print="--dangerously-skip-permissions", dropped the real prompt, and exited 0 — so
# the wrapper reported success having done no work. -p must come last.
echo "== agy prompt-flag order"
STUBBIN="$TARGET/.stubbin"; mkdir -p "$STUBBIN"
STUB_OUT="$TARGET/.agy-args"
# shellcheck disable=SC2016  # printf template: $ must stay literal
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" > "%s"\nexit 0\n' "$STUB_OUT" > "$STUBBIN/agy"
chmod +x "$STUBBIN/agy"
( cd "$TARGET" && PATH="$STUBBIN:$PATH" SPAWN_WORKER_TIMEOUT_SECS=0 \
    bash scripts/spawn-worker.sh agy docs/missions/20990101-fixture/tasks/T-001.md --tier premium --effort high --feature F001 ) >/dev/null 2>&1 || true
check "agy receives the real prompt as the value of -p" \
  sh -c "grep -q -- '-p Read ' '$STUB_OUT'"
check "agy -p is not fed the permissions flag" \
  sh -c "! grep -q -- '-p --dangerously-skip-permissions' '$STUB_OUT'"
check "agy gets a print-timeout longer than the 5m default" \
  sh -c "grep -q -- '--print-timeout' '$STUB_OUT'"

# ---- claude prompt-position regression (2.2.5) ----
# claude's --allowedTools is VARIADIC: it keeps consuming following args as tool names,
# so a prompt placed after it is swallowed and claude exits with "Input must be provided
# either through stdin or as a prompt argument". The prompt must precede the flags.
echo "== claude prompt position"
CLAUDE_OUT="$TARGET/.claude-args"
# shellcheck disable=SC2016  # printf template: $ must stay literal
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" > "%s"\nexit 0\n' "$CLAUDE_OUT" > "$STUBBIN/claude"
chmod +x "$STUBBIN/claude"
( cd "$TARGET" && PATH="$STUBBIN:$PATH" SPAWN_WORKER_TIMEOUT_SECS=0 \
    bash scripts/spawn-worker.sh claude docs/missions/20990101-fixture/tasks/T-001.md --tier premium --effort xhigh --feature F001 ) >/dev/null 2>&1 || true
check "claude receives the prompt immediately after -p" \
  sh -c "grep -q -- '-p Read ' '$CLAUDE_OUT'"
check "claude prompt is not placed after --allowedTools" \
  sh -c "! grep -qE -- '--allowedTools [^ ]+ Read ' '$CLAUDE_OUT'"

# ---- codex prompt/argument and stdin regressions ----
# Keep this stub's stdin read: codex waits for additional input unless its stdin is
# explicitly closed by spawn-worker.sh. The argument file is one line per argv entry so
# the exact flag/value boundaries and final prompt position are asserted, not just $*.
echo "== codex prompt, effort, and stdin"
CODEX_OUT="$TARGET/.codex-args"
CODEX_EOF_MARK="$TARGET/.codex-eof"
CODEX_STUB_PID="$TARGET/.codex-stub-pid"
# shellcheck disable=SC2016  # printf template: $ must stay literal
printf '#!/usr/bin/env bash\nset -euo pipefail\nprintf "%%s\\n" "$$" > "%s"\nwhile IFS= read -r _codex_stdin_line; do :; done\ntouch "%s"\nprintf "%%s\\n" "$(basename "$0")" "$@" > "%s"\nexit 0\n' "$CODEX_STUB_PID" "$CODEX_EOF_MARK" "$CODEX_OUT" > "$STUBBIN/codex"
chmod +x "$STUBBIN/codex"
CODEX_MODEL="codex-test-model"
CODEX_PROMPT="Read docs/missions/20990101-fixture/tasks/T-001.md and complete it exactly. Follow AGENTS.md and the skills the task names. Do not touch files outside the allow-list. Append a PROGRESS.md entry in the mission folder."
CODEX_EXPECTED="$TARGET/.codex-expected"
printf '%s\n' codex exec -C "$TARGET_CANONICAL" -s workspace-write --add-dir "$TARGET_CANONICAL/.git" -m "$CODEX_MODEL" \
  '-c' 'model_reasoning_effort="medium"' "$CODEX_PROMPT" > "$CODEX_EXPECTED"
( cd "$TARGET" && PATH="$STUBBIN:$PATH" SPAWN_WORKER_TIMEOUT_SECS=0 \
    bash scripts/spawn-worker.sh codex docs/missions/20990101-fixture/tasks/T-001.md \
      --tier economy --model "$CODEX_MODEL" --feature F001 ) >/dev/null 2>&1 || true
check "codex receives the exact invocation with medium default" \
  cmp -s "$CODEX_EXPECTED" "$CODEX_OUT"

CODEX_EXPECTED_XHIGH="$TARGET/.codex-expected-xhigh"
printf '%s\n' codex exec -C "$TARGET_CANONICAL" -s workspace-write --add-dir "$TARGET_CANONICAL/.git" -m "$CODEX_MODEL" \
  '-c' 'model_reasoning_effort="xhigh"' "$CODEX_PROMPT" > "$CODEX_EXPECTED_XHIGH"
( cd "$TARGET" && PATH="$STUBBIN:$PATH" SPAWN_WORKER_TIMEOUT_SECS=0 \
    bash scripts/spawn-worker.sh codex docs/missions/20990101-fixture/tasks/T-001.md \
      --tier premium --model "$CODEX_MODEL" --effort xhigh --feature F001 ) >/dev/null 2>&1 || true
check "codex receives --effort xhigh" \
  cmp -s "$CODEX_EXPECTED_XHIGH" "$CODEX_OUT"

# Hold the wrapper's stdin open through a FIFO. The fixed codex branch redirects the
# CLI's stdin to /dev/null and exits; the broken branch leaves the EOF-reading stub blocked.
CODEX_FIFO="$TARGET/.codex-stdin"
rm -f "$CODEX_EOF_MARK" "$CODEX_STUB_PID"
mkfifo "$CODEX_FIFO"
exec 9<>"$CODEX_FIFO"
set +e
( cd "$TARGET" && PATH="$STUBBIN:$PATH" SPAWN_WORKER_TIMEOUT_SECS=0 \
    bash scripts/spawn-worker.sh codex docs/missions/20990101-fixture/tasks/T-001.md \
      --tier economy --model "$CODEX_MODEL" --feature F001 ) <"$CODEX_FIFO" >/dev/null 2>&1 &
CODEX_PID=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do
  [ -f "$CODEX_EOF_MARK" ] && break
  sleep 0.1
done
if [ -f "$CODEX_EOF_MARK" ]; then
  wait "$CODEX_PID"
  CODEX_STDIN_EOF=$?
else
  CODEX_STUB_PID_VALUE=""
  if [ -f "$CODEX_STUB_PID" ]; then
    CODEX_STUB_PID_VALUE="$(<"$CODEX_STUB_PID")"
  fi
  if [ -n "$CODEX_STUB_PID_VALUE" ]; then kill "$CODEX_STUB_PID_VALUE" 2>/dev/null || true; fi
  kill "$CODEX_PID" 2>/dev/null || true
  exec 9>&-
  wait "$CODEX_PID" 2>/dev/null || true
  CODEX_STDIN_EOF=1
fi
set -e
exec 9>&-
rm -f "$CODEX_FIFO" "$CODEX_STUB_PID"
check "codex stdin is closed so EOF-reading stub returns" test "$CODEX_STDIN_EOF" -eq 0

# ---- agent prompt/argument regression ----
# Agent's -p is boolean. Assert the full invocation and final prompt, including every
# value-taking option, so a simplified smoke test cannot pass a swallowed prompt.
echo "== agent prompt and argument order"
AGENT_OUT="$TARGET/.agent-args"
# shellcheck disable=SC2016  # printf template: $ must stay literal
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$(basename "$0")" "$@" > "%s"\nexit 0\n' "$AGENT_OUT" > "$STUBBIN/agent"
chmod +x "$STUBBIN/agent"
AGENT_MODEL="agent-test-model"
AGENT_EXPECTED="$TARGET/.agent-expected"
printf '%s\n' agent -p --force --trust --workspace "$TARGET_CANONICAL" --model "${AGENT_MODEL}[effort=xhigh,fast=false]" "$CODEX_PROMPT" > "$AGENT_EXPECTED"
( cd "$TARGET" && PATH="$STUBBIN:$PATH" \
    bash scripts/spawn-worker.sh agent docs/missions/20990101-fixture/tasks/T-001.md \
      --tier economy --model "$AGENT_MODEL" --effort xhigh --feature F001 ) >/dev/null 2>&1 || true
check "agent receives the exact invocation with intact final prompt" \
  cmp -s "$AGENT_EXPECTED" "$AGENT_OUT"

# ---- legacy parent-symlink must be migrated safely ----
echo "== sync-skills parent-symlink migration"
git -C "$TARGET" add -A
if ! git -C "$TARGET" diff --cached --quiet; then
  git -C "$TARGET" commit -qm "harness install"
fi
rm -rf "$TARGET/.claude/skills"
ln -s ../.agents/skills "$TARGET/.claude/skills"
( cd "$TARGET" && bash scripts/sync-skills.sh )
check "parent symlink replaced" sh -c "[ ! -L '$TARGET/.claude/skills' ]"
check "canonical intact after sync" test -f "$TARGET/.agents/skills/dispatch-worker/SKILL.md"
check "canonical not a symlink" sh -c "[ ! -L '$TARGET/.agents/skills/dispatch-worker' ]"

# A discovery entry not owned by the manifest must survive a real sync.
mkdir -p "$TARGET/.claude/skills/foreign-project-skill"
echo "keep" > "$TARGET/.claude/skills/foreign-project-skill/README.md"
( cd "$TARGET" && bash scripts/sync-skills.sh )
check "foreign discovery skill survives sync" test -f "$TARGET/.claude/skills/foreign-project-skill/README.md"

mkdir -p "$TARGET/.agents/skills/foreign-canonical-skill"
echo keep > "$TARGET/.agents/skills/foreign-canonical-skill/SKILL.md"
( cd "$TARGET" && bash scripts/sync-skills.sh )
check "foreign canonical skill survives consumer sync" test -f "$TARGET/.agents/skills/foreign-canonical-skill/SKILL.md"

python3 -c "import json; p='$TARGET/harness-manifest.json'; d=json.load(open(p)); d['ownership']['discovery_targets']=['../escape']; open(p, 'w').write(json.dumps(d))"
check "path-traversing discovery ownership rejects sync" sh -c "cd '$TARGET' && ! bash scripts/sync-skills.sh"
git -C "$TARGET" checkout -q -- harness-manifest.json

# ---- re-install must refuse ----
check "second install refused" sh -c "! bash scripts/install-harness.sh '$TARGET'"

# ---- update path must preserve instance mission folders ----
echo "== update-harness.sh"
echo "keep-me" > "$TARGET/docs/missions/20990101-fixture/KEEP.md"
git -C "$TARGET" add -A && git -C "$TARGET" commit -qm "fixture mission marker"
DIRTY_UPDATE_BRANCH="$(git -C "$TARGET" branch --show-current)"
DIRTY_UPDATE_STATUS="$(git -C "$TARGET" status --porcelain)"
DIRTY_UPDATE_VERSION="$(<"$TARGET/.harness-version")"
printf '%s\n' 'deliberately dirty tagged update source' >> "$RELEASE_FIXTURE/README.md"
check "dirty tagged update source is rejected by real updater" sh -c "cd '$RELEASE_FIXTURE' && ! bash scripts/update-harness.sh '$TARGET' && test \"\$(git -C '$TARGET' branch --show-current)\" = '$DIRTY_UPDATE_BRANCH' && test \"\$(git -C '$TARGET' status --porcelain)\" = '$DIRTY_UPDATE_STATUS' && test \"\$(< '$TARGET/.harness-version')\" = '$DIRTY_UPDATE_VERSION'"
git -C "$RELEASE_FIXTURE" checkout -q -- README.md
bash scripts/update-harness.sh --dev "$TARGET"
check "update stayed on version branch" sh -c "git -C '$TARGET' branch --show-current | grep -q 'chore/harness-'"
check "kit skill still present after update" test -f "$TARGET/.agents/skills/mission-init/SKILL.md"
check "provider adapter remains after update" test -f "$TARGET/scripts/execute_provider.py"
check "dispatch policy remains after update" test -f "$TARGET/scripts/dispatch_policy.py"
check "fleet policy remains after update"    test -f "$TARGET/scripts/fleet_state.py"
check "fleet schemas remain after update"    sh -c "test -f '$TARGET/schemas/fleet-inventory.schema.json' && test -f '$TARGET/schemas/mission-fleet.schema.json'"
check "execution schemas remain after update" sh -c "test -f '$TARGET/schemas/execution-spec.schema.json' && test -f '$TARGET/schemas/execution-receipt.schema.json'"
check "execution receipt lifecycle remains after update" sh -c "test -f '$TARGET/scripts/execution_receipt.py' && test -f '$TARGET/scripts/execution_runner.py'"
check "MODEL_ROUTING under docs/missions" test -f "$TARGET/docs/missions/MODEL_ROUTING.md"
check "instance mission folder preserved" test -f "$TARGET/docs/missions/20990101-fixture/KEEP.md"
check "instance GOAL preserved" test -f "$TARGET/docs/missions/20990101-fixture/GOAL.md"
git -C "$TARGET" add -A && git -C "$TARGET" commit -qm "updated fixture"
printf '%s\n' banana > "$TARGET/.harness-version"
git -C "$TARGET" add .harness-version && git -C "$TARGET" commit -qm "invalid installed version"
check "update rejects banana installed version" sh -c "! bash scripts/update-harness.sh --dev '$TARGET'"

UNMANAGED="$(mktemp -d)"
git -C "$UNMANAGED" init -q
git -C "$UNMANAGED" config user.email ci@test && git -C "$UNMANAGED" config user.name CI
echo unmanaged > "$UNMANAGED/README.md"
git -C "$UNMANAGED" add -A && git -C "$UNMANAGED" commit -qm baseline
check "update refuses unmanaged target" sh -c "! bash scripts/update-harness.sh --dev '$UNMANAGED'"
printf ' \n' > "$UNMANAGED/.harness-version"
check "update rejects whitespace .harness-version" sh -c "! bash scripts/update-harness.sh --dev '$UNMANAGED'"
rm -rf "$UNMANAGED"

# ---- dirty-tree refusals ----
echo dirty > "$TARGET/dirty.txt"
check "update refuses dirty tree" sh -c "! bash scripts/update-harness.sh '$TARGET'"

echo ""
if [ "$FAIL" -eq 1 ]; then echo "TESTS FAILED"; exit 1; else echo "ALL TESTS PASSED"; fi
