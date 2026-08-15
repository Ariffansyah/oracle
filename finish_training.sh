#!/bin/bash
# Finish Stage 2: DPO on top of the SFT adapter, merge, verify.
#
# Everything here has already been tuned to fit a 6GB card: batch 1 (DPO holds
# chosen *and* rejected), max_length 768, reference log-probs precomputed so the
# policy and reference models are never resident together, and the JSON schema
# out of the prompt (it was 45% of every sequence).
#
#   ./finish_training.sh              # DPO + merge
#   ./finish_training.sh --skip-dpo   # merge the SFT adapter only
set -euo pipefail

HOST=${ORACLE_GPU_HOST:-oracle-gpu}
R() { ssh -o BatchMode=yes "$HOST" "bash -lc '$1'"; }

if ! ssh -o BatchMode=yes -o ConnectTimeout=8 "$HOST" true 2>/dev/null; then
  echo "cannot reach $HOST — wake the machine first"
  exit 1
fi

if [ "${1:-}" != "--skip-dpo" ]; then
  echo "=== building the preference set ==="
  R 'cd ~/oracle && .venv/bin/python -m dpo_pipeline.build_dpo_data --mock --n 120 --hard-negatives 40 | tail -1'

  echo "=== DPO (batch 1, len 768, precomputed reference log-probs) ==="
  R 'cd ~/oracle && PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True nohup .venv/bin/python -m fine_tuning.train_dpo --epochs 1 --merge > ~/oracle/dpo.log 2>&1 & sleep 5; echo launched'
  while R 'pgrep -f "fine_tuning[.]train_dpo" >/dev/null'; do sleep 60; done
  R 'tr "\r" "\n" < ~/oracle/dpo.log | grep -vE "it/s\]|s/it\]" | tail -6'
else
  echo "=== merging the SFT adapter only (no DPO) ==="
  R 'cd ~/oracle && .venv/bin/python -c "
from fine_tuning.qlora import merge_adapter
from config import BASE_MODEL, MERGED_MODEL_DIR, SFT_ADAPTER_DIR
merge_adapter(SFT_ADAPTER_DIR, MERGED_MODEL_DIR, BASE_MODEL)"'
fi

echo "=== artifacts ==="
R 'du -sh ~/oracle/artifacts/* 2>/dev/null'

# The merged model is what makes BACKEND=auto resolve to the tuned 3B.
if R 'test -f ~/oracle/artifacts/oracle-merged/config.json'; then
  echo "=== smoke test on the tuned model ==="
  R 'cd ~/oracle && .venv/bin/python main.py analyze --backend transformers --no-gate --json 2>/dev/null | tail -12'
  echo
  echo "merged model exists — BACKEND=auto now resolves to the tuned 3B."
  echo "pull it to this machine with:"
  echo "  rsync -az $HOST:~/oracle/artifacts/oracle-merged/ artifacts/oracle-merged/"
else
  echo "!!! no merged model was written — check ~/oracle/dpo.log"
  exit 1
fi
