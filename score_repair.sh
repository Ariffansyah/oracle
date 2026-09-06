#!/bin/bash
# Score the repair-supervised checkpoint on the SAME 40 real commits as v6/v7.
#
#   ./score_repair.sh            # serve, run the 40, write the grading sheet
#   ./score_repair.sh --sheet    # re-render the sheet from rows already on disk
#   ./score_repair.sh --bench    # also run the three synthetic sets (see caveat)
#
# THE CONTRACT IS THE WHOLE POINT. `ORACLE_OUTPUT_CONTRACT=repair` does three
# things, and dropping it silently ruins the measurement:
#
#   1. `_PROMPTS.get(OUTPUT_CONTRACT, _SYSTEM_PROMPT_V1)` falls back to the V1
#      prompt for any unknown name. Serving this checkpoint without it sends the
#      one prompt shape it never trained on — the failure that cost this project
#      two days through the TUI, arriving by a different door.
#   2. `build_user_message` switches to the repair user turn: no schema block,
#      no context block, byte-identical to training.
#   3. `_render` leaves the diff as plain unified, which is what the corpus used.
#
# It also disables per-file chunking in `analyze()`. The repair corpus is
# whole-commit, and chunking is what produced the duplicate findings in the v7
# grade — `d11f820ac3` returned five byte-identical explanations, one per file.
#
# CAVEAT on --bench: the three synthetic sets score v3 fields (effect.direction,
# effect.check, confidence=likely). The repair contract emits none of them, so
# those columns read 0 and mean nothing. Verdict and false-alarm columns remain
# comparable. The 40 real commits are the measurement that matters here.
set -uo pipefail

H=${H:-oracle-gpu}
PORT=${PORT:-8111}
PY=${PY:-.venv/bin/python}
ADAPTER=${ADAPTER:-artifacts/sft-repair}
TAG=${TAG:-repair}
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE" || exit 1

CTL=/tmp/.oracle-repair-%r@%h:%p
SSHOPTS="-o BatchMode=yes -o ConnectTimeout=10 -o ControlMaster=auto
         -o ControlPath=$CTL -o ControlPersist=300"
# The box's login shell is fish. Every remote command goes through bash -lc, or
# a `for` loop fails in a way that looks exactly like the host being down.
remote() { ssh -n $SSHOPTS "$H" "bash -lc '$1'" 2>/dev/null; }

sheet_only() {
  [ -f "data/real_commits_${TAG}.jsonl" ] || { echo "no data/real_commits_${TAG}.jsonl"; exit 1; }
  "$PY" bench/real_commits.py --sheet "data/real_commits_${TAG}.jsonl" 2>&1 | tail -2
  echo
  "$PY" bench/grade_real.py --tags v7 "$TAG" --show 2>&1 | tail -30
}

case "${1:-run}" in
  --sheet) sheet_only; exit 0 ;;
  --bench) WANT_BENCH=1 ;;
  run)     WANT_BENCH=0 ;;
  *)       echo "usage: $0 [run|--sheet|--bench]"; exit 2 ;;
esac

# Serving needs ~2.5GB and training holds ~5.7GB of the 6GB card. Starting both
# means an OOM mid-run and a half-written rows file.
if remote 'pgrep -f "fine_tuning[.]train_sft" >/dev/null'; then
  echo "!! training is still running on $H — it holds the VRAM this needs."
  echo "   Wait for it, or use --sheet to re-read rows already scored."
  exit 1
fi
remote "test -f ~/oracle/$ADAPTER/adapter_config.json" || {
  echo "!! $ADAPTER has no adapter_config.json on $H — not trained yet"; exit 1; }

echo "=== serving $ADAPTER on $H ==="
remote 'pkill -f "llm_explainer[.]serve" 2>/dev/null; sleep 1'
remote "(cd ~/oracle && nohup .venv/bin/python -m llm_explainer.serve \
        --model $ADAPTER --port $PORT) > ~/oracle/serve_repair.log 2>&1 < /dev/null &"
# Wait for the box to answer before tunnelling: a tunnel to nothing "works"
# until the first request and then misreports as a model failure.
for _ in $(seq 1 90); do
  remote "curl -s -m 2 http://localhost:$PORT/api/tags >/dev/null" && break
  sleep 4
done
ssh -f -N -L "$PORT:localhost:$PORT" $SSHOPTS "$H" 2>/dev/null
sleep 2
if ! curl -s -m 5 "http://localhost:$PORT/api/tags" >/dev/null; then
  echo "  !! server or tunnel not answering — last lines of serve_repair.log:"
  remote 'tail -5 ~/oracle/serve_repair.log'
  exit 1
fi
echo "  server up: $(curl -s -m 5 http://localhost:$PORT/api/tags)"

# serve.py has no --name: it reports the adapter dir's basename, and that is the
# name the bench must ask for.
NAME=$(basename "$ADAPTER")
# INFERENCE_SAMPLES=1 pins greedy single-sample; unset, the client runs 3-sample
# consensus at 3x the cost and the write-up says otherwise.
ENVV="ORACLE_OUTPUT_CONTRACT=repair ORACLE_INCLUDE_SCHEMA=false ORACLE_INFERENCE_SAMPLES=1"

if [ "$WANT_BENCH" = 1 ]; then
  for spec in "bench/basic:basic_bench" \
              "bench/mechanism_heldout:heldout_mech" \
              "bench/clean_heldout:heldout_clean"; do
    root=${spec%%:*} stem=${spec##*:}
    echo "  -- $root  (effect columns will read 0: repair emits no v3 effect)"
    env $ENVV "$PY" bench/basic_bench.py --backend ollama \
        --model-name "$NAME" --host "http://localhost:$PORT" \
        --root "$root" --out "data/${stem}_${TAG}.jsonl" 2>&1 | tail -14
  done
fi

# The 40 real commits — the measurement this checkpoint exists to move.
# Written to a per-tag copy: `--run` rewrites its input in place, and the
# pristine sample must survive so the 40 stay the same 40 across checkpoints.
echo
echo "  -- 40 real commits (same sample as v6 and v7)"
cp data/real_commits.jsonl "data/real_commits_${TAG}.jsonl"
env $ENVV "$PY" bench/real_commits.py --run "data/real_commits_${TAG}.jsonl" \
    --backend ollama --model-name "$NAME" --host "http://localhost:$PORT" 2>&1 | tail -6

remote 'pkill -f "llm_explainer[.]serve" >/dev/null 2>&1; true'
ssh $SSHOPTS -O exit "$H" 2>/dev/null

echo
sheet_only
echo
echo "Now hand-grade data/real_commits_${TAG}.md against the v7 taxonomy and"
echo "record it in data/real_commits_${TAG}_grades.json (mirror the v7 file)."
echo "v7 is the number to beat: 32 findings, 30 wrong (93%), 0 confirmed correct."
