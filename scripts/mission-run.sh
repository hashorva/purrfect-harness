#!/usr/bin/env bash
# Usage: mission-run.sh <mission-dir> --provider NAME [--feature F0xx]
# nohup bash scripts/mission-run.sh <mission> --provider NAME > .tasks/mission-run.out 2>&1 &
# tmux new -d 'bash scripts/mission-run.sh <mission> --provider NAME'
# Exits 0 (done or gate), 2 usage, 3 decision, 4 blocker. Overrides: MISSION_RUN_WORKER MISSION_RUN_VERIFY MISSION_RUN_REVIEW
# shellcheck disable=SC2016
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
usage() { echo "Usage: mission-run.sh <mission-dir> --provider NAME [--feature F0xx]" >&2; exit 2; }
[ $# -ge 1 ] || usage
MISSION=$1; shift; PROVIDER=""; FEATURE=""
while [ $# -gt 0 ]; do case "$1" in
  --provider) [ $# -ge 2 ] || usage; PROVIDER=$2; shift 2 ;;
  --feature) [ $# -ge 2 ] || usage; FEATURE=$2; shift 2 ;;
  *) usage ;; esac; done
[ -n "$PROVIDER" ] && [ -f "$MISSION/features.json" ] || usage
mkdir -p .tasks; touch .tasks/events.jsonl
IFS=' ' read -r -a WORKER <<< "${MISSION_RUN_WORKER:-bash $DIR/spawn-worker.sh}"
IFS=' ' read -r -a VERIFY <<< "${MISSION_RUN_VERIFY:-bash $DIR/verify-mission.sh}"
IFS=' ' read -r -a REVIEW <<< "${MISSION_RUN_REVIEW:-bash $DIR/spawn-brain.sh}"
event() { jq -cn --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg feature "$FEATURE" --arg event "$1" "${@:2}" '$ARGS.named' >> .tasks/events.jsonl; }
stop() { event "$1" --arg detail "$2"; echo "mission-run: $1: $2"; exit "$3"; }
commit_mission() { [ -z "$(git status --porcelain -- "$MISSION")" ] || { git add -- "$MISSION" && git commit -q -m "$1"; }; }
after() { jq -rs --arg role "$1" --argjson n "$2" --arg f "$3" '.[$n:] | map(select(.event=="run_exit" and .role==$role)) | last | .[$f] // empty' .tasks/events.jsonl; }
plan=$(python3 - "$MISSION" "$FEATURE" <<'PY'
import json, re, sys; from pathlib import Path
m, want = Path(sys.argv[1]), sys.argv[2]
data = json.loads((m / "features.json").read_text()); ok = {item["id"]: item.get("passes") is True for item in data["features"]}
feat = want or next((item for item in data["run_order"] if not ok.get(item)), "")
if not feat: print("-"); raise SystemExit
mine = [path for path in sorted((m / "tasks").glob("T-*.md"), key=lambda path: [int(n) for n in re.findall(r"\d+", path.name)]) if re.search("(?m)^feature:[ \\t]*%s[ \\t]*$" % re.escape(feat), (path.read_text().split("---", 2) + ["", ""])[1])]
passed = {str(obj.get("work_unit")) for rec in ((m / "verification").glob("*.json") if (m / "verification").is_dir() else []) for obj in [json.loads(rec.read_text())] if isinstance(obj, dict) and obj.get("result") == "pass"}
groups = {}
for path in mine: groups.setdefault(re.match(r"T-\d+", path.name).group(0), []).append(path)
open_paths = [xs[-1] for xs in groups.values() if not any(path.stem in passed for path in xs)]; gate = "-"; goal = (m / "GOAL.md").read_text() if (m / "GOAL.md").is_file() else ""
for number, sentence in re.findall(r"GATE (\d+)\b.*?Held after ([^.]*)", goal):
    ids = ["F%0*d" % (len(ends[0]) - 1, i) for token in re.findall(r"F\d+(?:\s*(?:–|-)\s*F\d+)?", sentence) for ends in [re.split(r"\s*(?:–|-)\s*", token)] for i in range(int(ends[0][1:]), int(ends[-1][1:]) + 1)]
    if feat in ids and all(ok.get(item) for item in ids if item != feat): gate = number; break
print(feat, gate, *open_paths)
PY
)
read -r -a PLAN <<< "$plan"
[ "${PLAN[0]}" = "-" ] && stop "done" "every feature passes" 0
FEATURE=${PLAN[0]}; GATE=${PLAN[1]}; [ "$GATE" = "-" ] || GATE="GATE $GATE"; TASKS=(); [ "${#PLAN[@]}" -le 2 ] || TASKS=("${PLAN[@]:2}")
MAX_ROUNDS=2
if [ "${#TASKS[@]}" -gt 0 ]; then
  for task in "${TASKS[@]}"; do
    id=$(basename "$task" .md); round=1; passed=0
    while [ "$round" -le "$MAX_ROUNDS" ]; do
      n=$(wc -l < .tasks/events.jsonl | tr -d ' ')
      "${WORKER[@]}" "$task" --provider "$PROVIDER" --feature "$FEATURE" --attempt "$round" </dev/null || true
      run=$(after worker "$n" run_id); [ -n "$run" ] || stop blocker "$id: no worker run started" 4
      result=pass; "${VERIFY[@]}" --run-id "$run" "$MISSION" </dev/null || result=fail
      commit_mission "docs: $id verified ($result)"
      event verify --arg task "$id" --arg run_id "$run" --argjson round "$round" --arg result "$result"
      if [ "$result" = pass ]; then
        n=$(wc -l < .tasks/events.jsonl | tr -d ' ')
        "${REVIEW[@]}" "$MISSION" review </dev/null || true
        verdict=$(python3 "$DIR/validate_verdict.py" --receipt "$(after brain "$n" receipt)") || stop blocker "$id: review gave no valid verdict" 4
        commit_mission "docs: $id review round $round ($verdict)"
        event review --arg task "$id" --arg run_id "$run" --argjson round "$round" --arg verdict "$verdict"
        [ "$verdict" = PASS ] && passed=1 && break
      fi
      round=$((round + 1))
    done
    [ "$passed" = 1 ] || stop decision_needed "$id: 2 rounds without a pass; split it (F006)" 3
  done
fi
[ "$GATE" = "-" ] && stop decision_needed "$FEATURE: every task passed; accept it" 3
stop gate_reached "$GATE" 0
