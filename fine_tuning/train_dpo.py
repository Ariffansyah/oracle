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
                    LOAD_IN_4BIT, MAX_PROMPT_LENGTH, MAX_SEQ_LENGTH,
                    MERGED_MODEL_DIR, SFT_ADAPTER_DIR)
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
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    ap.add_argument("--grad-accum", type=int, default=GRAD_ACCUM)
    ap.add_argument("--lr", type=float, default=DPO_LR)
    ap.add_argument("--beta", type=float, default=DPO_BETA,
                    help="KL penalty; lower stays closer to the reference model")
    ap.add_argument("--loss-type", default=DPO_LOSS_TYPE,
                    help="TRL DPO loss variant (default dpop = DPO-Positive)")
    ap.add_argument("--max-length", type=int, default=MAX_SEQ_LENGTH)
    ap.add_argument("--max-prompt-length", type=int, default=MAX_PROMPT_LENGTH)
    ap.add_argument("--merge", action="store_true",
                    help="merge the adapter into the base weights when done")
    ap.add_argument("--merged-dir", type=Path, default=Path(MERGED_MODEL_DIR))
    ap.add_argument("--no-4bit", dest="four_bit", action="store_false")
    ap.set_defaults(four_bit=LOAD_IN_4BIT)
    return ap.parse_args(argv)


def check_loss_type(loss_type: str) -> str:
    """Confirm the installed TRL actually supports the requested DPO variant.

    `dpop` (DPO-Positive) landed in TRL after the original DPO loss, so an older
    install silently has no such option. Failing here with the real list beats
    discovering it inside the trainer after the model is loaded.
    """
    import inspect

    from trl import DPOConfig

    field = DPOConfig.__dataclass_fields__.get("loss_type")
    annotation = str(field.type) if field else ""
    # TRL declares loss_type as a Literal[...] of the supported names.
    supported = re.findall(r"'([a-z0-9_]+)'", annotation)
    if not supported:  # unknown TRL layout - let the trainer validate instead
        source = inspect.getsource(DPOConfig)
        supported = re.findall(r"'([a-z0-9_]+)'", source.split("loss_type")[1][:400])

    if supported and loss_type not in supported:
        raise SystemExit(
            f"this TRL build does not support loss_type={loss_type!r}.\n"
            f"supported: {', '.join(sorted(set(supported)))}\n"
            f"upgrade TRL (`pip install -U trl`) for DPO-Positive, or pass "
            f"--loss-type sigmoid to fall back to standard DPO."
        )
    print(f"DPO loss: {loss_type}"
          + (" (DPO-Positive — penalises chosen log-prob collapse)"
             if loss_type == "dpop" else ""))
    return loss_type


def main(argv=None) -> None:
    args = parse_args(argv)
    if not args.dataset.exists():
        raise SystemExit(
            f"{args.dataset} not found — build it first:\n"
            f"  python -m dataset_builder.build_dpo_data --mock"
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
            learning_rate=args.lr,
            lr_scheduler_type="cosine",
            warmup_ratio=0.1,
            beta=args.beta,
            loss_type=loss_type,
            max_length=args.max_length,
            max_prompt_length=args.max_prompt_length,
            logging_steps=5,
            save_strategy="epoch",
            **precision_flags(),
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
