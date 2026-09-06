#!/bin/bash
# Score the v7 checkpoints: serve each adapter on the GPU box, tunnel to it,
# run all three bench sets, then report.
#
#   ./score_v6.sh              # both seeds, then compare + audit
#   ./score_v6.sh seed42       # one seed only
#   ./score_v6.sh --report     # re-run compare + audit on rows already scored
#
# v7 is the check-field rewrite. v4 trained on a corpus whose `check` was a
# per-category sentence with a filename slot - 100 distinct strings in 366
# targets, "the edit touches" in 357 of them - and emitted it on 100% of cases.
# v7 trains on per-case probe/watch text authored beside each case in
# `meta.json["check"]`; the corpus is 341 distinct checks in 366 targets.
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

# ONE seed. The prediction registered in run_v7.sh before training was that
# accuracy would NOT move (v4->v6 shifted no metric past noise, and v7 is a
# smaller change than that was), and the leakage hypothesis it was built to test
# died before the run finished: baseline cross-language leakage measured 1
# leaked term in 138 scored answers, so there is nothing for it to fall from.
# Seed 2 is only worth a night if seed 1 shows something unexpected.
declare -A ADAPTER=( [seed42]=artifacts/sft-v7-suggest )
declare -A TAG=( [seed42]=v7 )

# No epoch-1 pair to score: v7 trains ONE epoch. The 31 Aug comparison
# `compare_seeds.py --base v4 v4_seed7 --new v4_ep1 v4_ep1_seed7` returned "no"
# on every metric across all three sets - epoch 2 moved nothing past seed noise
# while doubling the run - so the second epoch was dropped rather than measured
# again.

# serve.py has no --name: it reports `args.model.name`, the adapter dir's
# basename, and that is the name the bench must ask for.
start_server() {  # $1 = adapter path on the box
  remote 'pkill -f "llm_explainer[.]serve" 2>/dev/null; sleep 1'
  remote "(cd ~/oracle && nohup .venv/bin/python -m llm_explainer.serve \
          --model $1 --port $PORT) > ~/oracle/serve_v6.log 2>&1 < /dev/null &"
  # Wait for the box to answer before tunnelling: a tunnel to nothing "works"
  # until the first request and then misreports as a model failure.
  for _ in $(seq 1 90); do
    remote "curl -s -m 2 http://localhost:$PORT/api/tags >/dev/null" && break
    sleep 4
  done
  ssh -f -N -L "$PORT:localhost:$PORT" $SSHOPTS "$H" 2>/dev/null
  sleep 2
  if ! curl -s -m 5 "http://localhost:$PORT/api/tags" >/dev/null; then
    echo "  !! server or tunnel not answering — last lines of serve_v6.log:"
    remote 'tail -5 ~/oracle/serve_v6.log'
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

  # The 40 real commits, in the SAME serving session — starting and stopping the
  # server is the expensive part, running 40 more diffs through it is not.
  #
  # These have no execution-proved label, so nothing here is scored: the output
  # is answers on real code, for hand-grading with `--sheet`. It exists because
  # the two standing objections to the explanation result are that n is thin and
  # that every case is synthetic, and `data/real_commits.jsonl` has been sitting
  # sampled-but-never-run since 26 Aug. A weak honest number on real commits is
  # worth more to the write-up than a strong one on 46 hand-written programs.
  #
  # Written to a per-tag copy: `--run` rewrites its input in place, and the
  # pristine sample must survive so the 40 commits stay the same 40 across
  # checkpoints.
  if [ -f data/real_commits.jsonl ]; then
    echo "  -- 40 real commits (unlabelled; for hand-grading)"
    cp data/real_commits.jsonl "data/real_commits_${tag}.jsonl"
    env $env "$PY" bench/real_commits.py --run "data/real_commits_${tag}.jsonl" \
        --backend ollama --model-name "$name" --host "http://localhost:$PORT" \
        2>&1 | tail -6
  fi

  stop_server
  return $rc
}

report() {
  echo
  echo "=== v7 against the v2 pair, with the noise band ==="
  "$PY" bench/compare_seeds.py --base v6 v6_seed7 --new v7 v7 2>&1 | tail -40
  echo
  # The question this run was launched to answer: did rewriting `check` cost
  # anything the v4 corpus was buying. v4 is the same contract, same recipe,
  # one corpus change - so it is the right base for the check-field question,
  # while v2 above stays the base for the contract question.
  echo "=== v7 against v4, both as seed pairs — the check-field question ==="
  "$PY" bench/compare_seeds.py --base v4 v4_seed7 --new v7 v7 2>&1 | tail -40
  echo
  echo "=== verbatim copying against an out-of-family floor ==="
  # Each family read against the corpus it actually saw: v4 checkpoints against
  # sft_v4_suggest, v7 against sft_v6_suggest. A checkpoint scored against a
  # corpus it never saw is a floor, not a copying rate, and the two must not be
  # printed in one column as though they were the same measurement.
  "$PY" bench/template_audit.py --corpus data/sft_v6_suggest.jsonl \
      --tags v6 v6_seed7 v7 2>&1 | tail -18
  echo
  echo "--- the same, counting effect.check as prose ---"
  # v4's headline copying number could not see `check` at all, which is how a
  # field that was 97% template survived into a training run.
  "$PY" bench/template_audit.py --corpus data/sft_v6_suggest.jsonl --with-check \
      --tags v6 v6_seed7 v7 2>&1 | tail -18
  echo
  echo "--- v4 against ITS OWN corpus, for the comparison ---"
  "$PY" bench/template_audit.py --corpus data/sft_v4_suggest.jsonl \
      --tags v4 v4_seed7 2>&1 | tail -10
  echo
  echo '=== is the check field composed or recited ==='
  "$PY" bench/check_field_audit.py --tags v4 v4_seed7 v7 v7_seed7 \
      --pairs v4:v4_seed7 v7:v7_seed7 2>&1 | tail -30
  echo
  echo "--- grading sheets for the 40 real commits (hand-grade these) ---"
  # --sheet writes beside its input as <stem>.md; it does not print to stdout.
  for t in v7; do
    [ -f "data/real_commits_$t.jsonl" ] || continue
    "$PY" bench/real_commits.py --sheet "data/real_commits_$t.jsonl" 2>&1 | tail -2
  done
}

case "${1:-all}" in
  --report) report; exit 0 ;;
  seed42|seed7) targets=("$1") ;;
  all|final) targets=(seed42) ;;
  *) echo "usage: $0 [seed42|seed7|all|--report]"; exit 2 ;;
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
