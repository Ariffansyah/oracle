#!/bin/bash
# Training progress only: SFT / DPO / encoder / gate, the step bar, the loss
# trace, the held-out kill gate, GPU, and the newest checkpoint. One SSH
# round-trip per refresh.
#
# Trimmed on 6 Sep from a five-section version that also rendered the local
# corpus table, the scoring suites, the exec-arm grades and the control-run
# tracker. Those live in ./dashboard.sh; this one is for watching a run.
#
# The line that matters during a run is `holdout`, not `loss`. The 2 Sep repair
# run sat at loss 0.23 with token accuracy 0.93 while its held-out recall was
# 0.000 -- the loss looked healthy the whole way down. Recall 0.000 on a
# non-zero positive count is the pre-registered kill.
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

render() {
printf '%sORACLE train%s   %s   box: %s   refresh %ss%s\n' "$BOLD" "$OFF" "$(date +%H:%M:%S)" "$H" "$INTERVAL" "$DIM(ctrl-c to stop)$OFF"

# ONE SSH round-trip. Everything below parses this blob; nothing else shells out.
RAW=$(R '
  for NAME in SFT DPO ENC GATE; do
    case $NAME in
      # run_*.log first: every launcher since 1 Sep writes run_<name>.log, and
      # matching only sft*/train_sft* rendered a LIVE run as "idle  no log".
      SFT) pat="fine_tuning[.]train_sft"; logs=$(ls -t ~/oracle/run_*.log ~/oracle/sft*.log ~/oracle/train_sft*.log 2>/dev/null | head -1);;
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
      echo "${NAME}_AGE=$(( ($(date +%s) - $(stat -c %Y "$logs" 2>/dev/null || echo 0)) / 60 ))"
    else
      echo "${NAME}_PROG=—"
      echo "${NAME}_AGE=-1"
    fi
  done
  # Live run detail. The tqdm bar carries step, pace and ETA; logging_steps=5
  # carries the loss. Both are on \r-separated lines, hence the tr.
  RLOG=$(ls -t ~/oracle/run_*.log 2>/dev/null | head -1)
  if [ -n "$RLOG" ] && [ -f "$RLOG" ]; then
    BAR=$(tr "\r" "\n" < "$RLOG" 2>/dev/null | grep -oE "[0-9]+/[0-9]+ \[[0-9:]+<[0-9:?]+, +[0-9.]+s/it\]" | tail -1)
    echo "RUN_BAR=${BAR:-—}"
    echo "RUN_LOSS=$(grep -ao "{.loss.*epoch.: .[0-9.]*.}" "$RLOG" 2>/dev/null | tail -1 | cut -c1-96)"
    # Count via grad_norm, not "loss": the latter needs a single quote inside a
    # single-quoted remote heredoc and came back 0 every refresh. grad_norm
    # appears exactly once per logged point and needs no quoting.
    echo "RUN_NLOSS=$(grep -aoc grad_norm "$RLOG" 2>/dev/null)"
    echo "RUN_LOG=$RLOG"
    echo "RUN_AGE=$(( ($(date +%s) - $(stat -c %Y "$RLOG" 2>/dev/null || echo 0)) / 60 ))"
    echo "GATE_LINE=$(tr "\r" "\n" < "$RLOG" 2>/dev/null | grep -a "holdout @ step" | tail -1 | cut -c1-104)"
    echo "GATE_PREV=$(tr "\r" "\n" < "$RLOG" 2>/dev/null | grep -a "holdout @ step" | tail -2 | head -1 | cut -c1-104)"
    echo "GATE_N=$(tr "\r" "\n" < "$RLOG" 2>/dev/null | grep -ac "holdout @ step")"
    echo "GATE_ZERO=$(grep -ac "RECALL IS ZERO" "$RLOG" 2>/dev/null)"
  else
    echo "RUN_BAR=—"; echo "RUN_LOSS="; echo "RUN_NLOSS=0"
    echo "RUN_LOG="; echo "RUN_AGE=-1"; echo "GATE_LINE="; echo "GATE_PREV="; echo "GATE_N=0"; echo "GATE_ZERO=0"
  fi
  echo "RUN_PEAK=$(cat /tmp/peak_vram_run 2>/dev/null || echo -)"
  # The epoch-1 pause watcher. Kept because "armed" is not visible anywhere
  # else: it is a sleeping process whose whole job is to fire once, hours from
  # now, and an unarmed one looks exactly like an armed one until the checkpoint
  # sails past. Renders nothing when off.
  if pgrep -f "[p]ause_after_epoch1" >/dev/null; then echo "PAUSE=ARMED"; else echo "PAUSE=OFF"; fi
  echo "PAUSE_LOG=$(tail -1 ~/oracle/pause_ep1.log 2>/dev/null | cut -c1-72)"
  # keep this as its own line so the parser stays trivial
  nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null | tr -d "\n" | sed "s/^/GPU:/"
  echo ""
  # newest checkpoint only — the run being watched is the one that wrote it
  cd ~/oracle/artifacts 2>/dev/null && stat -c "%Y %n" */adapter_model.safetensors */model.safetensors 2>/dev/null | sort -rn | head -1 | while read ts path; do
    printf "CKPT=%s|%sh ago\n" "$path" "$(( ($(date +%s) - ts) / 3600 ))"
  done
')

get() { echo "$RAW" | grep "^$1=" | cut -d= -f2-; }
line_for() { echo "$RAW" | grep "^$1_PROG=" | cut -d= -f2-; }
GPU=$(echo "$RAW" | grep "^GPU:" | sed 's/^GPU://')

sec "training (on $H)"
if [ -z "$RAW" ]; then
  job sft yellow "box unreachable — trying local pgrep"
  pgrep -f "fine_tuning.train_sft" >/dev/null && job sft green "running (local)" || job sft yellow "idle (local)"
  pgrep -f "fine_tuning.train_dpo" >/dev/null && job dpo green "running (local)" || job dpo yellow "idle (local)"
  pgrep -f "ml_model.train_encoder" >/dev/null && job encoder green "running (local)" || job encoder yellow "idle (local)"
  pgrep -f "ml_model.train_gate" >/dev/null && job gate green "running (local)" || job gate yellow "idle (local)"
else
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

  if [ -n "$GPU" ]; then
    printf '  %s%-14s %s%s\n' "$DIM" "gpu" "$GPU" "$OFF"
  else
    printf '  %s%-14s %s%s\n' "$DIM" "gpu" "unreachable / no nvidia-smi" "$OFF"
  fi

  CKPT=$(get CKPT)
  [ -n "$CKPT" ] && printf '  %s%-14s %s  %s%s\n' "$DIM" "newest ckpt" "${CKPT%%|*}" "${CKPT#*|}" "$OFF"

  # Live run detail: step bar, pace, ETA, loss trace. On a card with no tensor
  # cores a step is ~110-400s depending on corpus, so the tqdm ETA is the number
  # that matters — a run that looks stalled is usually just mid-step.
  RUN_BAR=$(get RUN_BAR); RUN_LOSS=$(get RUN_LOSS)
  RUN_NLOSS=$(get RUN_NLOSS); RUN_PEAK=$(get RUN_PEAK); RUN_LOG=$(get RUN_LOG)
  RUN_AGE=$(get RUN_AGE)
  if [ -n "$RUN_BAR" ] && [ "$RUN_BAR" != "—" ]; then
    rh=""
    if [ "${RUN_AGE:--1}" -ge 0 ] 2>/dev/null; then
      if [ "$RUN_AGE" -lt 60 ]; then rh="${RUN_AGE}m ago"
      elif [ "$RUN_AGE" -lt 1440 ]; then rh="$((RUN_AGE/60))h ago"
      else rh="$((RUN_AGE/1440))d ago"; fi
    fi
    # Which log the bar and the holdout line below were read from. Only
    # ~/oracle/run_*.log on the box is scanned, so a run launched with its
    # output redirected somewhere else leaves a STALE completed bar here.
    if [[ "$SFT_STATE" != *RUN* ]]; then
      printf '  %s%-14s %s%s  — not a live run%s\n' "$DIM" "from" \
             "$(basename "${RUN_LOG:-?}")" "${rh:+ ($rh)}" "$OFF"
    fi
    cur=${RUN_BAR%%/*}; rest=${RUN_BAR#*/}; tot=${rest%% *}
    printf '  %-14s ' "steps"; bar "$cur" "$tot" 20; printf '  %s\n' "$RUN_BAR"
    [ -n "$RUN_LOSS" ] && printf '  %s%-14s %s%s\n' "$DIM" "last log" "$RUN_LOSS" "$OFF"
    # 0.2 is the memorisation line agreed for this corpus (1034 rows, r=16).
    lastloss=$(echo "$RUN_LOSS" | grep -ao "loss.: .[0-9.]*" | grep -ao "[0-9.]*$")
    if [ -n "$lastloss" ]; then
      if awk -v l="$lastloss" 'BEGIN{exit !(l < 0.2)}'; then
        job loss red "COLLAPSED — loss $lastloss < 0.2, suspect memorisation"
      else
        printf '  %s%-14s loss %s over %s logged points (>0.2 ok)%s\n' \
               "$DIM" "guard" "$lastloss" "$RUN_NLOSS" "$OFF"
      fi
    fi
  fi
  [ "$RUN_PEAK" != "-" ] && [ -n "$RUN_PEAK" ] && \
    printf '  %s%-14s %s MiB (card is 6144; >5900 risks OOM at 2048)%s\n' "$DIM" "peak vram" "$RUN_PEAK" "$OFF"

  # ---- the kill gate -------------------------------------------------------
  # Recall 0.000 on a non-zero positive count IS the 2 Sep failure repeating
  # (--verdict-weight 0.5 was killed at step 20 on exactly this line: recall
  # 0.000 / 14 positives, specificity 1.000, top1 0.767 = precisely the
  # negatives). Kill it, do not spend the epoch.
  GATE_LINE=$(get GATE_LINE); GATE_PREV=$(get GATE_PREV)
  GATE_N=$(get GATE_N); GATE_ZERO=$(get GATE_ZERO); RUN_LOG=$(get RUN_LOG)
  # `holdout`, not `gate` — `gate` is already the ml_model.train_gate job above.
  if [ -n "$GATE_LINE" ]; then
    rec=$(echo "$GATE_LINE" | grep -ao "recall [0-9.]*" | awk '{print $2}')
    pos=$(echo "$GATE_LINE" | grep -ao "on [0-9]* positives" | awk '{print $2}')
    zero=0
    [ -n "$rec" ] && [ -n "$pos" ] && [ "$pos" -gt 0 ] 2>/dev/null \
      && awk -v r="$rec" 'BEGIN{exit !(r == 0)}' && zero=1
    if [[ "$SFT_STATE" != *RUN* ]]; then
      # A dead run's last gate line is a postmortem, not an alarm: run_repair_w05
      # sits at recall 0.000 forever because it was correctly killed there.
      job holdout yellow "last run $(basename "${RUN_LOG:-?}")$([ "$zero" = 1 ] && echo "  (ended at recall 0.000 — killed)")"
    elif [ "$zero" = 1 ]; then
      job holdout red "RECALL 0.000 on $pos positives — KILL IT (pre-registered)"
    else
      job holdout green "held-out recall $rec on ${pos:-?} positives"
    fi
    printf '  %s%-14s %s%s\n' "$DIM" "" "${GATE_LINE#*] }" "$OFF"
    [ -n "$GATE_PREV" ] && [ "$GATE_PREV" != "$GATE_LINE" ] && \
      printf '  %s%-14s prev: %s%s\n' "$DIM" "" "${GATE_PREV#*] }" "$OFF"
    printf '  %s%-14s %s check(s) so far%s%s\n' "$DIM" "" "$GATE_N" \
           "$([ "${GATE_ZERO:-0}" -gt 0 ] 2>/dev/null && echo "  ($GATE_ZERO zero-recall warning(s) in log)")" "$OFF"
  elif [[ "$SFT_STATE" == *RUN* ]]; then
    printf '  %s%-14s no holdout line yet — launched without --eval-steps?%s\n' "$DIM" "holdout" "$OFF"
    printf '  %s%-14s watch: grep -a "holdout @ step" %s%s\n' \
           "$DIM" "" "${RUN_LOG:-~/oracle/run_exec.log}" "$OFF"
  fi

  PAUSE=$(get PAUSE); PAUSE_LOG=$(get PAUSE_LOG)
  if [ "$PAUSE" = "ARMED" ]; then
    printf '  %s%-14s stops at checkpoint-146, then epoch 2 waits for resume_repair.sh%s\n' \
           "$DIM" "pause" "$OFF"
    [ -n "$PAUSE_LOG" ] && printf '  %s%-14s %s%s\n' "$DIM" "" "$PAUSE_LOG" "$OFF"
  fi
fi

printf '\n%s tip: ./dashboard.sh for scoring, control runs and the corpus table %s\n' "$DIM" "$OFF"
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
