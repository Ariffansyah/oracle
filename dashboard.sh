#!/bin/bash
# Live dashboard for everything ORACLE. Watch-mode TUI by default; one-shot
# with `--once`. Stays a single file, bash only, no dependencies.
#
#   ./dashboard.sh                 live dashboard (10s refresh)
#   ./dashboard.sh -n 30           refresh every 30s
#   ./dashboard.sh --once          one shot, no repaint
#
# Status conventions: green = advancing, red = stuck/dead, yellow = idle.
# A job is "stuck" when its log or output file has not grown past the stale
# window even though the process is running (the labelling watchdog died at
# 12:11 once and nothing restarted it — this dashboard exists to catch that).

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

CTL=/tmp/.oracle-dash-%r@%h:%p
SSHOPTS="-o BatchMode=yes -o ConnectTimeout=8 -o ControlMaster=auto
         -o ControlPath=$CTL -o ControlPersist=120"
R() { ssh $SSHOPTS "$H" "bash -lc '$1'" 2>/dev/null; }
cd "$(dirname "$0")" || exit 1

GREEN=$'\e[32m'; RED=$'\e[31m'; YELLOW=$'\e[33m'; CYAN=$'\e[36m'; DIM=$'\e[2m'; BOLD=$'\e[1m'; OFF=$'\e[0m'

fresh() { # seconds since a file was last written
  local f=$1
  [ -f "$f" ] && echo $(( $(date +%s) - $(stat -c %Y "$f") )) || echo 99999
}

bar() { # bar <done> <total> [width]
  local done=$1 total=$2 w=${3:-24}
  local pct=0; [ "$total" -gt 0 ] 2>/dev/null && pct=$(( done * 100 / total ))
  local filled=$(( done * w / total ))
  printf '%*s' "$filled" '' | tr ' ' '#'
  printf '%*s' "$((w - filled))" '' | tr ' ' '-'
  printf ' %3d%%' "$pct"
}

sec() { printf '\n%s%s%s\n' "$BOLD$CYAN" "$1" "$OFF"; }
job() { # job <name> <state:green|red|yellow> <detail>
  local c; [ "$2" = green ] && c=$GREEN; [ "$2" = red ] && c=$RED; [ "$2" = yellow ] && c=$YELLOW
  printf '  %s%-24s %s%s%s\n' "$c" "$1" "$3" "$OFF"
}

render() {

printf '%sORACLE dashboard%s   %s   box: %s   refresh %ss%s\n\n' \
  "$BOLD" "$OFF" "$(date +%H:%M:%S)" "$H" "$INTERVAL" "$DIM(ctrl-c to stop)$OFF"

sec "labelling (teacher labels, resume-safe)"
# Two corpora, one daily token budget, so they run in sequence: the general
# mined sample first, then the targeted guard corpus. The watchdog decides the
# phase the same way, off the raw file's attempt count.
if [ "$(wc -l < data/labelled_multilang_raw.jsonl 2>/dev/null || echo 0)" -lt 959 ]; then
  LAB_PHASE="pass 1 — general corpus"
  LAB_FILE=data/labelled_multilang.jsonl
  LAB_LOG=label_multilang.log
  LAB_TOTAL=959
else
  LAB_PHASE="pass 2 — guard corpus"
  LAB_FILE=data/labelled_guards.jsonl
  LAB_LOG=label_guards.log
  LAB_TOTAL=480
fi
LAB_DONE=$(wc -l < "$LAB_FILE" 2>/dev/null || echo 0)
LAB_N=$(grep -oE "[0-9]+ commits to label" "$LAB_LOG" 2>/dev/null | grep -oE "[0-9]+" | tail -1)
LAB_TOTAL=${LAB_N:-$LAB_TOTAL}
job phase yellow "$LAB_PHASE"
if pgrep -f "corpus[.]label" >/dev/null; then
  LF=$(fresh "$LAB_FILE")
  # Groq's IP throttle makes single commits take 5-15 min; only cry wolf at
  # the watchdog's own staleness window.
  if [ "$LF" -gt 900 ]; then
    job labelling red "running but STUCK ($((LF/60))m since last record)"
  else
    job labelling green "running   $(bar "$LAB_DONE" "$LAB_TOTAL")   $LAB_DONE/$LAB_TOTAL"
  fi
else
  job labelling yellow "idle   $(bar "$LAB_DONE" "$LAB_TOTAL")   $LAB_DONE/$LAB_TOTAL"
fi
WLOG=label_watch.log
if pgrep -f "label_watch[.]sh" >/dev/null; then
  # The watchdog's log is event-based: silence means no kills, which is
  # healthy. Liveness = the watchdog process itself; health = records advance
  # (checked above on the labelling row).
  job watchdog green "alive (event log: silence = no kills = good)"
else
  job watchdog red "DOWN — labelling will stop silently"
fi
[ -f "$WLOG" ] && grep -E "stale at" "$WLOG" | tail -1 | sed "s/^/    $DIM/;s/$/$OFF/"
tr '\r' '\n' < label_multilang.log 2>/dev/null | grep -E "^  [0-9]+/[0-9]+  kept" | tail -1 \
  | sed "s/^/    $DIM/;s/$/$OFF/"

sec "training (on $H)"
for probe in sft dpo; do
  state=$(R "pgrep -f \"fine_tuning[.]train_$probe\" >/dev/null && echo green || echo yellow")
  if [ "$state" = green ]; then
    detail=$(R "tr \"\r\" \"\n\" < \$(ls -t ~/oracle/$probe*.log 2>/dev/null | head -1) 2>/dev/null | grep -E '[0-9]+/[0-9]+ \[' | tail -1")
    job "$probe" green "running   ${detail:0:60}"
  else
    job "$probe" yellow "idle"
  fi
done
enc_state=$(R 'pgrep -f "ml_model[.]train_encoder" >/dev/null && echo green || echo yellow')
if [ "$enc_state" = green ]; then
  detail=$(R 'tr "\r" "\n" < ~/oracle/encoder_full.log 2>/dev/null | grep -E "epoch |best " | tail -1')
  job encoder green "running   ${detail:0:60}"
else
  job encoder yellow "idle"
fi

sec "gpu (on $H)"
R 'nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader 2>/dev/null | sed "s/^/  /"' \
  || echo "  box unreachable (powered off?)"

sec "evals (on $H)"
EV=$(R 'ps -eo etimes,args | grep "[e]valuate.py" | head -1' | sed 's/^[[:space:]]*//')
if [ -n "$EV" ]; then
  ELAPSED=${EV%% *}
  MODEL=$(printf '%s' "$EV" | sed -n 's/.*--model \([^ ]*\).*/\1/p')
  PROG=$(R 'tr "\r" "\n" < "$(ls -t ~/oracle/detect*.log ~/oracle/cve*.log 2>/dev/null | head -1)" 2>/dev/null | grep -E "^  [0-9]+/[0-9]+ " | tail -1')
  DONE=$(printf '%s' "$PROG" | sed -n 's|^ *\([0-9]*\)/.*|\1|p')
  TOTAL=$(printf '%s' "$PROG" | sed -n 's|^ *[0-9]*/\([0-9]*\).*|\1|p')
  job eval green "$MODEL   $(bar "${DONE:-0}" "${TOTAL:-1}")   ${DONE:-0}/${TOTAL:-1}"
else
  job eval yellow "idle"
fi

sec "local corpus"
for f in data/labelled.jsonl data/labelled_multilang.jsonl data/multilang_commits.jsonl \
         data/guard_commits.jsonl data/labelled_guards.jsonl \
         data/contrastive_pairs.jsonl data/apachejit_commits.jsonl; do
  [ -f "$f" ] && printf '  %-34s %6d\n' "$(basename "$f")" "$(wc -l < "$f")"
done

sec "serving"
curl -s -m 5 http://localhost:8111/api/tags >/dev/null 2>&1 \
  && job serve green "up on localhost:8111 (TUI ready)" \
  || job serve yellow "down (box off or ./serve.sh stop)"

sec "errors (on $H)"
R 'grep -hE "^[A-Za-z]*Error|Traceback" ~/oracle/sft.log ~/oracle/dpo.log 2>/dev/null | tail -2 | sed "s/^/  /"'

printf '\n'
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