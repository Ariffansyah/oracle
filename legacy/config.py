"""Central configuration for ORACLE.

Every value can be overridden with an environment variable of the same name
prefixed with ``ORACLE_`` (e.g. ``ORACLE_OLLAMA_MODEL=llama3.1:8b``).
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _env(name: str, default):
    raw = os.getenv(f"ORACLE_{name}")
    if raw is None:
        return default
    return type(default)(raw) if not isinstance(default, Path) else Path(raw)


# --- LLM -------------------------------------------------------------------
OLLAMA_HOST = _env("OLLAMA_HOST", "http://192.168.1.170:11434")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "qwen3-coder:latest")
# Generous on purpose: a cold 18GB model load on a memory-tight host can burn
# minutes before the first token, and that is indistinguishable from a hang.
LLM_TIMEOUT_S = _env("LLM_TIMEOUT_S", 600)
LLM_TEMPERATURE = _env("LLM_TEMPERATURE", 0.1)
LLM_NUM_CTX = _env("LLM_NUM_CTX", 8192)          # prompt context window (tokens)
LLM_MAX_DIFF_CHARS = _env("LLM_MAX_DIFF_CHARS", 24000)  # diff truncation guard

# --- ML risk model ---------------------------------------------------------
MODEL_PATH = _env("MODEL_PATH", ROOT / "artifacts" / "jit_xgb.json")
RISK_THRESHOLD = _env("RISK_THRESHOLD", 0.5)     # above this the LLM is invoked
RISK_BANDS = ((0.75, "HIGH"), (0.5, "MEDIUM"), (0.0, "LOW"))
SHAP_TOP_K = _env("SHAP_TOP_K", 5)

# 14 standard Kamei et al. JIT process metrics, in model feature order.
KAMEI_FEATURES = (
    "ns",       # number of modified subsystems
    "nd",       # number of modified directories
    "nf",       # number of modified files
    "entropy",  # distribution of change across files
    "la",       # lines added
    "ld",       # lines deleted
    "lt",       # lines of code in touched files before the change
    "fix",      # is the commit a bug fix
    "ndev",     # number of developers that previously touched the files
    "age",      # average time since the last change to the files (days)
    "nuc",      # number of unique changes to the touched files
    "exp",      # author experience (number of prior commits)
    "rexp",     # recent author experience (time-weighted)
    "sexp",     # subsystem experience of the author
)

# --- DPO -------------------------------------------------------------------
DPO_BASE_MODEL = _env("DPO_BASE_MODEL", "Qwen/Qwen2.5-Coder-1.5B-Instruct")
DPO_DATASET_PATH = _env("DPO_DATASET_PATH", ROOT / "data" / "oracle_dpo.jsonl")
DPO_OUTPUT_DIR = _env("DPO_OUTPUT_DIR", ROOT / "artifacts" / "dpo-adapter")
DPO_BETA = _env("DPO_BETA", 0.1)
LORA_R = _env("LORA_R", 16)
LORA_ALPHA = _env("LORA_ALPHA", 32)
LORA_DROPOUT = _env("LORA_DROPOUT", 0.05)
LORA_TARGET_MODULES = ["q_proj", "v_proj", "k_proj", "o_proj"]


def risk_band(score: float) -> str:
    return next(label for cutoff, label in RISK_BANDS if score >= cutoff)
