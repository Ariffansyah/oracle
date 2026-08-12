"""Shared QLoRA setup for both training stages.

Kept in one place so SFT and DPO cannot drift into different quantisation or
adapter shapes - a DPO run whose LoRA config disagrees with the SFT adapter it
continues from silently trains the wrong parameters.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (BNB_DOUBLE_QUANT, BNB_QUANT_TYPE, LOAD_IN_4BIT, LORA_ALPHA,
                    LORA_DROPOUT, LORA_R, LORA_TARGET_MODULES)


def require_torch():
    """Fail with instructions rather than a bare ImportError."""
    import importlib.util

    missing = [m for m in ("torch", "transformers", "trl", "peft", "datasets")
               if importlib.util.find_spec(m) is None]
    if missing:
        raise SystemExit(
            f"missing training dependencies: {', '.join(missing)}\n"
            "  pip install torch transformers trl peft datasets accelerate bitsandbytes\n"
            "Everything except training runs without them."
        )
    import torch

    return torch


def compute_dtype():
    """bfloat16 where the GPU supports it, float16 otherwise.

    Turing cards (GTX 16xx, RTX 20xx) have no bf16 - asking for it either throws
    or silently falls back. Ampere and newer do. CPU keeps float32.
    """
    import torch

    if not torch.cuda.is_available():
        return torch.float32
    return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16


def precision_flags() -> dict:
    """`bf16=`/`fp16=` for a HuggingFace TrainingArguments, matched to the GPU."""
    import torch

    if not torch.cuda.is_available():
        return {"bf16": False, "fp16": False}
    bf16 = torch.cuda.is_bf16_supported()
    return {"bf16": bf16, "fp16": not bf16}


def quant_config(load_in_4bit: bool = LOAD_IN_4BIT):
    """4-bit NF4 with double quantisation, or None for full precision."""
    if not load_in_4bit:
        return None
    from transformers import BitsAndBytesConfig

    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type=BNB_QUANT_TYPE,
        bnb_4bit_use_double_quant=BNB_DOUBLE_QUANT,
        bnb_4bit_compute_dtype=compute_dtype(),
    )


def lora_config():
    from peft import LoraConfig

    return LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=LORA_TARGET_MODULES,
        bias="none",
        task_type="CAUSAL_LM",
    )


def load_base(model_name: str, load_in_4bit: bool = LOAD_IN_4BIT):
    """Base model + tokenizer, ready for a LoRA adapter."""
    torch = require_torch()
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        # Qwen has no pad token; reusing EOS is standard and the collator masks
        # padded positions anyway.
        tokenizer.pad_token = tokenizer.eos_token

    # Turing has no bf16 and no FlashAttention-2; SDPA is the fast path there.
    kwargs = {"dtype": compute_dtype(), "device_map": "auto",
              "attn_implementation": "sdpa"}
    if (qc := quant_config(load_in_4bit)) is not None:
        kwargs["quantization_config"] = qc

    model = AutoModelForCausalLM.from_pretrained(model_name, **kwargs)
    model.config.use_cache = False  # incompatible with gradient checkpointing
    return model, tokenizer


def merge_adapter(adapter_dir: Path, out_dir: Path, base_model: str) -> Path:
    """Fold a LoRA adapter into the base weights and save as safetensors."""
    torch = require_torch()
    from peft import AutoPeftModelForCausalLM
    from transformers import AutoTokenizer

    if not Path(adapter_dir).exists():
        raise SystemExit(f"{adapter_dir} not found — train first")

    print(f"merging {adapter_dir} into base weights (loads the full model)")
    model = AutoPeftModelForCausalLM.from_pretrained(
        str(adapter_dir), dtype=torch.float16, device_map="cpu"
    )  # fp16 on CPU for the merge: widely compatible, halves the file size
    merged = model.merge_and_unload()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(out_dir), safe_serialization=True)
    AutoTokenizer.from_pretrained(base_model).save_pretrained(str(out_dir))
    print(f"merged model -> {out_dir}")
    return out_dir


def gpu_report() -> str:
    """What the training GPU can actually do - printed before every run."""
    import torch

    if not torch.cuda.is_available():
        return "no CUDA GPU visible — training will run on CPU (slow)"
    name = torch.cuda.get_device_name(0)
    vram = torch.cuda.get_device_properties(0).total_memory / 1e9
    cap = ".".join(map(str, torch.cuda.get_device_capability(0)))
    bf16 = torch.cuda.is_bf16_supported()
    note = "" if bf16 else "  (no bf16 on this architecture — using fp16)"
    return (f"{name}, {vram:.1f}GB VRAM, compute {cap}, "
            f"dtype={'bf16' if bf16 else 'fp16'}{note}")


if __name__ == "__main__":
    # Config sanity that needs no GPU.
    assert LORA_TARGET_MODULES == ["q_proj", "k_proj", "v_proj", "o_proj"]
    assert LORA_ALPHA == 2 * LORA_R, "alpha = 2r is the usual scaling"

    import torch

    flags = precision_flags()
    assert not (flags["bf16"] and flags["fp16"]), "bf16 and fp16 are exclusive"
    if not torch.cuda.is_available():
        assert compute_dtype() is torch.float32
        assert flags == {"bf16": False, "fp16": False}

    print(f"QLoRA: r={LORA_R} alpha={LORA_ALPHA} dropout={LORA_DROPOUT} "
          f"4bit={LOAD_IN_4BIT} targets={','.join(LORA_TARGET_MODULES)}")
    print(f"device: {gpu_report()}")
