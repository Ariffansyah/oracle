#!/bin/bash
# Live dashboard for everything ORACLE. Watch-mode TUI by default; one-shot
# with `--once`. Stays a single file, bash only, no dependencies.
#
#   ./dashboard.sh                 live dashboard (10s refresh)
#   ./dashboard.sh -n 30           refresh every 30s
#   ./dashboard.sh --once          one shot, no repaint
#
# Status conventions: green = advancing, red = stuck/dead, yellow = idle or
# blocked on something external. A job is "stuck" when neither its log nor its
# output file has grown past the stale window even though the process is running
# (the labelling watchdog died at 12:11 once and nothing restarted it — this
# dashboard exists to catch that).
#
# Labelling runs two corpora in sequence against one daily token budget: the
# general mined sample, then the targeted guard corpus. The phase is derived the
# same way label_watch.sh derives it, from the raw file's attempt count, so the
# two can never disagree about which corpus is live.

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
  local filled=$(( done * w / total )); [ "$filled" -gt "$w" ] && filled=$w
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
PASS1_ATTEMPTS=0
[ -f data/labelled_multilang_raw.jsonl ] && PASS1_ATTEMPTS=$(wc -l < data/labelled_multilang_raw.jsonl)
if [ "$PASS1_ATTEMPTS" -lt 959 ]; then
  LAB_PHASE="pass 1 — general corpus"
  LAB_FILE=data/labelled_multilang.jsonl
  LAB_LOG=label_multilang.log
  LAB_TOTAL=959
else
  LAB_PHASE="pass 2 — guard corpus"
  LAB_FILE=data/labelled_guards.jsonl
  LAB_LOG=label_guards.log
  # 60 per language over eight languages. Restarts before the cap counted
  # what was already on disk overshot several languages past 60, and those
  # labels are kept, so the target is the cap or the overshoot, per language.
  LAB_TOTAL=$(awk -F'"language": *"' 'NF>1{split($2,a,"\""); c[a[1]]++}
    END{t=0; n=0; for(k in c){n++; t += c[k]>60 ? c[k] : 60} print t + (8-n)*60}' \
    data/labelled_guards.jsonl 2>/dev/null)
  [ -z "$LAB_TOTAL" ] && LAB_TOTAL=480
fi
LAB_DONE=0; [ -f "$LAB_FILE" ] && LAB_DONE=$(wc -l < "$LAB_FILE")
# Do NOT take the total from the log's "N commits to label": that N is what was
# LEFT at the last relaunch (resume skips what is done), while LAB_DONE counts
# the whole output file. Mixing them read 924/829 = 111%.
job phase yellow "$LAB_PHASE"
if pgrep -f "corpus[.]label" >/dev/null; then
  LF=$(fresh "$LAB_FILE")     # since the last kept record
  LGF=$(fresh "$LAB_LOG")     # since the last line of any kind
  # Since the pacing fix a commit lands every ~20s, so minutes of silence is no
  # longer normal - but it is not automatically a wedge either. Groq caps tokens
  # per DAY, and an exhausted key legitimately parks for 10-20 minutes while the
  # log keeps moving. A growing log with a still output file is the run waiting
  # for budget; neither moving is the wedge the watchdog kills at 900s.
  if [ ! -f "$LAB_FILE" ]; then
    # The phase just handed over: the process is up but has not written its
    # first record yet, which is not the same as wedged.
    job labelling green "starting on $(basename "$LAB_FILE")"
  elif [ "$LF" -gt 900 ] && [ "$LGF" -gt 900 ]; then
    job labelling red "running but STUCK ($((LF/60))m silent — watchdog kills at 15m)"
  elif [ "$LF" -gt 300 ]; then
    job labelling yellow "waiting on token budget ($((LF/60))m since last record)   $LAB_DONE/$LAB_TOTAL"
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
elif [ "$LAB_DONE" -ge "${LAB_TOTAL:-0}" ] 2>/dev/null; then
  # A finished corpus needs no watchdog. Leaving this red meant the panel cried
  # wolf for days after labelling completed, which is how a real red gets
  # ignored.
  job watchdog yellow "not needed (corpus complete)"
else
  job watchdog red "DOWN — labelling will stop silently"
fi
[ -f "$WLOG" ] && tail -1 "$WLOG" | sed "s/^/    $DIM/;s/$/$OFF/"
# Strip the rate and ETA: that counter restarts with every process restart, so
# it reports the pace of the current fragment as though it were the run's. The
# kept/dropped/failed tallies are cumulative for the fragment and do mean
# something. The honest progress number is the bar above, which counts the file.
[ -f "$LAB_LOG" ] && tr '\r' '\n' < "$LAB_LOG" | grep -E "^  [0-9]+/[0-9]+  kept" | tail -1 \
  | sed "s/ *([^)]*)$//" | sed "s/^/    $DIM/;s/$/$OFF/"
# The daily token budget is what actually paces this project, and the only free
# read on it is what the labeller already logged. A parked key here explains a
# yellow "waiting" row above.
[ -f "$LAB_LOG" ] && tr '\r' '\n' < "$LAB_LOG" \
  | grep -oE "key \.\.\.[A-Za-z0-9]+ spent for [0-9]+m|all [0-9]+ keys rate-limited, waiting [0-9]+s" \
  | tail -1 | sed "s/^/    ${DIM}budget: /;s/$/$OFF/"

sec "local jobs"
if pgrep -f "mine[.]py" >/dev/null; then
  MINE_LAST=$(grep -E "records$|add a guard$|cloning" guard_mine.log 2>/dev/null | tail -1 | sed 's/^ *//')
  job mining green "running   ${MINE_LAST:0:58}"
else
  job mining yellow "idle"
fi
sec "training (on $H)"
for probe in sft dpo; do
  state=$(R "pgrep -f \"fine_tuning[.]train_$probe\" >/dev/null && echo green || echo yellow")
  if [ "$state" = green ]; then
    # Not anchored at the line start: TRL prefixes its bars with the phase
    # ("Computing reference log probs for train dataset:  5%|..."), and that
    # prefix is the useful half - it says whether DPO is still precomputing
    # reference log-probs or actually training.
    detail=$(R "tr \"\r\" \"\n\" < \$(ls -t ~/oracle/$probe*.log 2>/dev/null | head -1) 2>/dev/null | grep -E \"[0-9]+%\\|\" | tail -1")
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
# What the training actually produced. A merged model older than the DPO
# adapter means the last run died before the merge, which is exactly what an
# OOM at step 0 looks like: the process is gone and every artifact is stale.
R 'cd ~/oracle/artifacts 2>/dev/null && stat -c "%n %y" \
     sft-adapter/adapter_model.safetensors dpo-adapter/adapter_model.safetensors \
     sft-ml8-grounded/adapter_model.safetensors \
     sft-merged/model.safetensors oracle-merged/model.safetensors 2>/dev/null' \
  | awk '{printf "    %-44s %s %s\n", $1, $2, substr($3,1,5)}'

sec "gpu (on $H)"
R 'nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader 2>/dev/null | sed "s/^/  /"' \
  || echo "  box unreachable (powered off?)"

sec "evals (on $H)"
EV=$(R 'ps -eo etimes,args | grep "[e]valuate.py" | head -1' | sed 's/^[[:space:]]*//')
if [ -n "$EV" ]; then
  ELAPSED=${EV%% *}
  MODEL=$(printf '%s' "$EV" | sed -n 's/.*--model \([^ ]*\).*/\1/p')
  PROG=$(R 'tr "\r" "\n" < "$(ls -t ~/oracle/detect*.log ~/oracle/cve*.log ~/oracle/eval*.log 2>/dev/null | head -1)" 2>/dev/null | grep -E "^  [0-9]+/[0-9]+ " | tail -1')
  DONE=$(printf '%s' "$PROG" | sed -n 's|^ *\([0-9]*\)/.*|\1|p')
  TOTAL=$(printf '%s' "$PROG" | sed -n 's|^ *[0-9]*/\([0-9]*\).*|\1|p')
  job eval green "$MODEL   $(bar "${DONE:-0}" "${TOTAL:-1}")   ${DONE:-0}/${TOTAL:-1}"
else
  job eval yellow "idle"
fi

sec "variance (on $H)"
# Variance runs on the box, not here: 800 calls at ~75s is 16h, and a run
# tunnelled from a laptop dies with the laptop. Everything below therefore
# comes from one remote call — state, totals, row age and the live agreement
# rate — because a per-field ssh would cost four round trips every refresh.
#
# The results path is read out of the run's own header rather than hardcoded:
# --out changed from variance_results.jsonl to variance200.jsonl, and a
# hardcoded path would have shown a finished 40-commit run as live progress.
# The state probe is its OWN ssh call, and it must stay that way. The block
# below ends with `.venv/bin/python variance.py --score`, so when the pgrep
# lived in the same string it matched the `bash -lc` process running it and
# reported RUN forever - which is what printed a red STUCK over a variance run
# that had been finished for a day. Same self-match trap serve.sh:29 documents.
VAR_STATE=$(R 'pgrep -f "variance\.py" >/dev/null && echo RUN || echo IDLE')
VAR=$(R "cd ~/oracle &&
  sed -n \"s/.* = \\([0-9]*\\) calls\$/\\1/p\" variance.log 2>/dev/null | tail -1;
  grep -cE \"^  \\[[0-9]+/[0-9]+\\]\" variance.log 2>/dev/null;
  F=\$(sed -n \"s/^backend.*->  *//p\" variance.log 2>/dev/null | tail -1);
  if [ -n \"\$F\" ] && [ -f \"\$F\" ]; then echo \$(( \$(date +%s) - \$(stat -c %Y \"\$F\") )); else echo -1; fi;
  [ -s \"\$F\" ] && .venv/bin/python variance.py --score \"\$F\" 2>/dev/null |
    grep -E \"verdict agreement|category agreement|commits unanimous\"")
VAR_TOTAL=$(sed -n 1p <<<"$VAR")
VAR_DONE=$(sed -n 2p <<<"$VAR")
VAR_AGE=$(sed -n 3p <<<"$VAR")
if [ -z "$VAR_STATE" ]; then
  job variance yellow "box unreachable"
elif [ "$VAR_STATE" = RUN ]; then
  # One call is ~75s on the 6GB card; several minutes of silence means the
  # server died under it, and every later row would be an error row.
  # A run that has written every row it owes is finishing, not wedged. Judging
  # on mtime alone printed a red STUCK over a *completed* 800-call run, and a
  # panel that cries wolf is a panel nobody reads.
  if [ "${VAR_DONE:-0}" -ge "${VAR_TOTAL:-1}" ] 2>/dev/null; then
    job variance green "all ${VAR_TOTAL:-?} calls done, finishing up"
  elif [ "${VAR_AGE:-0}" -gt 400 ]; then
    job variance red "running but STUCK ($((VAR_AGE/60))m since last row — server died?)"
  else
    job variance green "running   $(bar "${VAR_DONE:-0}" "${VAR_TOTAL:-1}")   ${VAR_DONE:-0}/${VAR_TOTAL:-1}"
  fi
elif [ -n "$VAR_DONE" ] && [ "$VAR_DONE" -gt 0 ]; then
  job variance yellow "idle   ${VAR_DONE}/${VAR_TOTAL:-?} calls done"
else
  job variance yellow "idle"
fi
# The agreement rate is the whole point of the run, so show it while it climbs
# rather than only at the end.
sed -n '4,$p' <<<"$VAR" | sed "s/^ */    $DIM/;s/$/$OFF/"

sec "basic-algorithm benchmark (the 8/10 goal)"
# This is the instrument the current goal is measured by, so it gets a panel.
# Scores are re-derived from the stored answers through basic_bench --score,
# never read off the rows' own verdict fields: scorer fixes land after runs do
# (the hyphen fix moved the base model a whole case) and a stale field would
# quietly report the old number forever.
BENCH_CASES=$(ls -d bench/basic/*/ 2>/dev/null | wc -l)
BENCH_LANGS=$(sed -n 's/.*"language": *"\([^"]*\)".*/\1/p' bench/basic/*/meta.json 2>/dev/null \
  | sort -u | wc -l)
if pgrep -f "basic_bench[.]py" >/dev/null; then
  BENCH_MODEL=$(pgrep -af "basic_bench[.]py" | sed -n 's/.*--model-name \([^ ]*\).*/\1/p' | head -1)
  # Progress has to come from the server's log: --out is written once, at the
  # end, so the output file says nothing while the run is in flight. The count
  # is generations answered since that server started, which equals cases done
  # only when one run owns the server - true here, and labelled as "answered"
  # rather than "done" so it cannot overstate.
  BENCH_ANS=$(R 'grep -c " -> " "$(ls -t ~/oracle/serve*.log 2>/dev/null | head -1)" 2>/dev/null')
  job bench green "scoring ${BENCH_MODEL:-?}   $(bar "${BENCH_ANS:-0}" "${BENCH_CASES:-1}")   ~${BENCH_ANS:-0}/$BENCH_CASES answered"
else
  job bench yellow "idle   $BENCH_CASES cases, $BENCH_LANGS languages"
fi
for f in data/basic_bench_*.jsonl; do
  [ -f "$f" ] || continue
  .venv/bin/python bench/basic_bench.py --score "$f" 2>/dev/null \
    | awk -v n="$(basename "$f" .jsonl | sed 's/^basic_bench_//')" '
        /fully correct/     {fully=$3; pct=$4}
        /hallucinated/      {h=$2}
        END {if (fully != "") printf "    %-20s fully %-8s %-6s halluc %s\n", n, fully, pct, h}'
done

sec "local corpus"
for f in data/labelled.jsonl data/labelled_multilang.jsonl data/multilang_commits.jsonl \
         data/guard_commits.jsonl data/labelled_guards.jsonl \
         data/contrastive_pairs.jsonl data/apachejit_commits.jsonl; do
  [ -f "$f" ] && printf '  %-34s %6d\n' "$(basename "$f")" "$(wc -l < "$f")"
done

sec "serving"
# Name the model, not just the port. A tunnel that answers says nothing about
# which weights are behind it - swapping oracle-merged for sft-merged to run an
# A/B leaves the port identical, and a run started against the wrong one looks
# exactly like a run started against the right one.
SERVED=$(curl -s -m 5 http://localhost:8111/api/tags 2>/dev/null \
  | sed -n 's/.*"name": *"\([^"]*\)".*/\1/p')
if [ -n "$SERVED" ]; then
  job serve green "up on localhost:8111 — serving $SERVED"
else
  job serve yellow "down (box off or ./serve.sh stop)"
fi

sec "errors (on $H)"
# `^[A-Za-z]*Error` missed the one that mattered: torch.OutOfMemoryError is
# dotted, so a DPO run that died on VRAM showed a clean error panel for hours.
# Hand-naming the logs missed the one that mattered: the 25 Aug retrain wrote
# to sft_ml8.log, which was on nobody's list, so a failure in a 9.5h run would
# have shown a clean error panel. Glob every log the box keeps instead.
R 'grep -hE "^[A-Za-z_.]+Error|Traceback|OutOfMemory" \
     ~/oracle/*.log 2>/dev/null \
   | tail -2 | cut -c1-100 | sed "s/^/  /"'

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