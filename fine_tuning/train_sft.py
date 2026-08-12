"""Stage 1: supervised fine-tuning with QLoRA.

Teaches the base model the task and the output format - given a diff, emit one
`Analysis` JSON object. Stage 2 (DPO) then fixes *what* it says; this stage only
establishes *how* it answers.

    python -m dataset_builder.build_sft_data --mock
    python -m fine_tuning.train_sft
    python -m fine_tuning.train_sft --base-model Qwen/Qwen2.5-Coder-1.5B-Instruct
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (BASE_MODEL, BATCH_SIZE, GRAD_ACCUM, LOAD_IN_4BIT,
                    MAX_SEQ_LENGTH, SFT_ADAPTER_DIR, SFT_DATASET, SFT_EPOCHS,
                    SFT_LR)
from fine_tuning.qlora import (gpu_report, load_base, lora_config,
                               precision_flags, require_torch)


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, default=Path(SFT_DATASET))
    ap.add_argument("--base-model", default=BASE_MODEL)
    ap.add_argument("--output-dir", type=Path, default=Path(SFT_ADAPTER_DIR))
    ap.add_argument("--epochs", type=float, default=SFT_EPOCHS)
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    ap.add_argument("--grad-accum", type=int, default=GRAD_ACCUM)
    ap.add_argument("--lr", type=float, default=SFT_LR)
    ap.add_argument("--max-seq-length", type=int, default=MAX_SEQ_LENGTH)
    ap.add_argument("--no-4bit", dest="four_bit", action="store_false",
                    help="load in bf16 instead of 4-bit (needs much more VRAM)")
    ap.set_defaults(four_bit=LOAD_IN_4BIT)
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    if not args.dataset.exists():
        raise SystemExit(
            f"{args.dataset} not found — build it first:\n"
            f"  python -m dataset_builder.build_sft_data --mock"
        )

    torch = require_torch()
    print(f"device: {gpu_report()}")
    from datasets import load_dataset
    from trl import SFTConfig, SFTTrainer

    dataset = load_dataset("json", data_files=str(args.dataset), split="train")
    print(f"{len(dataset)} SFT examples from {args.dataset}")
    if len(dataset) < 32:
        print("warning: very small dataset — expect memorisation, not learning")

    model, tokenizer = load_base(args.base_model, load_in_4bit=args.four_bit)

    trainer = SFTTrainer(
        model=model,
        args=SFTConfig(
            output_dir=str(args.output_dir),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            gradient_checkpointing=True,
            learning_rate=args.lr,
            lr_scheduler_type="cosine",
            warmup_ratio=0.03,
            max_length=args.max_seq_length,
            logging_steps=5,
            save_strategy="epoch",
            **precision_flags(),
            report_to=[],
            # The dataset is already conversational: TRL applies the chat
            # template and masks everything but the assistant turn.
            assistant_only_loss=True,
        ),
        train_dataset=dataset,
        processing_class=tokenizer,
        peft_config=lora_config(),
    )

    trainer.train()
    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    print(f"\nSFT adapter -> {args.output_dir}")
    print("next:\n"
          "  python -m dataset_builder.build_dpo_data --mock\n"
          "  python -m fine_tuning.train_dpo")


if __name__ == "__main__":
    main()
