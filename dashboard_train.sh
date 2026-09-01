#!/bin/bash
# Lightweight training dashboard — only SFT / DPO / encoder + gpu + checkpoints.
# Does NOT replace dashboard.sh / status.sh. One SSH round-trip per refresh.
#
#   ./dashboard_train.sh              live (10s)
#   ./dashboard_train.sh --once       one shot
#   ./dashboard_train.sh -n 30        every 30s
#   ./dashboard_train.sh --once localhost   # check local machine instead

WATCH=1
INTERVAL=10
H="oracle-gpu"
while [ $# -gt 0 ]; do
  case "$1" in
    --once) WATCH=0; shift ;;
    -n) INTERVAL=$2; shift 2 ;;
    *)  H=$1; shift ;;
  esac
done

CTL=/tmp/.oracle-train-dash-%r@%h:%p
SSHOPTS="-o BatchMode=yes -o ConnectTimeout=6 -o ControlMaster=auto -o ControlPath=$CTL -o ControlPersist=120"
R() { ssh $SSHOPTS "$H" "bash -lc '$1'" 2>/dev/null; }
cd "$(dirname "$0")" || exit 1

GREEN=$'\e[32m'; RED=$'\e[31m'; YELLOW=$'\e[33m'; CYAN=$'\e[36m'; DIM=$'\e[2m'; BOLD=$'\e[1m'; OFF=$'\e[0m'

bar() { # bar done total [width]
  local done=$1 total=$2 w=${3:-20}
  local pct=0; [ "$total" -gt 0 ] 2>/dev/null && pct=$(( done * 100 / total ))
  local filled=$(( done * w / total )); [ "$filled" -gt "$w" ] && filled=$w; [ "$filled" -lt 0 ] && filled=0
  local i out=''
  for ((i = 0; i < filled; i++)); do out+='#'; done
  for ((i = filled; i < w; i++)); do out+='.'; done
  printf '%s %3d%%' "$out" "$pct"
}
sec() { printf '\n%s%s%s\n' "$BOLD$CYAN" "$1" "$OFF"; }
job() { local c; [ "$2" = green ] && c=$GREEN; [ "$2" = red ] && c=$RED; [ "$2" = yellow ] && c=$YELLOW; printf '  %s%-14s %s%s\n' "$c" "$1" "$3" "$OFF"; }

# ---- scoring (score_v4.sh runs LOCALLY and tunnels to the box) --------------
# Progress comes from the rows files, not the log: `basic_bench.py | tail -18`
# buffers a whole suite, so a silent log is normal mid-suite and would read as
# stalled. data/<stem>_<tag>.jsonl is the durable per-suite signal.
# Log path: $SCORE_LOG if set, else the newest scratchpad score_v4_run*.log.
SCORE_PY=$([ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

scoring_section() {
  sec "scoring (local)"
  local pid slog age elapsed
  pid=$(pgrep -af 'score_v4\.sh' | grep -vE 'zsh -c|bash -c|grep' | head -1 | awk '{print $1}')
  # Newest of ANY scoring log: a resume run writes resume_*.log, and locking
  # onto a stale score_v4_run*.log makes a healthy run read as STALLED (31 Aug).
  slog=${SCORE_LOG:-$(ls -t /tmp/claude-*/*/*/scratchpad/score_v4_run*.log \
                            /tmp/claude-*/*/*/scratchpad/resume_*.log 2>/dev/null | head -1)}

  # 12 = 4 checkpoints x 3 suites; the denominator score_v4.sh works through.
  local made
  made=$(ls data/basic_bench_v4.jsonl data/heldout_mech_v4.jsonl data/heldout_clean_v4.jsonl \
            data/basic_bench_v4_seed7.jsonl data/heldout_mech_v4_seed7.jsonl data/heldout_clean_v4_seed7.jsonl \
            data/basic_bench_v4_ep1.jsonl data/heldout_mech_v4_ep1.jsonl data/heldout_clean_v4_ep1.jsonl \
            data/basic_bench_v4_ep1_seed7.jsonl data/heldout_mech_v4_ep1_seed7.jsonl data/heldout_clean_v4_ep1_seed7.jsonl \
            2>/dev/null | wc -l)

  if [ -n "$pid" ]; then
    elapsed=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')
    # GPU idle while alive is the 31 Aug hang signature: server up, script in
    # do_wait, nothing generating. Log age alone cannot tell those apart.
    local util; util=$(echo "$GPU" | awk -F, '{gsub(/[^0-9]/,"",$3); print $3}')
    age=-1; [ -n "$slog" ] && [ -f "$slog" ] && age=$(( ($(date +%s) - $(stat -c %Y "$slog")) / 60 ))
    if [ -n "$util" ] && [ "$util" -le 2 ] 2>/dev/null && [ "$age" -gt 20 ] 2>/dev/null; then
      job score red "running but STALLED (gpu ${util}%, ${age}m since log)  pid $pid"
    else
      job score green "running  pid $pid  elapsed ${elapsed:-?}  gpu ${util:-?}%"
    fi
  elif [ "$made" -eq 12 ]; then
    job score green "complete — all 12 suites scored"
  elif [ "$made" -gt 0 ]; then
    job score yellow "not running — $made/12 suites on disk (interrupted?)"
  else
    job score yellow "not started    ./score_v4.sh all"
  fi

  printf '  %-14s ' "suites"; bar "$made" 12 20; printf '  %d/12\n' "$made"
  [ -n "$slog" ] && printf '  %s%-14s %s%s\n' "$DIM" "log" "$slog" "$OFF"

  # Current suite: the last `-- bench/...` line the log flushed.
  if [ -n "$slog" ] && [ -f "$slog" ]; then
    local cur; cur=$(grep -E '^(=== |  -- bench/)' "$slog" 2>/dev/null | tail -2 | tr '\n' ' ' | cut -c1-88)
    [ -n "$cur" ] && printf '  %s%-14s %s%s\n' "$DIM" "at" "$cur" "$OFF"
  fi

  printf '\n  %s%-14s %-13s %-13s %-13s %s%s\n' "$DIM" "tag" "basic n/fa" "mech n/unloc" "clean n/fa" "err" "$OFF"
  "$SCORE_PY" - <<'PYTBL' 2>/dev/null
import json, os
# Per suite, never pooled: heldout_clean is all-clean and heldout_mech all-buggy,
# so pooling lets one dilute the other into a rate no suite actually has.
# Denominator is total rows, matching basic_bench.py's own printed false-alarm
# figure -- the v2 4-15% band was computed that way and must stay comparable.
for t in ["v4", "v4_seed7", "v4_ep1", "v4_ep1_seed7"]:
    cells, err, seen = [], 0, False
    for stem, kind in [("basic_bench", "fa"), ("heldout_mech", "unloc"), ("heldout_clean", "fa")]:
        p = f"data/{stem}_{t}.jsonl"
        if not os.path.exists(p):
            cells.append("."); continue
        try:
            rows = [json.loads(l) for l in open(p) if l.strip()]
        except Exception:
            cells.append("bad"); continue
        seen = True
        n = len(rows)
        err += sum(1 for r in rows if r.get("error"))
        if kind == "fa":
            fa = sum(1 for r in rows if r.get("false_alarm"))
            cells.append(f"{n} / {round(100*fa/n) if n else 0}%")
        else:
            cells.append(f"{n} / {sum(1 for r in rows if r.get('unconfirmed'))}")
    print(f"  {t:<14} {cells[0]:<13} {cells[1]:<13} {cells[2]:<13} {err if seen else '-'}")
PYTBL
  printf '  %sfa=false alarms (bench denominator, total rows); unloc=right verdict, defect unnamed%s\n' "$DIM" "$OFF"
  printf '  %s./score_v4.sh --report is authoritative; a single seed is a point estimate%s\n' "$DIM" "$OFF"
}

# ---- control / eval runs (local driver, model served on the box) -----------
# For the base-model and second-model controls run through
# `bench/real_commits.py --run`, which are NOT part of score_v*.sh.
#
# Two reasons the obvious progress signals do not work here:
#   - the rows file is written in ONE pass after the last commit
#     (real_commits.py:196), so a row count reads 0/40 for the entire run;
#   - the driver's own [i/n] lines were block-buffered into an 8KB buffer a
#     40-commit run never fills, so its log stayed empty until exit (fixed
#     1 Sep with line_buffering, but old logs still behave that way).
# The signal that always works is on the BOX: serve.py logs one
# "N chars in Xs" line per generation. Note it counts generations since the
# SERVER started, so it over-reads if one server is reused for several runs.
control_section() {
  sec "control run (local driver -> $H)"
  local pid target total served model elapsed base
  pid=$(pgrep -af 'real_commits\.py --run' | grep -vE 'zsh -c|bash -c|grep' | head -1 | awk '{print $1}')
  target=$(pgrep -af 'real_commits\.py --run' | sed -n 's/.*--run \([^ ]*\).*/\1/p' | head -1)
  served=$(echo "$RAW" | grep '^SERVE_N=' | cut -d= -f2-)
  model=$(echo "$RAW"  | grep '^SERVE_MODEL=' | cut -d= -f2-)
  [ -z "$served" ] && served=0

  if [ -n "$pid" ]; then
    elapsed=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')
    base=$(basename "${target:-?}")
    total=40; [ -f "$target" ] && total=$(wc -l < "$target")
    job control green "running  pid $pid  elapsed ${elapsed:-?}  $base"
    printf '  %-14s ' "generated"; bar "$served" "$total" 20; printf '  %s/%s\n' "$served" "$total"
    printf '  %s%-14s %s%s\n' "$DIM" "rows" "written only at exit — 0 mid-run is normal" "$OFF"
  else
    job control yellow "idle — no real_commits.py --run in flight"
  fi

  # Which checkpoint is actually answering. Serving the wrong one is the single
  # easiest way to spend an hour measuring nothing, and it has happened twice.
  if [ -n "$model" ]; then
    printf '  %s%-14s %s%s\n' "$DIM" "serving" "$model" "$OFF"
  else
    printf '  %s%-14s %s%s\n' "$DIM" "serving" "no llm_explainer.serve on $H" "$OFF"
  fi

  # Completed control runs: answered / total, so a half-finished file is visible
  # rather than looking the same as a complete one.
  local f
  for f in data/real_commits_*.jsonl; do
    [ -f "$f" ] || continue
    case "$f" in *real_commits.jsonl) continue ;; esac
    "$SCORE_PY" - "$f" <<'PYROW' 2>/dev/null
import json, sys
p = sys.argv[1]
rows = [json.loads(l) for l in open(p) if l.strip()]
ans = sum(1 for r in rows if isinstance(r.get("predicted"), dict) and r["predicted"].get("summary") is not None)
err = sum(1 for r in rows if r.get("error"))
find = sum(len((r.get("predicted") or {}).get("findings") or []) for r in rows)
tag = p.split("real_commits_")[-1].removesuffix(".jsonl")
print(f"  {'':14}{tag:<16} {ans}/{len(rows)} answered  {find:>3} findings  {err} err")
PYROW
  done
}

# ponytail: single SSH call for all remote state; split if you need per-field timeouts/retries.
render() {
printf '%sORACLE train%s   %s   box: %s   refresh %ss%s\n' "$BOLD" "$OFF" "$(date +%H:%M:%S)" "$H" "$INTERVAL" "$DIM(ctrl-c to stop)$OFF"

sec "datasets (local)"
# honest step count — catches the truncation bug where TRL drops prompt-overflow rows silently
for f in data/oracle_sft.jsonl data/oracle_dpo.jsonl data/sft_v2_pilot2.jsonl data/sft_mechanism_v1.jsonl; do
  [ -f "$f" ] || continue
  n=$(wc -l < "$f")
  # SFT 2 epochs, DPO 1 epoch, divisor 8 (batch1 * accum8)
  epochs=2; [[ "$f" == *dpo* ]] && epochs=1
  steps=$(( n * epochs / 8 ))
  printf '  %-30s %5d rows  → ~%4d steps (%dx epochs /8)\n' "$(basename "$f")" "$n" "$steps" "$epochs"
done
[ -f data/oracle_sft.jsonl ] || printf '  ${DIM}no data/oracle_sft.jsonl — build with: python main.py build-sft --mock${OFF}\n'

sec "training (on $H)"
# One remote call — SFT + DPO + encoder + log tails. Keeps the refresh light on a slow link.
RAW=$(R '
  for NAME in SFT DPO ENC GATE; do
    case $NAME in
      SFT) pat="fine_tuning[.]train_sft"; logs=$(ls -t ~/oracle/sft*.log ~/oracle/train_sft*.log 2>/dev/null | head -1);;
      DPO) pat="fine_tuning[.]train_dpo"; logs=$(ls -t ~/oracle/dpo*.log ~/oracle/train_dpo*.log 2>/dev/null | head -1);;
      ENC) pat="ml_model[.]train_encoder"; logs=$(ls -t ~/oracle/encoder*.log 2>/dev/null | head -1);;
      GATE) pat="ml_model[.]train_gate"; logs=$(ls -t ~/oracle/gate*.log 2>/dev/null | head -1);;
    esac
    if pgrep -f "$pat" >/dev/null; then echo "${NAME}=RUN"; else echo "${NAME}=IDLE"; fi
    echo "${NAME}_LOG=${logs:-none}"
    if [ -n "$logs" ] && [ -f "$logs" ]; then
      # TRL tqdm bar or HF step log — whichever is freshest
      line=$(tr "\r" "\n" < "$logs" 2>/dev/null | grep -E "[0-9]+%\\||[0-9]+/[0-9]+ \\[|loss|epoch" | tail -1 | cut -c1-90)
      echo "${NAME}_PROG=${line:-—}"
      # age of log in minutes
      echo "${NAME}_AGE=$(( ($(date +%s) - $(stat -c %Y "$logs" 2>/dev/null || echo 0)) / 60 ))"
    else
      echo "${NAME}_PROG=—"
      echo "${NAME}_AGE=-1"
    fi
  done
  # keep this as its own line so the parser stays trivial
  nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null | tr -d "\n" | sed "s/^/GPU:/"
  echo ""
  # Inference server: which checkpoint is being served, and how many generations
  # it has completed. serve.py logs one "N chars in Xs" line per request, which
  # is the only per-commit signal a control run has - see control_section().
  SLOG=$(ls -t ~/oracle/serve*.log 2>/dev/null | head -1)
  echo "SERVE_LOG=${SLOG:-none}"
  if [ -n "$SLOG" ] && [ -f "$SLOG" ]; then
    echo "SERVE_N=$(tr "\r" "\n" < "$SLOG" 2>/dev/null | grep -acE "chars in [0-9.]+s")"
  else
    echo "SERVE_N=0"
  fi
  echo "SERVE_MODEL=$(pgrep -af "[l]lm_explainer.serve" | sed -n "s/.*--model \([^ ]*\).*/\1/p" | head -1)"
  # checkpoints — newest first, with ages
  echo "CKPT_START"
  cd ~/oracle/artifacts 2>/dev/null && stat -c "%Y %n" */adapter_model.safetensors */model.safetensors 2>/dev/null | sort -rn | head -6 | while read ts path; do
    age=$(( ($(date +%s) - ts) / 3600 ))
    printf "%s|%sh ago\n" "$path" "$age"
  done
  echo "CKPT_END"
')

if [ -z "$RAW" ]; then
  job sft yellow "box unreachable — trying local pgrep"
  pgrep -f "fine_tuning.train_sft" >/dev/null && job sft green "running (local)" || job sft yellow "idle (local)"
  pgrep -f "fine_tuning.train_dpo" >/dev/null && job dpo green "running (local)" || job dpo yellow "idle (local)"
  pgrep -f "ml_model.train_encoder" >/dev/null && job encoder green "running (local)" || job encoder yellow "idle (local)"
  pgrep -f "ml_model.train_gate" >/dev/null && job gate green "running (local)" || job gate yellow "idle (local)"
else
  # parse the single blob — no second SSH
  get() { echo "$RAW" | grep "^$1=" | cut -d= -f2-; }
  line_for() { echo "$RAW" | grep "^$1_PROG=" | cut -d= -f2-; }

  SFT_STATE=$(get SFT); SFT_LOG=$(get SFT_LOG); SFT_AGE=$(get SFT_AGE); SFT_PROG=$(line_for SFT)
  DPO_STATE=$(get DPO); DPO_LOG=$(get DPO_LOG); DPO_AGE=$(get DPO_AGE); DPO_PROG=$(line_for DPO)
  ENC_STATE=$(get ENC); ENC_LOG=$(get ENC_LOG); ENC_AGE=$(get ENC_AGE); ENC_PROG=$(line_for ENC)
  GATE_STATE=$(get GATE); GATE_LOG=$(get GATE_LOG); GATE_AGE=$(get GATE_AGE); GATE_PROG=$(line_for GATE)

  for kind in SFT DPO ENC GATE; do
    eval "STATE=\$${kind}_STATE; LOG=\$${kind}_LOG; AGE=\$${kind}_AGE; PROG=\$${kind}_PROG"
    name=$(echo "$kind" | tr '[:upper:]' '[:lower:]')
    logbase=$(basename "$LOG" 2>/dev/null)
    [ "$logbase" = "none" ] && logbase="no log"
    if [[ "$STATE" == *RUN* ]]; then
      if [ "$AGE" -gt 15 ] 2>/dev/null; then
        job "$name" red "running but STUCK (${AGE}m since log)  $logbase"
      else
        job "$name" green "running  $logbase  ${PROG:0:62}"
      fi
    else
      human=""; if [ "$AGE" -ge 0 ] 2>/dev/null; then
        if [ "$AGE" -lt 60 ]; then human="${AGE}m ago"
        elif [ "$AGE" -lt 1440 ]; then human="$((AGE/60))h ago"
        else human="$((AGE/1440))d ago"; fi
        human=" ($human)"
      fi
      extra=""; [ "$PROG" != "—" ] && extra="  ${PROG:0:58}"
      job "$name" yellow "idle  $logbase${human}${extra}"
    fi
  done

  GPU=$(echo "$RAW" | grep "^GPU:" | sed 's/^GPU://')
  if [ -n "$GPU" ]; then
    printf '  %s%-14s %s%s\n' "$DIM" "gpu" "$GPU" "$OFF"
  else
    printf '  %s%-14s %s%s\n' "$DIM" "gpu" "unreachable / no nvidia-smi" "$OFF"
  fi

  sec "checkpoints (on $H)"
  CKPT=$(echo "$RAW" | sed -n '/CKPT_START/,/CKPT_END/p' | grep -v CKPT)
  if [ -n "$CKPT" ]; then
    echo "$CKPT" | while IFS='|' read path age; do printf '  %-48s %s\n' "$path" "$age"; done
  else
    printf '  %sno adapter/model.safetensors yet%s\n' "$DIM" "$OFF"
    # hint what WOULD appear
    printf '  %sartifacts/sft-adapter  artifacts/dpo-adapter  artifacts/oracle-merged%s\n' "$DIM" "$OFF"
  fi
fi

scoring_section
control_section

printf '\n%s tip: ./dashboard.sh for the full view (labelling/variance/bench) %s\n' "$DIM" "$OFF"
}

if [ "$WATCH" = 1 ]; then
  trap 'ssh $SSHOPTS -O exit "$H" 2>/dev/null; printf "\n"; exit 0' INT
  while :; do
    out=$(render)
    clear
    printf '%s\n' "$out"
    printf -- '--- %s   refresh %ss ---\n' "$(date +%H:%M:%S)" "$INTERVAL"
    sleep "$INTERVAL"
  done
else
  render
fi
