"""ORACLE configuration.

Every value is overridable by an environment variable of the same name prefixed
with ``ORACLE_`` (e.g. ``ORACLE_BASE_MODEL=Qwen/Qwen2.5-Coder-1.5B-Instruct``).
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ARTIFACTS = ROOT / "artifacts"


def _env(name: str, default):
    raw = os.getenv(f"ORACLE_{name}")
    if raw is None:
        return default
    if isinstance(default, Path):
        return Path(raw)
    if isinstance(default, bool):
        return raw.lower() in ("1", "true", "yes")
    return type(default)(raw)


# --- Models ----------------------------------------------------------------
# 7B is the target; drop to 1.5B to train on a single small GPU or on CPU.
# 3B is the design point, not a compromise. The task is narrow - read a diff,
# emit one JSON verdict - and a small model masters it once trained. It also
# trains on 6GB of VRAM (7B was measured OOMing on a GTX 1660 SUPER before the
# first step) and answers in well under a second.
# ORACLE_BASE_MODEL=Qwen/Qwen2.5-Coder-1.5B-Instruct trades a little accuracy
# for roughly half the latency and memory.
BASE_MODEL = _env("BASE_MODEL", "Qwen/Qwen2.5-Coder-3B-Instruct")
SFT_ADAPTER_DIR = _env("SFT_ADAPTER_DIR", ARTIFACTS / "sft-adapter")
DPO_ADAPTER_DIR = _env("DPO_ADAPTER_DIR", ARTIFACTS / "dpo-adapter")
MERGED_MODEL_DIR = _env("MERGED_MODEL_DIR", ARTIFACTS / "oracle-merged")

# --- Datasets --------------------------------------------------------------
RAW_COMMITS_CSV = _env("RAW_COMMITS_CSV", DATA / "commits.csv")
SFT_DATASET = _env("SFT_DATASET", DATA / "oracle_sft.jsonl")
DPO_DATASET = _env("DPO_DATASET", DATA / "oracle_dpo.jsonl")

# --- QLoRA -----------------------------------------------------------------
LOAD_IN_4BIT = _env("LOAD_IN_4BIT", True)
BNB_QUANT_TYPE = _env("BNB_QUANT_TYPE", "nf4")
BNB_DOUBLE_QUANT = _env("BNB_DOUBLE_QUANT", True)

# r=64 on a 3B is ~120M trainable params. Capacity is cheap here - the adapter
# is still small, and a narrow task learned well beats a narrow task learned
# thinly. The MLP projections are included because
# format adherence (always valid JSON) lives there as much as in attention.
LORA_R = _env("LORA_R", 64)
LORA_ALPHA = _env("LORA_ALPHA", 128)
LORA_DROPOUT = _env("LORA_DROPOUT", 0.05)
LORA_TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj",
                       "gate_proj", "up_proj", "down_proj"]

# --- Training --------------------------------------------------------------
# Measured on the real corpus: prompts run 414 tokens median, 476 at p90, 795
# max once the JSON Schema is out of the prompt. 1024 covers everything with
# headroom, and shorter sequences are the main reason 3B trains comfortably.
# Real corpus prompts measure ~800 tokens median (2917 chars). 1024 covers the
# distribution; 1536 was paying for padding that is not there, at ~30% more
# time per step.
MAX_SEQ_LENGTH = _env("MAX_SEQ_LENGTH", 1024)
MAX_PROMPT_LENGTH = _env("MAX_PROMPT_LENGTH", 896)
# 2 epochs over 1759 real examples, not 4 over 200 templated ones. More epochs
# on a small corpus memorise; more data is what generalises, and we now have it.
SFT_EPOCHS = _env("SFT_EPOCHS", 2.0)
SFT_LR = _env("SFT_LR", 2e-4)          # LoRA tolerates a high LR
DPO_EPOCHS = _env("DPO_EPOCHS", 1.0)
DPO_LR = _env("DPO_LR", 5e-6)          # preference tuning needs a small one
# Standard DPO can drive the log-probability of the *chosen* answer down as long
# as the rejected one falls faster - exactly what happens when the two differ by
# a few tokens, as in a frontend edit where "safe" and "defective" share 95% of
# their text (DPO-Positive, Pal et al. 2024, names this failure).
#
# TRL has no `dpop` loss. It does support combining losses, and the same anchor
# is obtained with ["sigmoid", "sft"]: the sigmoid term is ordinary DPO, and the
# sft term is an NLL on the chosen answer, which is precisely the quantity DPOP
# stops from collapsing. `DPO_SFT_WEIGHT` is how hard that anchor pulls.
DPO_LOSS_TYPE = _env("DPO_LOSS_TYPE", "sigmoid,sft")
DPO_SFT_WEIGHT = _env("DPO_SFT_WEIGHT", 0.5)
DPO_BETA = _env("DPO_BETA", 0.5)
BATCH_SIZE = _env("BATCH_SIZE", 1)     # 1536 tokens: one at a time
# DPO processes chosen *and* rejected, so a batch of 2 is really 4 sequences,
# each carrying logits over a 152k vocab. Measured OOM on 6GB at batch 2.
DPO_BATCH_SIZE = _env("DPO_BATCH_SIZE", 1)
# 512, not 768. DPO's peak is the logits tensor and its gradient, both sized
# tokens x 152k vocab: at 768 the chosen+rejected pair needs ~1.8GB of the
# 5.61GB card, on top of ~1.9GB of 4-bit weights and a ~1.2GB fp32 lm_head.
# Measured OOM at 768, fits at 512. Prompts are 414 tokens median, so this
# truncates only the long tail (truncation_mode keeps the end, which is the
# diff and the answer).
DPO_MAX_LENGTH = _env("DPO_MAX_LENGTH", 512)
GRAD_ACCUM = _env("GRAD_ACCUM", 8)

# --- Stage 1: deep-learning gatekeeper --------------------------------------
# A pretrained code encoder reads the diff; a small classifier turns that plus
# the process metrics into one probability in milliseconds. Its job is to say
# "certainly safe" cheaply so the 3B validator is never invoked on the ~75% of
# commits that need no review.
GATE_ENCODER = _env("GATE_ENCODER", "microsoft/graphcodebert-base")
GATE_ENCODER_MAX_TOKENS = _env("GATE_ENCODER_MAX_TOKENS", 512)
GATE_EMBED_CACHE = _env("GATE_EMBED_CACHE", ARTIFACTS / "gate_embeddings.npz")
GATE_MODEL_PATH = _env("GATE_MODEL_PATH", ARTIFACTS / "gate.joblib")
GATE_HEAD = _env("GATE_HEAD", "lightgbm")          # lightgbm | mlp

# The gate is deliberately biased toward letting commits through. A false
# negative here is a defect that is never reviewed by anything; a false positive
# only costs one LLM call. The threshold is therefore not 0.5 - it is whatever
# achieves the recall below on held-out data, and `train_gate.py` solves for it.
GATE_TARGET_RECALL = _env("GATE_TARGET_RECALL", 0.95)
GATE_THRESHOLD = _env("GATE_THRESHOLD", 0.15)

# --- Inference -------------------------------------------------------------
# "transformers" loads the adapter/merged weights locally; "ollama" talks to a
# served GGUF build of the same model.
# The fine-tuned 3B is the intended Stage 2 validator: it fits in VRAM and
# answers in well under a second. Until it is trained and merged there is
# nothing to load, so the backend resolves at run time - `auto` prefers the
# local merged model and falls back to a served one while it does not exist.
BACKEND = _env("BACKEND", "auto")
# The merged 3B is ~5.8GB in fp16, which does not fit the 5.61GB usable on a
# 6GB card: transformers silently offloads layers to CPU and latency collapses.
# Loading it 4-bit puts the whole model in VRAM (~2GB) and keeps inference
# sub-second, which is the entire reason for choosing a 3B.
INFERENCE_4BIT = _env("INFERENCE_4BIT", True)
# Default to the local end of the SSH tunnel to the GPU box, where
# `llm_explainer.serve` exposes the fine-tuned model:
#   ssh -f -N -L 8111:localhost:8111 oracle-gpu
# Set ORACLE_OLLAMA_HOST=http://192.168.1.170:11434 to talk to Ollama instead.
OLLAMA_HOST = _env("OLLAMA_HOST", "http://localhost:8111")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "oracle-merged")
# Whether to spell the full JSON Schema out in the prompt. "auto" decides from
# the model: a locally-loaded fine-tuned one learnt the short form and does not
# need it, anything else does.
#
# Over HTTP that inference is impossible - the server just answers - so a served
# *tuned* model gets the schema it never saw in training unless you say so here.
# Set ORACLE_INCLUDE_SCHEMA=false when serving a checkpoint from serve.py.
INCLUDE_SCHEMA = _env("INCLUDE_SCHEMA", "auto")   # auto | true | false
# Sent explicitly on every request. Ollama otherwise falls back to whatever the
# Modelfile baked in, or its own 4096 default - and a prompt carrying file
# context silently overflows that without any error.
OLLAMA_NUM_CTX = _env("OLLAMA_NUM_CTX", 16384)
# Quality over latency: a cap that truncates a third finding mid-sentence is a
# worse failure than a slow answer. 768 lets the model report everything it
# found; the cost is seconds, and seconds are affordable here.
MAX_NEW_TOKENS = _env("MAX_NEW_TOKENS", 768)
TEMPERATURE = _env("TEMPERATURE", 0.0)  # greedy: a verdict should be reproducible
# With >1, the reviewer answers several times and keeps only findings a majority
# of samples agree on. Costs N times the latency, removes one-off hallucinations
# - the failure mode that matters most when the output is prose.
INFERENCE_SAMPLES = _env("INFERENCE_SAMPLES", 1)
INFERENCE_SAMPLE_TEMPERATURE = _env("INFERENCE_SAMPLE_TEMPERATURE", 0.6)
MAX_DIFF_CHARS = _env("MAX_DIFF_CHARS", 12000)

# Per-file chunked review. One prompt covering a whole large commit dilutes
# attention across every file and the model drifts into describing rather than
# auditing - measured on a 34kB commit, it summarised correctly and reported
# nothing. Above this size the client reviews file by file and merges.
# Context retrieval. A diff alone is a keyhole: the model sees `if (!token)
# return;` and calls it dead code because the disabled submit button that makes
# it belt-and-braces lives forty lines away, outside the hunk. Expanding the
# unified context - and attaching the post-commit file when it is small enough -
# is what removes that class of hallucination.
# More context, not less. The captcha case proved the point: a guard looks like
# dead code until you can see the disabled button forty lines away. Larger
# windows cost inference time and nothing else.
# Measured on a GTX 1660 SUPER serving the 3B: no context 8s, 4kB of context
# 50s, 20kB OOMs. Prefill cost is quadratic-ish in prompt length on this card,
# so context is bounded by what stays usable rather than by what fits.
EXPANDED_CONTEXT_LINES = _env("EXPANDED_CONTEXT_LINES", 60)
FULL_FILE_MAX_CHARS = _env("FULL_FILE_MAX_CHARS", 6000)
CONTEXT_MAX_CHARS = _env("CONTEXT_MAX_CHARS", 8000)

# Chunk earlier. Reviewing 15 files in one prompt produced 0 findings on a real
# 34kB commit; one prompt per file produced 7. Attention per file is what finds
# defects, and more prompts only costs time.
CHUNK_OVER_CHARS = _env("CHUNK_OVER_CHARS", 3000)
CHUNK_MAX_FILES = _env("CHUNK_MAX_FILES", 40)
CHUNK_SKIP_OVER_CHARS = _env("CHUNK_SKIP_OVER_CHARS", 60000)  # generated/vendored
REQUEST_TIMEOUT_S = _env("REQUEST_TIMEOUT_S", 600)
