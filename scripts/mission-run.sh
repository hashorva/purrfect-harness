#!/usr/bin/env bash
# Usage: mission-run.sh <mission-dir> --provider NAME [--feature F0xx] [--tier economy|premium]
# nohup bash scripts/mission-run.sh <mission> --provider NAME > .tasks/mission-run.out 2>&1 &
# tmux new -d 'bash scripts/mission-run.sh <mission> --provider NAME'
# Exits 0 (done or gate), 2 usage, 3 decision, 4 blocker. Overrides: MISSION_RUN_WORKER MISSION_RUN_VERIFY MISSION_RUN_REVIEW MISSION_RUN_PLAN MISSION_RUN_PROBE
# shellcheck disable=SC2016
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
usage() { echo "Usage: mission-run.sh <mission-dir> --provider NAME [--feature F0xx] [--tier economy|premium]" >&2; exit 2; }
[ $# -ge 1 ] || usage
MISSION=$1; shift; PROVIDER=""; FEATURE=""; TIER=economy
while [ $# -gt 0 ]; do case "$1" in
  --provider) [ $# -ge 2 ] || usage; PROVIDER=$2; shift 2 ;;
  --feature) [ $# -ge 2 ] || usage; FEATURE=$2; shift 2 ;;
  --tier) [ $# -ge 2 ] || usage; TIER=$2; shift 2; case "$TIER" in economy|premium) ;; *) usage ;; esac ;;
  *) usage ;; esac; done
[ -n "$PROVIDER" ] && [ -f "$MISSION/features.json" ] || usage
mkdir -p .tasks; touch .tasks/events.jsonl
IFS=' ' read -r -a WORKER <<< "${MISSION_RUN_WORKER:-bash $DIR/spawn-worker.sh}"
IFS=' ' read -r -a VERIFY <<< "${MISSION_RUN_VERIFY:-bash $DIR/verify-mission.sh}"
IFS=' ' read -r -a REVIEW <<< "${MISSION_RUN_REVIEW:-bash $DIR/spawn-brain.sh}"
IFS=' ' read -r -a PLANSTEP <<< "${MISSION_RUN_PLAN:-bash $DIR/spawn-brain.sh}"
IFS=' ' read -r -a PROBE <<< "${MISSION_RUN_PROBE:-bash $DIR/probe-seat.sh}"
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
fm = lambda path: (path.read_text().split("---", 2) + ["", ""])[1]
mine = [path for path in sorted((m / "tasks").glob("T-*.md"), key=lambda path: [int(n) for n in re.findall(r"\d+", path.name)]) if re.search("(?m)^feature:[ \\t]*%s[ \\t]*$" % re.escape(feat), fm(path))]
passed = {str(obj.get("work_unit")) for rec in ((m / "verification").glob("*.json") if (m / "verification").is_dir() else []) for obj in [json.loads(rec.read_text())] if isinstance(obj, dict) and obj.get("result") == "pass"}
replaced = {ln.split(":", 1)[1].strip() for path in mine for ln in fm(path).splitlines() if ln.startswith("split_from:")}
groups = {}
for path in mine: groups.setdefault(re.match(r"T-\d+", path.name).group(0), []).append(path)
open_paths = [xs[-1] for xs in groups.values() if not any(path.stem in passed or path.stem in replaced for path in xs)]; gate = "-"; goal = (m / "GOAL.md").read_text() if (m / "GOAL.md").is_file() else ""
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
      "${WORKER[@]}" "$task" --provider "$PROVIDER" --tier "$TIER" --feature "$FEATURE" --attempt "$round" </dev/null || true
      run=$(after worker "$n" run_id); [ -n "$run" ] || stop blocker "$id: no worker run started" 4
      if [ "$(after worker "$n" outcome)" = launch_failed ]; then
        seat=$(after worker "$n" seat); pok=0; "${PROBE[@]}" "$seat" --fleet "$MISSION/fleet.json" </dev/null || pok=$?
        if [ "$pok" -eq 0 ]; then event probe --arg task "$id" --arg seat "$seat" --arg result ok; else
          event probe --arg task "$id" --arg seat "$seat" --arg result broken
          export MISSION_RUN_BROKEN="${MISSION_RUN_BROKEN:+$MISSION_RUN_BROKEN }$seat"
          f12=$(jq -r 'any(.features[]; .id=="F012" and .passes==true)' "$MISSION/features.json")
          nxt=$(jq -r --arg t ".$TIER" --arg b " ${MISSION_RUN_BROKEN} " --argjson f12 "$f12" '.seats|keys|sort|map(select(. as $s | endswith($t) and ($b|contains(" "+$s+" ")|not) and ($f12 or ($s|startswith("claude.")|not))))|first//empty' "$MISSION/fleet.json")
          [ -n "$nxt" ] || stop blocker "$id: no usable $TIER seat left" 4
          event reroute --arg task "$id" --arg from "$seat" --arg to "$nxt"; PROVIDER=${nxt%%.*}; continue
        fi; fi
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
    if [ "$passed" = 1 ]; then continue; fi
    line2=$(sed -n '2p' "$task"); [[ $line2 == split_from:* ]] && stop decision_needed "$id: split from ${line2#split_from: }, 2 rounds without a pass" 3
    python3 -c '
import json,sys; from pathlib import Path; sys.path[:0]=[sys.argv[1]]; from observe_output import final_answer; mission,tid,feature,task=sys.argv[2:]; ev=[json.loads(line) for line in open(".tasks/events.jsonl") if line.strip()]; out=["Split %s feature: %s in front matter in %s into smaller tasks in the same task format because the task failed 2 rounds."%(task,feature,mission)]
def step(rnd): ver=next(e for e in ev if (e.get("event"),e.get("task"),e.get("round"))==("verify",tid,rnd)); rev=next((e for e in ev if (e.get("event"),e.get("task"),e.get("round"))==("review",tid,rnd)),None); brain=rev and next(e for e in reversed(ev[:ev.index(rev)]) if e.get("role")=="brain"); rc=brain and json.loads(Path(brain["receipt"]).read_text()); text=rc and final_answer(rc["provider"],Path(rc["log_path"]).read_bytes()); (out.append(text) if text else None); out.append("round %s: worker run %s, verification %s/verification/%s.json (%s), review %s"%(rnd,ver["run_id"],mission,ver["run_id"],ver["result"],rev["verdict"] if rev else "not run"))
step(1); step(2); Path(".tasks/requests").mkdir(parents=True,exist_ok=True); Path(".tasks/requests/%s-split.md"%tid).write_text("\n".join(out)+"\n")' "$DIR" "$MISSION" "$id" "$FEATURE" "$task"
    n=$(wc -l < .tasks/events.jsonl | tr -d ' '); req=".tasks/requests/$id-split.md"
    "${PLANSTEP[@]}" "$MISSION" plan --request "$req" </dev/null || true
    prun=$(after brain "$n" run_id); ids=$(python3 "$DIR/plan_extract.py" "$prun" "$MISSION/tasks" || true)
    [ -n "$prun" ] && [ -n "$ids" ] || stop blocker "$id: the split gave no tasks" 4
    python3 -c 'import re,sys; from pathlib import Path; feature,parent,root,raw=sys.argv[1:]; paths=[Path(root)/("%s.md"%t) for t in raw.split()]; pat=re.compile("(?m)^feature:[ \t]*%s[ \t]*$"%re.escape(feature)); texts=[p.read_text() for p in paths]; sys.exit(1) if any(not pat.search(t.split("---",2)[1]) for t in texts) else [p.write_text("".join(t.splitlines(True)[:1]+["split_from: %s\n"%parent]+t.splitlines(True)[1:])) for p,t in zip(paths,texts)]' "$FEATURE" "$id" "$MISSION/tasks" "$ids" || stop blocker "$id: a split task is not in $FEATURE" 4
    joined=${ids//$'\n'/ }; commit_mission "docs: $id split into $joined (decomposition miss)"
    event decomposition_miss --arg task "$id" --arg run_id "$prun" --arg request "$req" --arg tasks "$joined"
    exec bash "$0" "$MISSION" --provider "$PROVIDER" --feature "$FEATURE" --tier "$TIER"
  done
fi
[ "$GATE" = "-" ] && stop decision_needed "$FEATURE: every task passed; accept it" 3
stop gate_reached "$GATE" 0
