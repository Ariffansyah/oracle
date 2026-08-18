#!/bin/bash
# Keep the labelling run alive, and move it on to the next corpus when one is
# finished. Two wedges killed it originally: the Groq keep-alive socket goes
# CLOSE-WAIT and the process sleeps forever (fine foreground, hangs when
# nohup'd). Resume is free — label.py skips by commit_id — so a stale-detector
# that kills and restarts is enough.
#
# Phase order was chosen with the user on 18 Aug: finish pass 1 over the general
# mined corpus, then the targeted guard corpus, and drop pass 2. The two compete
# for one daily token budget, so they run in sequence, never together.
cd "$(dirname "$0")"

PASS1_IN=data/multilang_commits.jsonl
PASS1_OUT=data/labelled_multilang.jsonl
PASS1_RAW=data/labelled_multilang_raw.jsonl
PASS1_LIMIT=959
GUARD_IN=data/guard_commits.jsonl
GUARD_OUT=data/labelled_guards.jsonl
GUARD_RAW=data/labelled_guards_raw.jsonl

# Pass 1 is done when it has ATTEMPTED its limit, which is the raw file's line
# count. Do not use the output file: verify() drops labels it will not train on,
# so the output can never be relied on to reach the limit and the watchdog would
# sit on a finished phase forever.
active_out() {
  if [ "$(wc -l < "$PASS1_RAW" 2>/dev/null || echo 0)" -lt "$PASS1_LIMIT" ]; then
    echo "$PASS1_OUT"
  else
    echo "$GUARD_OUT"
  fi
}

launch() {
  # groq keys live in ~/.zshrc; this env file is written by the launch command,
  # never committed.
  [ -f /tmp/opencode/keys.env ] && . /tmp/opencode/keys.env
  if [ "$(active_out)" = "$PASS1_OUT" ]; then
    setsid nohup .venv/bin/python -m corpus.label \
      --in "$PASS1_IN" --out "$PASS1_OUT" --raw "$PASS1_RAW" \
      --limit "$PASS1_LIMIT" --provider groq --workers 1 \
      >> label_multilang.log 2>&1 < /dev/null &
  else
    # The guard corpus is buggy by construction, so --no-balance: the balancer
    # would otherwise fill half the sample with a clean class that does not
    # exist and label only half the limit. --per-language 60 samples 480 evenly
    # across the eight languages, because repository yield tracks repository
    # size rather than the goal (the raw mine is 228 php to 65 ruby).
    setsid nohup .venv/bin/python -m corpus.label \
      --in "$GUARD_IN" --out "$GUARD_OUT" --raw "$GUARD_RAW" \
      --limit 2000 --per-language 60 --no-balance \
      --provider groq --workers 1 \
      >> label_guards.log 2>&1 < /dev/null &
  fi
}

while true; do
  if ! pgrep -f "corpus[.]label" >/dev/null; then
    echo "$(date +%H:%M) not running — launching $(active_out)"
    launch
    sleep 15
  fi
  # Read the phase once, so both counts come from the same file. If the phase
  # flips during the window the counts tie, which trips the kill below — that is
  # the intended handover, not a false alarm.
  OUT=$(active_out)
  N1=$(wc -l < "$OUT" 2>/dev/null || echo 0)
  sleep 900
  N2=$(wc -l < "$OUT" 2>/dev/null || echo 0)
  if pgrep -f "corpus[.]label" >/dev/null && [ "$N2" -le "$N1" ]; then
    echo "$(date +%H:%M) stale at $N2 records in $OUT — killing"
    pkill -f "corpus[.]label"
    sleep 3
  fi
done
