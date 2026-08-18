#!/bin/bash
# Keep the labelling run alive. Two wedges killed it tonight: the Groq keep-
# alive socket goes CLOSE-WAIT and the process sleeps forever (works fine
# foreground, hangs when nohup'd). Resume is free (label.py skips by
# commit_id), so a stale-detector that kills and restarts is enough.
cd "$(dirname "$0")"
OUT=data/labelled_multilang.jsonl
while true; do
  if ! pgrep -f "corpus[.]label" >/dev/null; then
    echo "$(date +%H:%M) not running — relaunching"
    # groq keys live in ~/.zshrc; this env file is written by the launch
    # command, never committed.
    [ -f /tmp/opencode/keys.env ] && . /tmp/opencode/keys.env
    setsid nohup .venv/bin/python -m corpus.label \
      --in data/multilang_commits.jsonl --out "$OUT" \
      --raw data/labelled_multilang_raw.jsonl --limit 959 \
      --provider groq --workers 1 \
      > label_multilang.log 2>&1 < /dev/null &
    sleep 15
  fi
  N1=$(wc -l < "$OUT" 2>/dev/null || echo 0)
  sleep 900
  N2=$(wc -l < "$OUT" 2>/dev/null || echo 0)
  if pgrep -f "corpus[.]label" >/dev/null && [ "$N2" -le "$N1" ]; then
    echo "$(date +%H:%M) stale at $N2 records — killing"
    pkill -f "corpus[.]label"
    sleep 3
  fi
done