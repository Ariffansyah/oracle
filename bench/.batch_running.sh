#!/usr/bin/env bash
# The whole BugsInPy evaluation, in the one order that works.
#
# The ordering is not cosmetic. The transformer arms load the 3B onto a 6 GB
# card and cannot share it with the served model, so the server must be DOWN for
# them; the guarded arm asks the served model over :8111 and needs it UP. Run
# these by hand in the wrong order and you get an OOM or a connection refused
# forty minutes in.
#
#   ./bench/bugsinpy_batch.sh freeze     rebuild rows, score the gate, snapshot
#   ./bench/bugsinpy_batch.sh gpu        base + exec + score + diff (server down)
#   ./bench/bugsinpy_batch.sh guarded    the deployed path (server up)
#   ./bench/bugsinpy_batch.sh api        gpt-oss-120b, three arms (no GPU)
#   ./bench/bugsinpy_batch.sh report     compare, and check the docs' figures
#
# Each stage is separately runnable and re-runnable; nothing here deletes a
# previous run's output except `freeze`, which is the point of freezing.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
V=${V:-v2}
ROWS=data/bugsinpy_rows_$V.jsonl
SCORES=data/bugsinpy_gate_scores_$V.json
HOST=${HOST:-oracle-gpu}

case "${1:-}" in
freeze)
  $PY bench/bugsinpy_rows.py --census
  cp data/bugsinpy_rows.jsonl "$ROWS"
  $PY bench/bugsinpy_gate.py --scores --rows "$ROWS" --out "$SCORES"
  echo "frozen: $(wc -l < "$ROWS") rows -> $ROWS"
  ;;
gpu)
  ./serve.sh stop || true
  rsync -az bench/eval_bugsinpy_arms.py "$HOST:oracle/bench/"
  rsync -az "$ROWS" "$SCORES" "$HOST:oracle/data/"
  # `base` first: it is the run that decides whether the training transferred,
  # and the one worth having if the batch is interrupted.
  ssh "$HOST" "bash -lc 'cd ~/oracle && source .venv/bin/activate && \
    python bench/eval_bugsinpy_arms.py --arm exec --no-adapter \
      --dataset data/$(basename "$ROWS") --scores data/$(basename "$SCORES") \
      --out data/bip_arm_base_$V.json'"
  for a in exec score diff; do
    ssh "$HOST" "bash -lc 'cd ~/oracle && source .venv/bin/activate && \
      python bench/eval_bugsinpy_arms.py --arm $a \
        --dataset data/$(basename "$ROWS") --scores data/$(basename "$SCORES") \
        --out data/bip_arm_${a}_$V.json'"
  done
  for a in base exec score diff; do
    scp -q "$HOST:oracle/data/bip_arm_${a}_$V.json" data/
  done
  MODEL=artifacts/oracle-reviewer-3b ./serve.sh start
  ;;
guarded)
  ./serve.sh status | grep -q "server: up" || MODEL=artifacts/oracle-reviewer-3b ./serve.sh start
  $PY bench/bugsinpy_guarded.py --dataset "$ROWS" --out "data/bip_guarded_$V.json"
  ;;
api)
  set -a; source "$HOME/.zshrc" >/dev/null 2>&1 || true; set +a
  for a in exec score diff; do
    $PY bench/eval_bugsinpy_arms.py --arm "$a" --backend api \
      --dataset "$ROWS" --scores "$SCORES" --out "data/bip120b_arm_${a}_$V.json"
  done
  ;;
report)
  $PY bench/bugsinpy_compare.py --arms base,exec,score,diff,guarded \
    --prefix "bip_arm_" --suffix "_$V" --rows "$ROWS"
  $PY bench/bugsinpy_compare.py --arms exec,score,diff --rows "$ROWS" --metric invented
  $PY bench/bugsinpy_compare.py --arms exec,diff --prefix bip120b_arm_ --rows "$ROWS"
  $PY test_bugsinpy_figures.py
  ;;
*)
  sed -n '2,20p' "$0"; exit 1;;
esac
