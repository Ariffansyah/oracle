"""LoRA + DPO fine-tune of the reviewer model with HuggingFace TRL.

    python dpo_pipeline/train_dpo.py --dataset data/oracle_dpo.jsonl --epochs 1

Torch/TRL are imported inside `main()` so the rest of ORACLE runs without the
deep-learning stack installed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run as a script

from config import (
    DPO_BASE_MODEL,
    DPO_BETA,
    DPO_DATASET_PATH,
    DPO_OUTPUT_DIR,
    LORA_ALPHA,
    LORA_DROPOUT,
    LORA_R,
    LORA_TARGET_MODULES,
)


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="DPO-align the ORACLE reviewer.")
    ap.add_argument("--dataset", type=Path, default=Path(DPO_DATASET_PATH))
    ap.add_argument("--base-model", default=DPO_BASE_MODEL)
    ap.add_argument("--output-dir", type=Path, default=Path(DPO_OUTPUT_DIR))
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=5e-6)
    ap.add_argument("--beta", type=float, default=DPO_BETA,
                    help="DPO KL penalty; lower stays closer to the reference model")
    ap.add_argument("--max-length", type=int, default=4096)
    ap.add_argument("--max-prompt-length", type=int, default=3072)
    ap.add_argument("--4bit", dest="load_4bit", action="store_true",
                    help="load the base model in 4-bit (QLoRA)")
    ap.add_argument("--tui", action="store_true",
                    help="watch loss and reward margins in a live dashboard")
    return ap.parse_args(argv)


def _tui_callback(on_log):
    """TRL callback that forwards every logging step to the dashboard."""
    from transformers import TrainerCallback

    class Forward(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kw):
            if logs:
                on_log({"step": state.global_step, **logs})

    return Forward()


def main(argv=None) -> None:
    args = parse_args(argv)
    if not args.dataset.exists():
        raise SystemExit(
            f"{args.dataset} not found - build it first:\n"
            f"  python dpo_pipeline/dataset_builder.py --output {args.dataset}"
        )

    import importlib.util

    if importlib.util.find_spec("torch") is None:
        raise SystemExit(
            "torch is not installed — the DPO stack is optional:\n"
            "  pip install torch transformers trl peft datasets accelerate\n"
            "Preview the training dashboard without it: python -m ui.train_app"
        )

    if not args.tui:
        return run(args)

    from ui.train_app import TrainMonitor

    pairs = sum(1 for line in args.dataset.open() if line.strip())
    steps = max(int(pairs * args.epochs / (args.batch_size * args.grad_accum)), 1)
    cfg = (
        f"base      {args.base_model}\n"
        f"dataset   {args.dataset} ({pairs} pairs)\n"
        f"lora      r={LORA_R} alpha={LORA_ALPHA} {','.join(LORA_TARGET_MODULES)}\n"
        f"beta      {args.beta}   lr {args.lr}\n"
        f"batch     {args.batch_size} x {args.grad_accum} accum   epochs {args.epochs}\n"
        f"output    {args.output_dir}"
    )
    TrainMonitor(lambda on_log: run(args, on_log), total_steps=steps, cfg=cfg).run()


def run(args, on_log=None) -> None:
    import torch
    from datasets import load_dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import DPOConfig, DPOTrainer

    dataset = load_dataset("json", data_files=str(args.dataset), split="train")
    print(f"{len(dataset)} preference pairs from {args.dataset}")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model_kwargs = {"dtype": torch.bfloat16, "device_map": "auto"}
    if args.load_4bit:
        from transformers import BitsAndBytesConfig

        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

    model = AutoModelForCausalLM.from_pretrained(args.base_model, **model_kwargs)
    model.config.use_cache = False

    peft_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=LORA_TARGET_MODULES,
        bias="none",
        task_type="CAUSAL_LM",
    )

    trainer = DPOTrainer(
        model=model,
        # ref_model=None: with a PEFT adapter TRL uses the frozen base weights
        # as the implicit reference model.
        ref_model=None,
        args=DPOConfig(
            output_dir=str(args.output_dir),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            gradient_checkpointing=True,
            learning_rate=args.lr,
            lr_scheduler_type="cosine",
            warmup_ratio=0.1,
            beta=args.beta,
            max_length=args.max_length,
            max_prompt_length=args.max_prompt_length,
            logging_steps=5,
            save_strategy="epoch",
            bf16=torch.cuda.is_available(),
            report_to=[],
        ),
        train_dataset=dataset,
        processing_class=tokenizer,
        peft_config=peft_config,
        callbacks=[_tui_callback(on_log)] if on_log else None,
    )

    trainer.train()
    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    print(f"adapter saved -> {args.output_dir}")
    print("serve it with Ollama by merging the adapter, or load it via PEFT in Python.")


if __name__ == "__main__":
    main()
