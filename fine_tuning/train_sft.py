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
    ap.add_argument("--warmup-steps", type=int, default=10)
    # TRL defaults to seed=42 and nothing here ever overrode it, so every run in
    # this project so far shares one seed. That makes two checkpoints trained on
    # different corpora incomparable in one specific way: there is no measurement
    # of how much a retrain moves on its own. Varying this is how you get one.
    ap.add_argument("--seed", type=int, default=42,
                    help="training seed; vary it to measure run-to-run variance")
    # A 2-epoch run on this card is ~32h. Stopping at the epoch-1 checkpoint to
    # score it, then continuing, costs nothing in fidelity: optimiser state, LR
    # schedule, RNG and dataloader position all come back from the checkpoint.
    ap.add_argument("--resume", nargs="?", const="auto", default=None,
                    metavar="CHECKPOINT",
                    help="continue an interrupted run: bare --resume takes the "
                         "latest checkpoint under --output-dir, or name one")
    # THE VERDICT IS 1% OF THE TARGET. Measured 2 Sep: the supervised answer
    # averages 100 tokens and `defect_found` is exactly one of them, against a
    # 71% negative base rate. Plain token cross-entropy therefore prices the only
    # decision the task is about at 1% of the loss, and the epoch-1 checkpoint
    # took the free option -- it answered `false` to 40/40 examples it had been
    # trained to call `true` while showing loss 0.23 and 93% token accuracy.
    #
    # This adds an auxiliary cross-entropy on the verdict token alone, so that
    # token is priced separately from the 99 that surround it. As a coefficient
    # rather than a multiplier because it is cheap: it gathers one logit row per
    # example instead of upcasting the full (batch x seq x vocab) tensor, which
    # does not fit beside the model on a 6GB card.
    #
    #   share of total loss ~= (w + 1/N) / (1 + w)   for an N-token target
    #   w=0.5, N=100  ->  ~34%      w=0.1  ->  ~10%      w=0 -> off (1%)
    ap.add_argument("--verdict-weight", type=float, default=0.0, metavar="W",
                    help="auxiliary loss coefficient on the defect_found token "
                         "(0 = off, 0.5 puts it at ~34%% of the loss)")
    # A 16h run is far too expensive to be the thing that discovers the verdict
    # token was never located. This locates it over N batches and exits.
    # The split exists to answer one question each epoch: does the model ever
    # say `true`? Nothing measured that on the first run, which is how a model
    # that answered `false` to 40/40 of its own training positives ran 16h
    # looking healthy.
    ap.add_argument("--eval-dataset", type=Path, default=None,
                    help="held-out set; verdict recall is reported each epoch")
    # An epoch-end-only metric is a postmortem, not a gate: it reports after the
    # GPU time has already been spent. Evaluating every N steps is what lets a
    # zero-recall run be killed in the first hour.
    #
    # Step cost depends on the corpus, so do not plan a run from a number
    # written here. Measured on this card (1660 SUPER, 6GB, fp16, 4-bit base):
    #   exec_sft_v2   1103 rows, 138 steps, ~4.7h total          (3 Sep)
    #   exec_sft_v3   1170 rows, 147 steps, ~110s/step -> ~4.5h  (5 Sep)
    # An earlier version of this comment claimed ~6 min/step and a 14h epoch,
    # which produced a 3x-wrong ETA. Read the tqdm estimate off the first few
    # steps instead.
    ap.add_argument("--eval-steps", type=int, default=0, metavar="N",
                    help="also report holdout recall every N optimizer steps")
    # A forward pass costs ~15s on this card, so a 100-example holdout is
    # ~25min per eval -- hours bolted onto the run at a small --eval-steps.
    # Capping trades precision on the recall figure for a gate that is cheap
    # enough to fire often. This used to say "safe only because the holdout is
    # shuffled" -- it is not; the generators group by family. The slice is
    # shuffled at load time now, which is what makes the claim true.
    ap.add_argument("--eval-max", type=int, default=0, metavar="N",
                    help="evaluate at most N held-out examples (0 = all)")
    ap.add_argument("--verdict-check", type=int, default=0, metavar="N",
                    help="locate the verdict token over N batches, print what "
                         "was found, and exit without training")
    ap.add_argument("--no-4bit", dest="four_bit", action="store_false",
                    help="load in bf16 instead of 4-bit (needs much more VRAM)")
    ap.set_defaults(four_bit=LOAD_IN_4BIT)
    return ap.parse_args(argv)


def resolve_resume(args, n_examples: int):
    """Turn --resume into a checkpoint path, refusing a mismatched schedule.

    Resuming is exact, but only while the SCHEDULE is unchanged. Alter the
    corpus, the batch math or the epoch count and the checkpoint's "step 146"
    now denotes a different fraction of training: the cosine LR restarts at the
    wrong point on the curve, and transformers warns about none of it. That is
    this project's recurring failure shape - a quantity nothing reads. So the
    step total these arguments imply is compared against the one the checkpoint
    was written under, and a disagreement stops the run.
    """
    import json
    import math

    if args.resume is None:
        return None
    if args.resume == "auto":
        from transformers.trainer_utils import get_last_checkpoint
        ckpt = get_last_checkpoint(str(args.output_dir))
        if ckpt is None:
            raise SystemExit(f"--resume: no checkpoint-* under {args.output_dir}")
    else:
        ckpt = str(args.resume)
    state = Path(ckpt) / "trainer_state.json"
    if not state.exists():
        raise SystemExit(f"--resume: {ckpt} has no trainer_state.json — "
                         "it is not a resumable checkpoint")
    st = json.loads(state.read_text())
    per_epoch = math.ceil(n_examples / (args.batch_size * args.grad_accum))
    want = math.ceil(per_epoch * args.epochs)
    if st.get("max_steps") and st["max_steps"] != want:
        raise SystemExit(
            f"--resume: {ckpt} was written for a {st['max_steps']}-step run, but "
            f"these arguments imply {want} ({n_examples} examples, batch "
            f"{args.batch_size}x{args.grad_accum}, {args.epochs} epochs). The LR "
            "schedule would not line up. Match the original run, or start fresh.")
    done, tot = st.get("global_step"), st.get("max_steps")
    ep = st.get("epoch")
    print(f"resuming {ckpt}: step {done}/{tot}"
          + (f", epoch {ep:.2f}" if isinstance(ep, (int, float)) else ""))
    # Missing state does not stop the run - it restarts that one piece cold, and
    # you want to know which piece rather than find out from the loss curve.
    for f in ("optimizer.pt", "scheduler.pt", "rng_state.pth"):
        if not (Path(ckpt) / f).exists():
            print(f"  WARNING: no {f} in the checkpoint — that state restarts cold")
    return ckpt


def verdict_token_ids(tokenizer) -> set[int]:
    """Token ids that decode to exactly `true` or `false`.

    Derived from the tokenizer rather than hardcoded: the literal may carry a
    leading space depending on what precedes it, and a wrong id here would fail
    silently as "no verdict token found" on every row.
    """
    ids: set[int] = set()
    for lit in ("true", "false"):
        for ctx in (lit, f" {lit}", f'"defect_found": {lit},',
                    f'{{"defect_found": {lit}, "confidence": 0.7}}'):
            for tid in tokenizer(ctx, add_special_tokens=False)["input_ids"]:
                if tokenizer.decode([tid]).strip() == lit:
                    ids.add(tid)
    return ids


def _first_verdict_pos(shift_labels, verdict_ids):
    """Index of the verdict token per row, and which rows have one.

    `defect_found` is the first key of every target in this corpus (checked over
    all 1164) and no `true`/`false` precedes it, so the FIRST supervised token
    matching the literal is the verdict. Prompt tokens are already -100, so a
    `true` in the diff cannot be picked up here.
    """
    import torch
    hit = torch.isin(shift_labels, verdict_ids.to(shift_labels.device))
    hit &= shift_labels != -100
    has = hit.any(dim=1)
    pos = torch.argmax(hit.int(), dim=1)
    return pos, has


class VerdictWeightedSFTTrainer:
    """Mixin adding an auxiliary CE on the verdict token. See --verdict-weight.

    Rows where the verdict token cannot be located are counted and reported, not
    skipped quietly: this project's recurring failure is a measurement that
    silently reads nothing, and a weight applied to no token would look exactly
    like a weight that did not work.
    """

    def __init__(self, *a, verdict_ids=None, verdict_weight=0.0, **kw):
        super().__init__(*a, **kw)
        import torch
        self._verdict_ids = torch.tensor(sorted(verdict_ids or []), dtype=torch.long)
        self._verdict_weight = float(verdict_weight)
        self.verdict_found = 0
        self.verdict_missing = 0

    def compute_loss(self, model, inputs, return_outputs=False,
                     num_items_in_batch=None):
        import torch
        from torch.nn import functional as F

        labels = inputs.get("labels")
        want = bool(self._verdict_weight) and labels is not None

        # TRL's default `loss_type="chunked_nll"` never materialises full logits
        # -- that is how a 2048-token sequence fits beside the model on a 6GB
        # card -- so `outputs.logits` comes back None. Take the one hidden state
        # the verdict term needs by hook, then project a single position through
        # lm_head: (rows x hidden) @ head, where full logits would be
        # (batch x seq x 151k).
        cap = _LastHidden(model) if want else None
        if want and cap.mod is None:
            inputs["output_hidden_states"] = True     # no norm found: fall back

        if cap is not None:
            with cap:
                loss, outputs = super().compute_loss(
                    model, inputs, return_outputs=True,
                    num_items_in_batch=num_items_in_batch)
        else:
            loss, outputs = super().compute_loss(
                model, inputs, return_outputs=True,
                num_items_in_batch=num_items_in_batch)

        if want:
            shift_labels = labels[:, 1:]
            pos, has = _first_verdict_pos(shift_labels, self._verdict_ids)
            self.verdict_found += int(has.sum())
            self.verdict_missing += int((~has).sum())
            if has.any():
                rows = torch.nonzero(has, as_tuple=True)[0]
                sel = pos[rows]
                targets = shift_labels[rows, sel]
                # hidden state at index i predicts token i+1, which is exactly
                # the indexing shift_labels already uses.
                h = cap.h if cap is not None else None
                if h is None:
                    hs = getattr(outputs, "hidden_states", None)
                    h = hs[-1] if hs is not None else None
                if h is None:
                    raise RuntimeError("--verdict-weight could not reach a "
                                       "hidden state on this loss path")
                head = model.get_output_embeddings()
                gathered = head(h[rows, sel, :].to(head.weight.dtype))
                aux = F.cross_entropy(gathered.float(), targets)
                loss = loss + self._verdict_weight * aux

        return (loss, outputs) if return_outputs else loss


class _LastHidden:
    """Capture the final hidden state with a hook, not `output_hidden_states`.

    `output_hidden_states=True` returns EVERY layer -- 36 x 2048 x 2048 in fp16
    is ~300MB per forward, on a card whose training peak was already 5318 of
    6144 MiB. That is what OOM'd the first eval, and it would have taken the
    real run down hours in. The final RMSNorm's output is the single tensor the
    verdict term needs, and a hook keeps just that one.
    """

    def __init__(self, model):
        self.h = self.handle = None
        try:
            self.mod = getattr(model.get_decoder(), "norm", None)
        except Exception:
            self.mod = None

    def __enter__(self):
        if self.mod is not None:
            self.handle = self.mod.register_forward_hook(
                lambda m, i, o: setattr(self, "h", o))
        return self

    def __exit__(self, *a):
        if self.handle is not None:
            self.handle.remove()
        return False


def verdict_eval(trainer, tokenizer, verdict_ids, dataloader) -> dict:
    """Teacher-forced verdict accuracy on the held-out set.

    Reads the model's prediction AT the verdict position only. The prefix up to
    that token is fixed by the output format -- every answer opens
    `{"defect_found": ` -- so teacher forcing there is not the crutch it would be
    deeper into the sentence, and it costs one forward pass instead of a full
    decode.

    Reported two ways because they fail differently: `constrained` scores the
    argmax restricted to {true, false}, which is the decision itself; `top1`
    scores the unrestricted argmax, which also catches a model that has stopped
    emitting the schema at all.
    """
    import torch

    model = trainer.model
    was_training = model.training
    model.eval()
    ids = torch.tensor(sorted(verdict_ids), dtype=torch.long)
    true_ids = {i for i in verdict_ids if tokenizer.decode([i]).strip() == "true"}
    tp = fn = tn = fp = top1 = seen = 0
    # Training fragmentation is what left 5.25 MiB free when this first ran.
    torch.cuda.empty_cache()
    with torch.no_grad():
        for batch in dataloader:
            batch = {k: v.to(model.device) for k, v in batch.items()
                     if isinstance(v, torch.Tensor)}
            labels = batch.get("labels")
            if labels is None:
                continue
            fwd = {k: v for k, v in batch.items() if k != "labels"}
            cap = _LastHidden(model)
            with cap:
                out = model(**fwd, use_cache=False)
            shift_labels = labels[:, 1:]
            pos, has = _first_verdict_pos(shift_labels, ids)
            if not has.any():
                continue
            rows = torch.nonzero(has, as_tuple=True)[0]
            sel = pos[rows]
            gold = shift_labels[rows, sel]
            h = cap.h
            if h is None:
                lg = getattr(out, "logits", None)
                if lg is None:
                    continue
                got = lg[:, :-1, :][rows, sel, :]
            else:
                head = model.get_output_embeddings()
                got = head(h[rows, sel, :].to(head.weight.dtype))
            got = got.float()
            top1 += int((got.argmax(-1) == gold).sum())
            cand = ids.to(got.device)
            pick = cand[got[:, cand].argmax(-1)]
            for g, pk in zip(gold.tolist(), pick.tolist()):
                gt, pt = g in true_ids, pk in true_ids
                seen += 1
                if gt and pt: tp += 1
                elif gt and not pt: fn += 1
                elif not gt and pt: fp += 1
                else: tn += 1
            del out, h, got
    torch.cuda.empty_cache()
    if was_training:
        model.train()
    pos_n = tp + fn
    return {"verdict_recall": tp / pos_n if pos_n else float("nan"),
            "verdict_specificity": tn / (tn + fp) if (tn + fp) else float("nan"),
            "verdict_top1_acc": top1 / seen if seen else float("nan"),
            "verdict_positives": pos_n, "verdict_seen": seen}


def main(argv=None) -> None:
    # `logging_steps` below emits the loss on schedule, but transformers'
    # ProgressCallback writes it with `tqdm.write`, i.e. to stdout, while the
    # progress bar goes to stderr. Under `run_v4.sh` stdout is a file, so it is
    # block-buffered and the loss sits in an 8 KB buffer until the process
    # exits: a 7-hour run shows a moving bar and no loss at all (30 Aug).
    # stderr is line-buffered either way, which is why the bar looked fine.
    sys.stdout.reconfigure(line_buffering=True)

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

    eval_ds = None
    if args.eval_dataset:
        if not args.eval_dataset.exists():
            raise SystemExit(f"--eval-dataset {args.eval_dataset} not found — "
                             f"build it with build_repair_sft.py --holdout")
        eval_ds = load_dataset("json", data_files=str(args.eval_dataset),
                               split="train")
        if args.eval_max and args.eval_max < len(eval_ds):
            # Take a SHUFFLED slice, not the head. The generators write holdout
            # rows grouped by family, so `range(n)` reads one family off the top:
            # the v4 cross holdout's first 40 rows were 39x f_range_end and one
            # other, which turned a six-family generalisation check into a
            # single-family one. The seed is fixed so the slice is identical
            # across steps and across runs, which is what makes readings
            # comparable at all.
            eval_ds = eval_ds.shuffle(seed=1234).select(range(args.eval_max))
        # `label` is the v1/v2 encoding. The exec corpus has no `label` -- its
        # verdict is `differs`, the first boolean of the target -- and counting
        # 0 positives here aborted the run on a corpus whose holdout is 46%
        # positive. Read the positive class the same way verdict_eval scores it:
        # the first `true`/`false` literal in the supervised target. Checked
        # over all 1404 exec rows that no other field carries one.
        def _is_pos(r) -> bool:
            if r.get("label") is not None:
                return r["label"] == 1
            msgs = r.get("messages") or []
            tgt = msgs[-1].get("content", "") if msgs else ""
            i_t, i_f = tgt.find("true"), tgt.find("false")
            return i_t != -1 and (i_f == -1 or i_t < i_f)

        n_pos = sum(1 for r in eval_ds if _is_pos(r))
        print(f"{len(eval_ds)} held-out examples from {args.eval_dataset} "
              f"({n_pos} defective)")
        if n_pos == 0:
            raise SystemExit("held-out slice has no defective examples — recall "
                             "would be undefined, which is the whole metric")

    vids = verdict_token_ids(tokenizer)
    weighting = bool(args.verdict_weight) or bool(args.verdict_check)
    if weighting:
        if not vids:
            raise SystemExit(
                "--verdict-weight: no token decodes to `true`/`false` under this "
                "tokenizer, so the weight would apply to nothing")
        shown = ", ".join(f"{i}={tokenizer.decode([i])!r}" for i in sorted(vids))
        print(f"verdict tokens: {shown}")
        print(f"verdict weight: {args.verdict_weight}")

    # Composed rather than declared, so an unweighted run instantiates the exact
    # SFTTrainer it always did and this file stays a no-op at --verdict-weight 0.
    trainer_cls = (type("VerdictSFTTrainer", (VerdictWeightedSFTTrainer, SFTTrainer), {})
                   if weighting else SFTTrainer)
    extra = ({"verdict_ids": vids, "verdict_weight": args.verdict_weight}
             if weighting else {})

    trainer = trainer_cls(
        model=model,
        args=SFTConfig(
            output_dir=str(args.output_dir),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            # Defaults to 8, independent of the train batch size. At seq 2048
            # that is an 8x wider forward than training ever does, and it OOM'd
            # the holdout pass on a 6GB card while training state was still
            # resident. The eval pass has no reason to be wider than training.
            per_device_eval_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            # Paged states survive the VRAM spikes that otherwise OOM a small
            # card mid-step; 8-bit keeps the optimiser itself off the budget.
            optim="paged_adamw_8bit",
            learning_rate=args.lr,
            lr_scheduler_type="cosine",
            # transformers 5.x dropped warmup_ratio; steps is what remains.
            warmup_steps=args.warmup_steps,
            max_length=args.max_seq_length,
            logging_steps=5,
            save_strategy="epoch",
            **precision_flags(args.four_bit),
            report_to=[],
            seed=args.seed,
            # The dataset is already conversational: TRL applies the chat
            # template and masks everything but the assistant turn.
            assistant_only_loss=True,
        ),
        train_dataset=dataset,
        eval_dataset=eval_ds,
        processing_class=tokenizer,
        peft_config=lora_config(),
        **extra,
    )

    # Run OUR verdict pass, not the trainer's own eval loop: eval_strategy stays
    # off so the held-out set is forwarded once per epoch, not twice.
    if eval_ds is not None:
        from transformers import TrainerCallback

        class _VerdictEval(TrainerCallback):
            def on_step_end(self, cfg, state, control, **kw):
                if args.eval_steps and state.global_step % args.eval_steps == 0:
                    self._report(state)

            def on_epoch_end(self, cfg, state, control, **kw):
                self._report(state)

            def _report(self, state):
                m = verdict_eval(trainer, tokenizer, vids,
                                 trainer.get_eval_dataloader())
                print(f"\n[holdout @ step {state.global_step}, "
                      f"epoch {state.epoch:.2f}] "
                      f"recall {m['verdict_recall']:.3f} on {m['verdict_positives']} "
                      f"positives | specificity {m['verdict_specificity']:.3f} "
                      f"| top1 {m['verdict_top1_acc']:.3f} "
                      f"| n={m['verdict_seen']}")
                if m["verdict_positives"] and m["verdict_recall"] == 0.0:
                    print("   RECALL IS ZERO — the model is answering `false` to "
                          "every held-out positive. This is the epoch-1 failure "
                          "repeating; stop rather than spend the next epoch.")

        trainer.add_callback(_VerdictEval())

    if args.verdict_check:
        import torch
        seen = found = 0
        vt = torch.tensor(sorted(vids), dtype=torch.long)
        for n, batch in enumerate(trainer.get_train_dataloader()):
            if n >= args.verdict_check:
                break
            labels = batch["labels"]
            pos, has = _first_verdict_pos(labels[:, 1:], vt)
            seen += labels.size(0)
            found += int(has.sum())
            for r in range(labels.size(0)):
                if has[r]:
                    tid = int(labels[r, 1:][pos[r]])
                    ctx = labels[r, 1:][max(0, int(pos[r]) - 6):int(pos[r]) + 1]
                    ctx = [t for t in ctx.tolist() if t != -100]
                    print(f"  batch {n} row {r}: {tokenizer.decode(ctx)!r}"
                          f"  -> verdict {tokenizer.decode([tid])!r}")
                else:
                    print(f"  batch {n} row {r}: NO VERDICT TOKEN LOCATED")
        print(f"\nverdict located in {found}/{seen} examples over "
              f"{args.verdict_check} batches")
        if found != seen:
            raise SystemExit("not every example has a locatable verdict — fix "
                             "before spending a training run on this")
        print("ok: every example has one. safe to train with --verdict-weight.")
        return

    trainer.train(resume_from_checkpoint=resolve_resume(args, len(dataset)))

    # The counters exist so the weight cannot apply to nothing in silence -- the
    # failure this whole change is a response to was a number that read fine
    # while the thing it described never happened. `missing` above zero means
    # some fraction of the run trained with no verdict term at all.
    if weighting and args.verdict_weight:
        found = getattr(trainer, "verdict_found", 0)
        missing = getattr(trainer, "verdict_missing", 0)
        print(f"\nverdict token located in {found}/{found + missing} training rows")
        if missing:
            print(f"  WARNING: {missing} rows carried no verdict term "
                  f"({100 * missing / max(1, found + missing):.1f}% of the run)")

    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    print(f"\nSFT adapter -> {args.output_dir}")
    print("next:\n"
          "  python -m dpo_pipeline.build_dpo_data --mock\n"
          "  python -m fine_tuning.train_dpo")


if __name__ == "__main__":
    main()
