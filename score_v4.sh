#!/bin/bash
# Score the v4 suggestion-contract checkpoints: serve each adapter on the GPU
# box, tunnel to it, run all three bench sets, then report.
#
#   ./score_v4.sh              # both seeds, then compare + audit
#   ./score_v4.sh seed42       # one seed only
#   ./score_v4.sh --report     # re-run compare + audit on rows already scored
#
# No merge step: `llm_explainer/serve.py` detects `adapter_config.json` and
# loads a LoRA adapter directly (serve.py:62), which is what `train_sft.py`
# writes. Merging first would cost 20 minutes and change nothing.
#
# The contract is set on THIS side, not the box: serve.py only generates from
# the `messages` it is handed, so the system prompt comes from the local
# config. Scoring a v3 checkpoint with the contract unset would send it v1
# prompts and measure the mismatch instead of the model (27 Aug: six cases in
# forty-six lost to exactly that).
set -uo pipefail

H=${H:-oracle-gpu}
PORT=${PORT:-8111}
PY=${PY:-.venv/bin/python}
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE" || exit 1

CTL=/tmp/.oracle-score-%r@%h:%p
SSHOPTS="-o BatchMode=yes -o ConnectTimeout=10 -o ControlMaster=auto
         -o ControlPath=$CTL -o ControlPersist=300"
# The box's login shell is fish. Every remote command goes through bash -lc, or
# a `for` loop fails in a way that looks exactly like the host being down.
remote() { ssh -n $SSHOPTS "$H" "bash -lc '$1'" 2>/dev/null; }

declare -A ADAPTER=( [seed42]=artifacts/sft-v4-suggest
                     [seed7]=artifacts/sft-v4-suggest-seed7
                     [seed42ep1]=artifacts/sft-v4-suggest/checkpoint-46
                     [seed7ep1]=artifacts/sft-v4-suggest-seed7/checkpoint-46 )
declare -A TAG=( [seed42]=v4 [seed7]=v4_seed7
                 [seed42ep1]=v4_ep1 [seed7ep1]=v4_ep1_seed7 )

# The epoch-1 checkpoints are scored because seed 42's loss curve flattened long
# before step 92: 0.070 at the epoch-1 boundary against 0.036 at the end, with
# entropy collapsing 1.51 -> 0.045 on a 366-example corpus (30 Aug). That is the
# shape that produces verbatim copying, which `template_audit.py` measures and
# the plan puts a threshold on. `save_strategy="epoch"` already wrote both, so
# this costs scoring time and no GPU-hours. BOTH seeds are scored: one seed's
# checkpoint-46 would be the point estimate compare_seeds.py exists to refuse.

# serve.py has no --name: it reports `args.model.name`, the adapter dir's
# basename, and that is the name the bench must ask for.
start_server() {  # $1 = adapter path on the box
  remote 'pkill -f "llm_explainer[.]serve" 2>/dev/null; sleep 1'
  remote "(cd ~/oracle && nohup .venv/bin/python -m llm_explainer.serve \
          --model $1 --port $PORT) > ~/oracle/serve_v4.log 2>&1 < /dev/null &"
  # Wait for the box to answer before tunnelling: a tunnel to nothing "works"
  # until the first request and then misreports as a model failure.
  for _ in $(seq 1 90); do
    remote "curl -s -m 2 http://localhost:$PORT/api/tags >/dev/null" && break
    sleep 4
  done
  ssh -f -N -L "$PORT:localhost:$PORT" $SSHOPTS "$H" 2>/dev/null
  sleep 2
  if ! curl -s -m 5 "http://localhost:$PORT/api/tags" >/dev/null; then
    echo "  !! server or tunnel not answering — last lines of serve_v4.log:"
    remote 'tail -5 ~/oracle/serve_v4.log'
    return 1
  fi
  echo "  server up: $(curl -s -m 5 http://localhost:$PORT/api/tags)"
}

stop_server() {
  remote 'pkill -f "llm_explainer[.]serve" >/dev/null 2>&1; true'
  ssh $SSHOPTS -O exit "$H" 2>/dev/null
}

score_one() {  # $1 = seed key
  local key=$1 adapter=${ADAPTER[$1]} tag=${TAG[$1]} name
  name=$(basename "$adapter")
  echo
  echo "=== $key -> data/*_$tag.jsonl  (adapter $adapter) ==="
  remote "test -f ~/oracle/$adapter/adapter_config.json" || {
    echo "  !! $adapter has no adapter_config.json on $H — not trained yet"; return 1; }
  start_server "$adapter" || return 1

  # ORACLE_INFERENCE_SAMPLES=1 pins greedy single-sample. Unset, the client runs
  # 3-sample consensus at 3x the cost and the write-up says otherwise.
  local env="ORACLE_OUTPUT_CONTRACT=v3 ORACLE_INCLUDE_SCHEMA=false ORACLE_INFERENCE_SAMPLES=1"
  local rc=0
  for spec in "bench/basic:basic_bench" \
              "bench/mechanism_heldout:heldout_mech" \
              "bench/clean_heldout:heldout_clean"; do
    local root=${spec%%:*} stem=${spec##*:}
    echo "  -- $root"
    env $env "$PY" bench/basic_bench.py --backend ollama \
        --model-name "$name" --host "http://localhost:$PORT" \
        --word-diff-module --root "$root" \
        --out "data/${stem}_${tag}.jsonl" 2>&1 | tail -18
    [ "${PIPESTATUS[0]}" -ne 0 ] && rc=1
  done
  stop_server
  return $rc
}

report() {
  echo
  echo "=== two-seed comparison, with the noise band ==="
  "$PY" bench/compare_seeds.py --base v2_pilot2 v2_seed7 --new v4 v4_seed7 2>&1 | tail -40
  echo
  echo "=== epoch-1 pair, same frame as the headline ==="
  "$PY" bench/compare_seeds.py --base v2_pilot2 v2_seed7 --new v4_ep1 v4_ep1_seed7 2>&1 | tail -40
  echo
  # The direct epoch question: does stopping at 46 move anything past seed noise?
  echo "=== epoch 1 against epoch 2, both as seed pairs ==="
  "$PY" bench/compare_seeds.py --base v4 v4_seed7 --new v4_ep1 v4_ep1_seed7 2>&1 | tail -40
  echo
  echo "=== verbatim copying against an out-of-family floor ==="
  "$PY" bench/template_audit.py --corpus data/sft_v4_suggest.jsonl \
      --tags base44 gptoss120b v2_pilot2 v2_seed7 v3 v3_seed7 v4 v4_seed7 \
            v4_ep1 v4_ep1_seed7 2>&1 | tail -25
}

case "${1:-all}" in
  --report) report; exit 0 ;;
  seed42|seed7|seed42ep1|seed7ep1) targets=("$1") ;;
  final) targets=(seed42 seed7) ;;
  ep1) targets=(seed42ep1 seed7ep1) ;;
  all) targets=(seed42 seed7 seed42ep1 seed7ep1) ;;
  *) echo "usage: $0 [seed42|seed7|seed42ep1|seed7ep1|final|ep1|all|--report]"; exit 2 ;;
esac

# Serving needs ~2.5GB and training is already holding ~4.5GB of the 6GB card.
# Starting both means an OOM mid-run and a half-written rows file.
if remote 'pgrep -f "fine_tuning[.]train_sft" >/dev/null'; then
  echo "!! training is still running on $H — it holds the VRAM this needs."
  echo "   Wait for it, or pass --report to re-read rows already scored."
  exit 1
fi

fail=0
for t in "${targets[@]}"; do score_one "$t" || fail=1; done
[ "$fail" -ne 0 ] && echo && echo "!! at least one set did not complete — read above before trusting any number"
report
