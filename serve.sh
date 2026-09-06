#!/bin/bash
# Serve the tuned model on the GPU box and tunnel to it, so the TUI can run
# anywhere. The box's login shell is fish, so every remote command goes through
# bash -lc.
#
#   ./serve.sh start      launch the explainer server on $H, open the tunnel
#   ./serve.sh stop       kill the server (pkill-proofed), close the tunnel
#   ./serve.sh status     is the server up, is the tunnel up
#   ./serve.sh tui        start server + tunnel, then run the TUI
#
# The TUI talks to the tunneled port, not the box directly:
#   ORACLE_BACKEND=ollama ORACLE_OLLAMA_HOST=http://localhost:8111
H=${H:-oracle-gpu}
PORT=${PORT:-8111}
# serve.py's own default is config.MERGED_MODEL_DIR (artifacts/oracle-merged),
# a merged checkpoint from a DIFFERENT output contract that scores like the
# untrained base on BugsInPy. Inheriting it here meant `./serve.sh start` with no
# MODEL served the wrong model, which is how the deployed path came to measure
# 183/458 -- exactly the base model's score. The default is now the alias:
#   artifacts/oracle-reviewer-3b -> sft-exec-v3
# Promote a new checkpoint by repointing that symlink on the box; nothing here
# changes. An explicit override still wins:
#   MODEL=artifacts/sft-repair-w05 ./serve.sh start
# serve.py has no --name: it reports the BASENAME as the model name, which is
# what the TUI and the benches must ask for. It does not resolve the path, so a
# symlink reports the LINK name -- `oracle-reviewer-3b` stays the served name
# however the symlink is repointed, and the `WANT` check below keeps working.
MODEL=${MODEL:-artifacts/oracle-reviewer-3b}
TUI_ARGS=${TUI_ARGS:---repo .}
HERE=$(cd "$(dirname "$0")" && pwd)

CTL=/tmp/.oracle-serve-%r@%h:%p
SSHOPTS="-o BatchMode=yes -o ConnectTimeout=8 -o ControlMaster=auto
         -o ControlPath=$CTL -o ControlPersist=300"

remote() { ssh $SSHOPTS "$H" "bash -lc '$1'" 2>/dev/null; }

start() {
  WANT=$(basename "$MODEL")
  # Reuse a server already serving the model we want. A restart reloads 3B of
  # weights in 4-bit, which is a minute-plus on this card, and `start` used to
  # pay it on EVERY launch — including when the right server was already up.
  # serve.py reports the adapter directory's basename, so the name is the check.
  HAVE=$(remote "curl -s -m 3 http://localhost:$PORT/api/tags" \
         | grep -o '"name"[^"]*"[^"]*"' | head -1 | sed 's/.*"\(.*\)"$/\1/')
  if [ "$HAVE" = "$WANT" ]; then
    echo "reusing the running server ($HAVE) — pass RESTART=1 to reload it"
  fi
  if [ "$HAVE" != "$WANT" ] || [ -n "${RESTART:-}" ]; then
    remote "test -d ~/oracle/$MODEL" || {
      echo "!! $MODEL does not exist on $H"; exit 1; }
    # Kill and launch must be separate ssh calls: the launch command itself
    # contains "llm_explainer.serve", which pkill's pattern matches — running
    # both in one shell makes pkill kill the shell that is about to start it.
    remote 'pkill -f "llm_explainer[.]serve" 2>/dev/null; sleep 1'
    echo "serving $MODEL (reported as \"$WANT\") — loading weights, ~1min"
    # </dev/null is load-bearing: nohup redirects stdout and stderr, but the
    # detached server keeps ssh's stdin open, so ssh never sees EOF and blocks
    # forever on a process it has already successfully launched. This wedged a
    # batch run for eleven minutes with the server up and answering.
    remote "cd ~/oracle && nohup .venv/bin/python -m llm_explainer.serve --port $PORT \
         --model $MODEL > ~/oracle/serve.log 2>&1 < /dev/null &"
    # Wait for the server to answer on the box before tunnelling; a tunnel to
    # nothing "works" until the first request and misreports as down.
    for i in $(seq 1 60); do
      remote "curl -s -m 2 http://localhost:$PORT/api/tags >/dev/null" && break
      sleep 2
    done
  fi
  # Likewise the tunnel: a second -L on a live port just fails noisily.
  if ! curl -s -m 3 "http://localhost:${PORT}/api/tags" >/dev/null 2>&1; then
    ssh -f -N -L "${PORT}:localhost:${PORT}" $SSHOPTS "$H"
    sleep 1
  fi
  curl -s -m 3 "http://localhost:${PORT}/api/tags" >/dev/null \
    && echo "server + tunnel up on localhost:${PORT}" \
    || echo "server started but the tunnel is not answering"
}

stop() {
  # The [.] bracket keeps pkill from matching this wrapper's own command line
  # (the pkill pattern is part of the ssh command string) and exiting 255.
  remote 'pkill -f "llm_explainer[.]serve" && echo server stopped || echo server not running'
  ssh $SSHOPTS -O exit "$H" 2>/dev/null
  echo "tunnel closed"
}

status() {
  remote 'pgrep -f "llm_explainer[.]serve" >/dev/null &&
      echo "  server: up  ($(tr "\r" "\n" < ~/oracle/serve.log 2>/dev/null | tail -1))" ||
      echo "  server: down"'
  curl -s -m 3 "http://localhost:${PORT}/api/tags" >/dev/null 2>&1 &&
    echo "  tunnel: up, answering on localhost:${PORT}" ||
    echo "  tunnel: down"
}

tui() {
  start
  sleep 2
  echo "---"
  ORACLE_BACKEND=ollama ORACLE_OLLAMA_HOST="http://localhost:${PORT}" \
    "$HERE/.venv/bin/python" main.py tui $TUI_ARGS
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  tui) tui ;;
  *) sed -n '2,9p' "$0" ;;
esac