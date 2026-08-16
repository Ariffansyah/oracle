#!/bin/bash
# Where everything is, in one screen. Remote shell is fish, so every remote
# command goes through bash -lc.
#
#   ./status.sh              one shot
#   ./status.sh -w           refresh until interrupted
#   ./status.sh -w -n 30     ... every 30s
WATCH=0
INTERVAL=10
H=""
while [ $# -gt 0 ]; do
  case "$1" in
    -w|--watch) WATCH=1; shift ;;
    -n) INTERVAL=$2; shift 2 ;;
    *)  H=$1; shift ;;
  esac
done
H=${H:-oracle-gpu}

# One multiplexed SSH connection for every remote check. Without this each
# section pays a fresh handshake, which is what makes a watch loop slower than
# its own refresh interval.
CTL=/tmp/.oracle-status-%r@%h:%p
SSHOPTS="-o BatchMode=yes -o ConnectTimeout=8 -o ControlMaster=auto
         -o ControlPath=$CTL -o ControlPersist=120"
R() { ssh $SSHOPTS "$H" "bash -lc '$1'" 2>/dev/null; }
cd "$(dirname "$0")" || exit 1

report() {

echo "=== training (on $H) ==="
R 'pgrep -f "fine_tuning[.]train_sft" >/dev/null && echo "  SFT: running" || echo "  SFT: idle"
   pgrep -f "fine_tuning[.]train_dpo" >/dev/null && echo "  DPO: running" || echo "  DPO: idle"
   tr "\r" "\n" < "$(ls -t ~/oracle/sft*.log 2>/dev/null | head -1)" 2>/dev/null | grep -E "[0-9]+/[0-9]+ \[" | tail -1 | sed "s/^/  /"
   tr "\r" "\n" < ~/oracle/dpo.log 2>/dev/null | grep -E "[0-9]+/[0-9]+ \[" | tail -1 | sed "s/^/  /"'

echo "=== gpu ==="
R 'nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader | sed "s/^/  /"'

echo "=== checkpoints ==="
R 'for d in sft-adapter sft-cve dpo-adapter oracle-merged gate-encoder; do
     if [ -d ~/oracle/artifacts/$d ]; then
       echo "  $d: $(du -sh ~/oracle/artifacts/$d | cut -f1)"
     else echo "  $d: not built"; fi
   done
   ls -d ~/oracle/artifacts/*/checkpoint-* 2>/dev/null |
     sed "s|.*/artifacts/|  saved: |"'

echo "=== evals ==="
# etimes (seconds) not etime (D-HH:MM:SS): the ETA arithmetic below needs a
# number, and average rate over the whole run predicts better than the
# per-commit time the log prints, which swings with diff size.
# sed strips the left-padding ps adds to etimes; without it the first field is
# empty and every ETA computes as zero.
EV=$(R 'ps -eo etimes,args | grep "[e]valuate.py" | head -1' | sed 's/^[[:space:]]*//')
if [ -n "$EV" ]; then
  ELAPSED=${EV%% *}
  MODEL=$(printf '%s' "$EV" | sed -n 's/.*--model \([^ ]*\).*/\1/p')
  # Whichever eval log was written most recently — detection on ApacheJIT and
  # on CVEfixes use the same progress format but different files.
  PROG=$(R 'tr "\r" "\n" < "$(ls -t ~/oracle/detect*.log ~/oracle/cve*.log 2>/dev/null | head -1)" 2>/dev/null | grep -E "^  [0-9]+/[0-9]+ " | tail -1')
  DONE=$(printf '%s' "$PROG" | sed -n 's|^ *\([0-9]*\)/.*|\1|p')
  TOTAL=$(printf '%s' "$PROG" | sed -n 's|^ *[0-9]*/\([0-9]*\).*|\1|p')
  echo "  running: $MODEL"
  if [ -n "$DONE" ] && [ "$DONE" -gt 0 ] 2>/dev/null; then
    LEFT=$(( (TOTAL - DONE) * ELAPSED / DONE ))
    printf '  %s/%s   %ds/commit   ETA %dh%02dm   done ~%s\n' \
      "$DONE" "$TOTAL" "$((ELAPSED / DONE))" "$((LEFT/3600))" "$(((LEFT%3600)/60))" \
      "$(date -d "+$LEFT seconds" +%H:%M 2>/dev/null)"
  fi
else
  echo "  idle"
fi
R 'for log in ~/oracle/detect*.log ~/oracle/cve*.log ~/oracle/eval.log; do
     [ -f "$log" ] || continue
     line=$(tr "\r" "\n" < "$log" | grep -E "^  [0-9]+/[0-9]+ " | tail -1)
     [ -n "$line" ] && echo "  $(basename $log): $line"
   done
   for f in ~/oracle/data/eval_*.jsonl ~/oracle/data/detect_*.jsonl ~/oracle/data/cve_*.jsonl; do
     [ -f "$f" ] && [ "$(basename $f)" != "detect_eval.jsonl" ] &&
       printf "  %-22s %5d rows\n" "$(basename $f)" "$(wc -l < $f)"
   done
   tr "\r" "\n" < ~/oracle/detect.log 2>/dev/null | grep -E "^  (detection|valid JSON)" | tail -2'

echo "=== local jobs ==="
pgrep -f "corpus[.]label" >/dev/null && echo "  labelling: running" || echo "  labelling: idle"
# Progress of the newest labelling run, wherever its log was written.
LBL=$(ls -t /tmp/claude-*/*/*/scratchpad/relabel*.log logs/relabel*.log 2>/dev/null | head -1)
[ -n "$LBL" ] && grep -E "^  [0-9]+/[0-9]+  kept" "$LBL" | tail -1 | sed "s/^ */    /"
pgrep -f "corpus[.]fetch" >/dev/null && echo "  fetching:  running" || echo "  fetching:  idle"
pgrep -f "corpus[.]mine"  >/dev/null && echo "  mining:    running" || echo "  mining:    idle"

echo "=== corpus ==="
for f in data/labelled.jsonl data/labelled_train.jsonl data/labelled_heldout.jsonl \
         data/heldout_unhinted.jsonl data/mined.jsonl data/detect_eval.jsonl \
         data/cvefixes_eval.jsonl data/apachejit_commits.jsonl data/oracle_sft.jsonl \
         data/oracle_dpo_onpolicy.jsonl; do
  [ -f "$f" ] && printf '  %-34s %6d\n' "$(basename "$f")" "$(wc -l < "$f")"
done

echo "=== cvefixes ==="
CVE=data/cvefixes
if pgrep -f "[s]qlite3 CVEfixes.db" >/dev/null; then
  # Free space matters here: the dump expands several times over, and sqlite
  # dying on a full disk leaves a half-written database that looks complete.
  echo "  restore: RUNNING  ($(du -h $CVE/CVEfixes.db 2>/dev/null | cut -f1) written,\
 $(df -h --output=avail /home | tail -1 | tr -d ' ') free)"
  # Progress comes from how far zcat has read into the .sql.gz - the only
  # number that knows the denominator. The db size does not: it is compressed
  # SQL expanding into pages at an unknown ratio.
  GZ=$(ls $CVE/*/Data/*.sql.gz 2>/dev/null | head -1)
  ZPID=$(pgrep -f "sql\.gz" | head -1)
  if [ -n "$GZ" ] && [ -n "$ZPID" ]; then
    SIZE=$(stat -c %s "$GZ")
    POS=$(grep -h '^pos:' /proc/$ZPID/fdinfo/* 2>/dev/null | awk '{print $2}' | sort -rn | head -1)
    EL=$(ps -o etimes= -p "$ZPID" 2>/dev/null | tr -d ' ')
    if [ -n "$POS" ] && [ "$POS" -gt 0 ] 2>/dev/null && [ -n "$EL" ]; then
      LEFT=$(( (SIZE - POS) * EL / POS ))
      printf '  read %d%% of the dump   ETA %dh%02dm   done ~%s\n' \
        $(( POS * 100 / SIZE )) $((LEFT/3600)) $(((LEFT%3600)/60)) \
        "$(date -d "+$LEFT seconds" +%H:%M 2>/dev/null)"
    fi
  fi
elif [ -f "$CVE/CVEfixes.db" ]; then
  echo "  restore: done  ($(du -h $CVE/CVEfixes.db | cut -f1))"
  sqlite3 "$CVE/CVEfixes.db" \
    "select '  '||name||': '||(select count(*) from sqlite_master m2 where m2.name=m.name)
     from sqlite_master m where type='table' order by name;" 2>/dev/null | head -12
else
  echo "  not downloaded"
fi

echo "=== serving ==="
curl -s -m 5 http://localhost:8111/api/tags >/dev/null 2>&1 \
  && echo "  tuned model: up on localhost:8111" \
  || echo "  tuned model: down (ssh -f -N -L 8111:localhost:8111 $H, then start serve.py)"

echo "=== errors ==="
R 'grep -hE "^[A-Za-z]*Error|Traceback" ~/oracle/sft.log ~/oracle/dpo.log 2>/dev/null | tail -3 | sed "s/^/  /"'

}

if [ "$WATCH" = 1 ]; then
  trap 'ssh $SSHOPTS -O exit "$H" 2>/dev/null; echo; exit 0' INT
  while :; do
    out=$(report)                      # render fully, then repaint: a section
    clear                              # drawn as it arrives flickers badly
    printf '%s\n' "$out"
    printf -- '--- %s   refresh %ss   ctrl-c to stop ---\n' "$(date +%H:%M:%S)" "$INTERVAL"
    sleep "$INTERVAL"
  done
else
  report
fi
