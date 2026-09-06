#!/bin/bash
# Everything that NEEDS THE SERVED MODEL, finished before training takes the GPU.
# Once train_sft starts, the server must be down for 3-4h, so nothing below can
# run alongside it. Order is chosen so each model is served exactly once.
set -uo pipefail
cd /home/arp/Documents/oracle || exit 1

LOG=/home/arp/Documents/oracle/overnight.log
VAR_PID=845235
PY=.venv/bin/python
ENVCFG="ORACLE_INFERENCE_SAMPLES=1 ORACLE_OUTPUT_CONTRACT=v1 ORACLE_INCLUDE_SCHEMA=true"

say() { printf '[%s] %s\n' "$(date +'%m-%d %H:%M')" "$*" >> "$LOG"; }
box() { ssh -o BatchMode=yes -o ConnectTimeout=8 oracle-gpu "bash -lc '$1'" 2>&1; }
score() { $PY bench/basic_bench.py --score "$1" 2>&1 \
          | grep -E 'fully correct|false alarms' | tr -s ' ' | tr '\n' ' '; }

# run_set <root> <outfile> <exec-facts json | ->
run_set() {
  local root=$1 out=$2 facts=$3 extra=""
  [ "$facts" != "-" ] && extra="--exec-facts $facts"
  env $ENVCFG $PY bench/basic_bench.py --backend ollama \
      --model-name "$MODELNAME" --host http://localhost:8111 \
      --root "$root" $extra --out "$out" >> "$LOG" 2>&1
}

say "=== chain v3 started (corrected corpus) — waiting on variance.sh (pid $VAR_PID) ==="
while kill -0 "$VAR_PID" 2>/dev/null; do sleep 60; done
say "variance.sh done"
for i in 1 2 3 4 5; do
  [ -f "data/var_exec_${i}_f.jsonl" ] && printf '    var %d  %s\n' "$i" "$(score data/var_exec_${i}_f.jsonl)" >> "$LOG"
done

# The corpus was already synced to the box at 00:29 (it was built locally at
# 23:55 and the box had no copy — the smoke run would have died on it).
box 'cd ~/oracle && test -s data/exec_sft_ctx.jsonl' >/dev/null \
  && say "exec corpus present on box: $(box 'cd ~/oracle && wc -l < data/exec_sft_ctx.jsonl') rows" \
  || { say "!! exec corpus MISSING on the box — stopping before the smoke run"; exit 1; }

# ---------- PHASE A: oracle-merged, already served. Two sets it has never been
# scored on, plus the exec-facts probe below.
MODELNAME=oracle-merged
say "--- PHASE A: oracle-merged (server already up) ---"
if [ "$(curl -s -m 5 http://localhost:8111/api/tags | grep -c oracle-merged)" -eq 0 ]; then
  say "!! oracle-merged is not being served — skipping phase A"
else
  say "A1 clean_heldout (34, no exec facts) ~17min"
  run_set bench/clean_heldout data/heldout_clean_oracle.jsonl -
  say "   clean_heldout oracle-merged : $(score data/heldout_clean_oracle.jsonl)"

  say "A2 mechanism_heldout (21, no exec facts) ~11min"
  run_set bench/mechanism_heldout data/heldout_mech_oracle.jsonl -
  say "   mech_heldout oracle-merged  : $(score data/heldout_mech_oracle.jsonl)"

  # Probe: 21 of the 34 clean_heldout cases are `*-fix` pairs whose behaviour
  # legitimately DIFFERS. On bench/basic buggy and differs coincide, so the
  # exec-grounded prompt has never been asked to tell "behaviour changed" apart
  # from "defect introduced". This is the case that separates them.
  say "A3 clean_heldout WITH exec facts (34) ~17min  [conflation probe]"
  run_set bench/clean_heldout data/heldout_clean_oracle_exec.jsonl data/exec_diff_clean_heldout.json
  $PY bench/exec_filter.py data/heldout_clean_oracle_exec.jsonl \
      data/heldout_clean_oracle_exec_filtered.jsonl >> "$LOG" 2>&1
  say "   clean+facts   : $(score data/heldout_clean_oracle_exec.jsonl)"
  say "   clean+facts+f : $(score data/heldout_clean_oracle_exec_filtered.jsonl)"
  say "   ^ compare against A1. Higher false alarms here means the exec-grounded"
  say "     prompt reads 'behaviour differs' as 'defect', and the 40/46 FA 0"
  say "     headline is resting on buggy and differs coinciding in bench/basic."
fi

# ---------- PHASE B: base-3b, the ablation
say "--- PHASE B: base ablation, reloading server with artifacts/base-3b ---"
MODEL=artifacts/base-3b ./serve.sh start >> "$LOG" 2>&1
NAME=$(curl -s -m 5 http://localhost:8111/api/tags | grep -o '"name"[^"]*"[^"]*"' | head -1 | sed 's/.*"\(.*\)"$/\1/')
if [ "$NAME" != "base-3b" ]; then
  say "!! server reports '$NAME', not base-3b — SKIPPING phase B, going to training"
else
  MODELNAME=base-3b
  say "B1 basic + exec facts (46) ~25min   [THE ablation vs the SFT's 40/46 FA 0]"
  run_set bench/basic data/basic_bench_base46_exec.jsonl data/exec_diff_basic.json
  $PY bench/exec_filter.py data/basic_bench_base46_exec.jsonl \
      data/basic_bench_base46_exec_filtered.jsonl >> "$LOG" 2>&1
  say "   base unfiltered : $(score data/basic_bench_base46_exec.jsonl)"
  say "   base + filter   : $(score data/basic_bench_base46_exec_filtered.jsonl)   <- vs SFT 40/46 FA 0"

  say "B2 clean_heldout (34) ~17min"
  run_set bench/clean_heldout data/heldout_clean_base.jsonl -
  say "   clean_heldout base-3b : $(score data/heldout_clean_base.jsonl)"

  say "B3 mechanism_heldout (21) ~11min"
  run_set bench/mechanism_heldout data/heldout_mech_base.jsonl -
  say "   mech_heldout base-3b  : $(score data/heldout_mech_base.jsonl)"
fi
say "--- server work COMPLETE. Everything below needs the GPU free. ---"

# ---------- PHASE C: free the VRAM
./serve.sh stop >> "$LOG" 2>&1
sleep 10
say "VRAM after stop: $(box 'nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader')"

# ---------- PHASE D: the smoke run
say "--- PHASE D: smoke run -> artifacts/sft-exec ---"
box 'cd ~/oracle && PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True nohup .venv/bin/python -u \
  -m fine_tuning.train_sft \
  --dataset data/exec_sft_ctx.jsonl \
  --eval-dataset data/exec_sft_ctx_holdout_within.jsonl \
  --output-dir artifacts/sft-exec \
  --verdict-weight 0.5 --eval-steps 20 --eval-max 60 \
  --epochs 1 --max-seq-length 512 --warmup-steps 15 --seed 42 \
  > run_exec.log 2>&1 &' >> "$LOG" 2>&1
sleep 120
box 'pgrep -f "fine_tuning[.]train_sft" >/dev/null && echo "training is up" || echo "!! training is NOT running"' >> "$LOG" 2>&1
say "$(box 'cd ~/oracle && tr "\r" "\n" < run_exec.log | grep -aE "examples from|verdict weight|device:" | head -4')"

# ---------- THE GATE
say "--- watching for the step-20 gate ---"
for i in $(seq 1 300); do
  box 'pgrep -f "fine_tuning[.]train_sft" >/dev/null' >/dev/null || { say "training exited before the gate — read run_exec.log"; break; }
  GATE=$(box 'cd ~/oracle && tr "\r" "\n" < run_exec.log | grep -a "holdout @ step" | head -1')
  if [ -n "$GATE" ]; then
    say "GATE: $GATE"
    if echo "$GATE" | grep -q "recall 0.000"; then
      box 'pkill -f "fine_tuning[.]train_sft"' >> "$LOG" 2>&1
      say "RECALL ZERO -> KILLED per the standing gate. Two corpora in a row now."
    else
      say "recall NON-ZERO — worth its wall time. Left running."
    fi
    break
  fi
  sleep 60
done
say "=== chain finished ==="
