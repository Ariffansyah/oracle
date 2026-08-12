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
BASE_MODEL = _env("BASE_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct")
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

LORA_R = _env("LORA_R", 16)
LORA_ALPHA = _env("LORA_ALPHA", 32)
LORA_DROPOUT = _env("LORA_DROPOUT", 0.05)
LORA_TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj"]

# --- Training --------------------------------------------------------------
MAX_SEQ_LENGTH = _env("MAX_SEQ_LENGTH", 8192)   # full-file context needs the room
MAX_PROMPT_LENGTH = _env("MAX_PROMPT_LENGTH", 6144)
SFT_EPOCHS = _env("SFT_EPOCHS", 2.0)
SFT_LR = _env("SFT_LR", 2e-4)          # LoRA tolerates a high LR
DPO_EPOCHS = _env("DPO_EPOCHS", 1.0)
DPO_LR = _env("DPO_LR", 5e-6)          # preference tuning needs a small one
# DPO-Positive (Pal et al. 2024). Standard DPO can drive the log-probability of
# the *chosen* answer down as long as the rejected one falls faster, which is
# exactly what happens when the two differ by a few tokens - a frontend edit
# where "safe" and "defective" share 95% of their text. DPOP adds a penalty term
# that stops the chosen likelihood collapsing.
DPO_LOSS_TYPE = _env("DPO_LOSS_TYPE", "dpop")
DPO_BETA = _env("DPO_BETA", 0.5)
BATCH_SIZE = _env("BATCH_SIZE", 1)
GRAD_ACCUM = _env("GRAD_ACCUM", 8)

# --- Inference -------------------------------------------------------------
# "transformers" loads the adapter/merged weights locally; "ollama" talks to a
# served GGUF build of the same model.
# "ollama" talks to a served GGUF build over HTTP - the only path that runs
# without the training stack installed. Switch to "transformers" once a
# fine-tuned adapter or merged model exists locally.
BACKEND = _env("BACKEND", "ollama")
OLLAMA_HOST = _env("OLLAMA_HOST", "http://192.168.1.170:11434")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "qwen2.5-review")
# Sent explicitly on every request. Ollama otherwise falls back to whatever the
# Modelfile baked in, or its own 4096 default - and a prompt carrying file
# context silently overflows that without any error.
OLLAMA_NUM_CTX = _env("OLLAMA_NUM_CTX", 16384)
MAX_NEW_TOKENS = _env("MAX_NEW_TOKENS", 768)
TEMPERATURE = _env("TEMPERATURE", 0.1)
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
EXPANDED_CONTEXT_LINES = _env("EXPANDED_CONTEXT_LINES", 50)
FULL_FILE_MAX_CHARS = _env("FULL_FILE_MAX_CHARS", 8000)
CONTEXT_MAX_CHARS = _env("CONTEXT_MAX_CHARS", 24000)

CHUNK_OVER_CHARS = _env("CHUNK_OVER_CHARS", 6000)
CHUNK_MAX_FILES = _env("CHUNK_MAX_FILES", 40)
CHUNK_SKIP_OVER_CHARS = _env("CHUNK_SKIP_OVER_CHARS", 60000)  # generated/vendored
REQUEST_TIMEOUT_S = _env("REQUEST_TIMEOUT_S", 600)
