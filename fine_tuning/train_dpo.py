"""Stage 2: preference alignment on top of the SFT adapter.

SFT teaches the format; DPO teaches restraint. The pairs prefer an empty
`findings` list on safe diffs over an invented defect, and a real finding over
false reassurance on defective ones.

    python -m fine_tuning.train_dpo
    python -m fine_tuning.train_dpo --merge      # also write merged weights

The SFT adapter is loaded and training continues on it, so the two stages
compose instead of competing. With a PEFT adapter attached TRL uses the frozen
base as the implicit reference model - no second copy is loaded.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (BASE_MODEL, BATCH_SIZE, DPO_ADAPTER_DIR, DPO_BETA,
                    DPO_DATASET, DPO_EPOCHS, DPO_LOSS_TYPE, DPO_LR, GRAD_ACCUM,
                    DPO_BATCH_SIZE, DPO_MAX_LENGTH, DPO_MAX_GRAD_NORM,
                    LOAD_IN_4BIT,
                    DPO_SFT_WEIGHT, MERGED_MODEL_DIR, SFT_ADAPTER_DIR)
from fine_tuning.qlora import (gpu_report, load_base, lora_config,
                               merge_adapter, precision_flags, require_torch)


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, default=Path(DPO_DATASET))
    ap.add_argument("--base-model", default=BASE_MODEL)
    ap.add_argument("--sft-adapter", type=Path, default=Path(SFT_ADAPTER_DIR),
                    help="adapter to continue from; omit with --from-base")
    ap.add_argument("--from-base", action="store_true",
                    help="skip the SFT adapter and align the base model directly")
    ap.add_argument("--output-dir", type=Path, default=Path(DPO_ADAPTER_DIR))
    ap.add_argument("--epochs", type=float, default=DPO_EPOCHS)
    ap.add_argument("--batch-size", type=int, default=DPO_BATCH_SIZE)
    ap.add_argument("--grad-accum", type=int, default=GRAD_ACCUM)
    ap.add_argument("--lr", type=float, default=DPO_LR)
    ap.add_argument("--beta", type=float, default=DPO_BETA,
                    help="KL penalty; lower stays closer to the reference model")
    ap.add_argument("--loss-type", default=DPO_LOSS_TYPE,
                    help="comma-separated TRL loss terms; default 'sigmoid,sft' "
                         "anchors the chosen log-prob the way DPO-Positive does")
    ap.add_argument("--sft-weight", type=float, default=DPO_SFT_WEIGHT,
                    help="weight of the anchoring sft term")
    ap.add_argument("--max-length", type=int, default=DPO_MAX_LENGTH,
                    help="covers the p90 prompt (813 tokens) plus the answer "
                         "(max 60); logits over Qwen's 152k vocab dominate "
                         "memory, so every token costs ~0.6MB of gradient")
    ap.add_argument("--warmup-steps", type=int, default=20)
    ap.add_argument("--max-grad-norm", type=float, default=DPO_MAX_GRAD_NORM,
                    help="gradient clipping; HF defaults to 1.0, which clipped "
                         "every step of the 23 Aug run 10-20x")
    ap.add_argument("--merge", action="store_true",
                    help="merge the adapter into the base weights when done")
    ap.add_argument("--merged-dir", type=Path, default=Path(MERGED_MODEL_DIR))
    ap.add_argument("--no-4bit", dest="four_bit", action="store_false")
    ap.set_defaults(four_bit=LOAD_IN_4BIT)
    return ap.parse_args(argv)


def supported_losses() -> list[str]:
    """Loss names this TRL build accepts, read from its own documentation."""
    import inspect

    from trl import DPOConfig

    source = inspect.getsource(DPOConfig)
    head = source.split("loss_type")[1][:900] if "loss_type" in source else ""
    return sorted(set(re.findall(r"`'([a-z0-9_]+)'`", head)))


def check_loss_type(loss_type: str) -> list[str]:
    """Validate the requested loss terms before anything expensive loads."""
    terms = [t.strip() for t in loss_type.split(",") if t.strip()]
    if not terms:
        raise SystemExit("--loss-type is empty")

    supported = supported_losses()
    unknown = [t for t in terms if supported and t not in supported]
    if unknown:
        raise SystemExit(
            f"this TRL build does not support {', '.join(unknown)}.\n"
            f"supported: {', '.join(supported)}\n"
            f"Note there is no `dpop` loss in TRL; ['sigmoid', 'sft'] anchors "
            f"the chosen log-probability the same way DPO-Positive does."
        )
    note = ""
    if terms == ["sigmoid", "sft"]:
        note = "  (DPO + an SFT anchor on the chosen answer — DPOP's mechanism)"
    print(f"DPO loss: {terms}{note}")
    return terms


def main(argv=None) -> None:
    args = parse_args(argv)
    if not args.dataset.exists():
        raise SystemExit(
            f"{args.dataset} not found — build it first:\n"
            f"  python -m dpo_pipeline.build_dpo_data --mock"
        )

    torch = require_torch()
    print(f"device: {gpu_report()}")
    from datasets import load_dataset
    from peft import PeftModel
    from trl import DPOConfig, DPOTrainer

    loss_type = check_loss_type(args.loss_type)

    dataset = load_dataset("json", data_files=str(args.dataset), split="train")
    print(f"{len(dataset)} preference pairs from {args.dataset}")

    model, tokenizer = load_base(args.base_model, load_in_4bit=args.four_bit)

    peft_config = lora_config()
    if not args.from_base:
        if not args.sft_adapter.exists():
            raise SystemExit(
                f"{args.sft_adapter} not found — run SFT first, or pass "
                f"--from-base to align the base model directly"
            )
        print(f"continuing from SFT adapter {args.sft_adapter}")
        model = PeftModel.from_pretrained(model, str(args.sft_adapter),
                                          is_trainable=True)
        peft_config = None  # the adapter is already attached

    trainer = DPOTrainer(
        model=model,
        ref_model=None,  # frozen base acts as the reference
        args=DPOConfig(
            output_dir=str(args.output_dir),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            # Paged states survive the VRAM spikes that otherwise OOM a small
            # card mid-step; 8-bit keeps the optimiser itself off the budget.
            optim="paged_adamw_8bit",
            learning_rate=args.lr,
            lr_scheduler_type="cosine",
            warmup_steps=args.warmup_steps,
            max_grad_norm=args.max_grad_norm,
            beta=args.beta,
            loss_type=loss_type,
            **({"loss_weights": [1.0, args.sft_weight]}
               if len(loss_type) > 1 else {}),
            max_length=args.max_length,
            # DPO holds logits for the policy *and* the reference model, and
            # Qwen's 152k vocab makes each one ~1.2GB at 2048 tokens. Computing
            # the reference log-probs in a separate pass first means the two are
            # never resident together - the single biggest saving available.
            precompute_ref_log_probs=True,
            precompute_ref_batch_size=1,
            # Prompts run 751-1132 tokens (median 751); padding every one to a
            # fixed length wastes about a quarter of the activation memory that
            # the vocab-sized logits then have to carry.
            padding_free=True,
            # DPOConfig no longer takes max_prompt_length; prompts are
            # truncated within max_length by truncation_mode.
            truncation_mode="keep_end",
            logging_steps=5,
            save_strategy="epoch",
            # Free the allocator between steps: fragmentation is what turns a
            # "just fits" run into an OOM three steps in.
            torch_empty_cache_steps=1,
            **precision_flags(args.four_bit),
            report_to=[],
        ),
        train_dataset=dataset,
        processing_class=tokenizer,
        peft_config=peft_config,
    )

    trainer.train()
    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    print(f"\nDPO adapter -> {args.output_dir}")

    if args.merge:
        merge_adapter(args.output_dir, args.merged_dir, args.base_model)
        print(f"run it:\n  python main.py analyze --model {args.merged_dir} --mock")


if __name__ == "__main__":
    main()
