#!/bin/bash
# CVEfixes detection eval: 500 fix commits, each emitted forward (clean) and
# reversed (introduces the CVE). Human-written explanations, no teacher.
# checkpoint-220 first — stock is the comparison and can be killed if the GPU
# is needed sooner.
cd ~/oracle || exit 1
set -x
.venv/bin/python evaluate.py --backend transformers \
  --model artifacts/sft-adapter/checkpoint-220 --heldout data/cvefixes_eval.jsonl \
  --limit 1000 --name cve-220 --out data/cve_sft220.jsonl
.venv/bin/python evaluate.py --backend transformers \
  --model Qwen/Qwen2.5-Coder-3B-Instruct --heldout data/cvefixes_eval.jsonl \
  --limit 1000 --name cve-stock --out data/cve_stock.jsonl
echo "CVE EVAL DONE"
