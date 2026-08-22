#!/bin/bash
# Start or stop the labelling run (teacher labels, resume-safe).
#
#   ./run_phase2.sh          start
#   ./run_phase2.sh --stop   stop
#
# This only drives the watchdog; label_watch.sh picks the phase itself from the
# raw line counts and launches corpus.label with the right flags. Pass 1 has
# already attempted its 959, so a start goes straight to the guard corpus
# (--per-language 60 --no-balance, 480 commits). Resume is free: label.py skips
# by commit_id, so kept records stand across any number of stops.
#
# Watch it with ./dashboard.sh (live) or ./dashboard.sh --once.
cd "$(dirname "$0")"

WATCH="label_watch[.]sh"
LABEL="corpus[.]label"

if [ "$1" = "--stop" ]; then
  # Watchdog first: it relaunches the labeller within 15 minutes otherwise.
  pkill -f "$WATCH"
  pkill -f "$LABEL"
  sleep 2
  pgrep -af "$WATCH|$LABEL" || echo "stopped"
  exit 0
fi

if [ -n "$1" ]; then
  echo "usage: $0 [--stop]" >&2
  exit 2
fi

if pgrep -f "$WATCH" >/dev/null; then
  echo "watchdog already running (pid $(pgrep -f "$WATCH" | tr '\n' ' '))"
  exit 0
fi

setsid nohup ./label_watch.sh >> label_watch.log 2>&1 < /dev/null &
echo "watchdog started — ./dashboard.sh to watch, tail -f label_guards.log for detail"
