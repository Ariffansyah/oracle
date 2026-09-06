#!/bin/bash
# Serve oracle-merged and open the TUI against a real repo, in the ONE
# configuration that checkpoint was actually measured in.
#
#   ./try_tui.sh                          # default repo, oracle-merged
#   ./try_tui.sh ~/Documents/flask        # any repo, as an argument
#   ./try_tui.sh --pick                   # choose from ~/Documents interactively
#   NO_GATE=1 ./try_tui.sh                # skip stage 1, LLM on every commit
#   LIMIT=100 ./try_tui.sh                # more commits in the list
#   MODEL=artifacts/sft-repair-w05 ./try_tui.sh
#   ./try_tui.sh stop                     # kill the server, close the tunnel
#
# NO_GATE: stage 1 is a GraphCodeBERT classifier that decides whether a commit
# is worth an LLM call at all. It is the right design for a real reviewer and
# the wrong one for judging the EXPLAINER, because a commit below the threshold
# produces no explanation to judge. NO_GATE=1 passes --no-gate, which skips
# stage 1 entirely — no encoder load, no scoring, every commit goes to the model.
# (GATE_THRESHOLD=0 also lets everything through, but still pays to load and run
# the encoder; use that one only if you want to SEE the scores.)
#
# WHY THE THREE ENV VARS ARE NOT OPTIONAL
# ---------------------------------------
# ui/tui_app.py:35 does `setdefault("ORACLE_OUTPUT_CONTRACT", "v3")`, because
# the interactive clients are v3 clients. `oracle-merged` is NOT one.
#
# WHICH CONTRACT, ESTABLISHED FROM THE STORED ROWS (2 Sep): every answer in
# data/basic_bench_oracle46.jsonl — the run that scored 41/46 — has exactly two
# keys, `summary` and `findings`. That is v1. It has no `effect`, which v2 and
# v3 both demand first. Re-running the same checkpoint under v2 scores 31/46
# with 9 false alarms instead of 41/46 with 2: a ten-point drop from the prompt
# alone. Do not "upgrade" this to v2 or v3 because the fields look richer —
# the richer fields are what the model was never trained to emit.
#
# If you serve a different checkpoint, CHANGE THESE to match how it was trained:
# a v7/repair checkpoint wants its own contract, not v2.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE" || exit 1

MODEL=${MODEL:-artifacts/oracle-merged}
export MODEL

if [ "${1:-}" = "stop" ]; then exec ./serve.sh stop; fi

REPO=${REPO:-$HOME/Documents/jinja}
if [ "${1:-}" = "--pick" ]; then
  # Any directory under ~/Documents with a .git — the repos actually to hand.
  mapfile -t REPOS < <(find "$HOME/Documents" -maxdepth 2 -name .git -type d \
                       -printf "%h\n" 2>/dev/null | sort)
  [ ${#REPOS[@]} -gt 0 ] || { echo "no git repos under ~/Documents"; exit 1; }
  echo "pick a repo:"
  for i in "${!REPOS[@]}"; do printf "  %2d) %s\n" "$((i+1))" "${REPOS[$i]}"; done
  printf "> "; read -r n
  case "$n" in ''|*[!0-9]*) echo "not a number"; exit 1 ;; esac
  [ "$n" -ge 1 ] && [ "$n" -le ${#REPOS[@]} ] || { echo "out of range"; exit 1; }
  REPO="${REPOS[$((n-1))]}"
elif [ -n "${1:-}" ]; then
  REPO="$1"
fi
REPO="${REPO/#\~/$HOME}"

[ -d "$REPO/.git" ] || { echo "!! $REPO is not a git repo"; exit 1; }

# The card holds ~5.2GB while training; serving needs ~2.5GB of 6GB. Starting
# both is an OOM in whichever one allocates second.
if ssh -n -o BatchMode=yes -o ConnectTimeout=8 "${H:-oracle-gpu}" \
     "bash -lc 'pgrep -f \"fine_tuning[.]train_sft\" >/dev/null'" 2>/dev/null; then
  echo "!! training is running on ${H:-oracle-gpu} — it holds the VRAM this needs."
  echo "   Stop it first, or wait for it to finish."
  exit 1
fi

GATE_ARG=""
GATE_MSG="on (NO_GATE=1 to skip)"
if [ -n "${NO_GATE:-}" ]; then
  GATE_ARG=" --no-gate"
  GATE_MSG="SKIPPED — every commit goes to the model"
fi

echo "repo   : $REPO"
echo "model  : $MODEL"
echo "config : contract=v1 schema=on rendering=unified  (oracle-merged's measured setup)"
echo "stage 1: $GATE_MSG"
echo

export ORACLE_OUTPUT_CONTRACT=v1
export ORACLE_INCLUDE_SCHEMA=true
export DIFF_RENDERING=unified
export TUI_ARGS="--repo $REPO --limit ${LIMIT:-50}$GATE_ARG"
exec ./serve.sh tui
