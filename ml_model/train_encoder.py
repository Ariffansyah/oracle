"""Stage 1, trained end to end: fine-tune the code encoder itself.

The frozen-embedding gate uses GraphCodeBERT as a fixed feature extractor - its
125M parameters never move, and a tree learns on top of whatever they happen to
produce. Those weights were trained for masked-language modelling, not for
"does this diff introduce a defect", so the representation is generic.

This trains them. The encoder, a classification head, and optionally a small
tower over the 14 process metrics are optimised together on the defect label.

    python -m ml_model.train_encoder --jsonl data/apachejit_commits.jsonl

125M parameters at 512 tokens fits a 6GB card comfortably. It also produces a
single artifact that does the whole of Stage 1 in one forward pass, which is
what makes the gate cheap at inference.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (ARTIFACTS, GATE_ENCODER, GATE_ENCODER_MAX_TOKENS,
                    GATE_TARGET_RECALL, ROOT)
from corpus.kamei_metrics import KAMEI_FEATURES

DEFAULT_OUT = ARTIFACTS / "gate-encoder"


def require_torch():
    import importlib.util as u

    missing = [m for m in ("torch", "transformers") if u.find_spec(m) is None]
    if missing:
        raise SystemExit(f"missing: {', '.join(missing)}\n"
                         f"  pip install torch transformers")
    import torch

    return torch


class FusionClassifier:
    """Encoder + metric tower + head, trained jointly.

    Built as a factory rather than a module subclass so torch is only imported
    when this actually runs - the rest of ORACLE stays importable without it.
    """

    @staticmethod
    def build(model_name: str, n_metrics: int, dropout: float = 0.1):
        torch = require_torch()
        import torch.nn as nn
        from transformers import AutoModel

        class Model(nn.Module):
            def __init__(self):
                super().__init__()
                self.encoder = AutoModel.from_pretrained(model_name)
                hidden = self.encoder.config.hidden_size
                self.n_metrics = n_metrics
                # A small tower keeps the 14 metrics from being drowned by 768
                # embedding dimensions when the two are concatenated.
                self.metric_tower = (
                    nn.Sequential(nn.Linear(n_metrics, 64), nn.GELU(),
                                  nn.LayerNorm(64))
                    if n_metrics else None)
                width = hidden + (64 if n_metrics else 0)
                self.head = nn.Sequential(
                    nn.Dropout(dropout), nn.Linear(width, 128), nn.GELU(),
                    nn.Dropout(dropout), nn.Linear(128, 1))

            def forward(self, input_ids, attention_mask, metrics=None):
                out = self.encoder(input_ids=input_ids,
                                   attention_mask=attention_mask).last_hidden_state
                mask = attention_mask.unsqueeze(-1).float()
                pooled = (out * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
                if self.metric_tower is not None and metrics is not None:
                    pooled = torch.cat([pooled, self.metric_tower(metrics)], dim=-1)
                return self.head(pooled).squeeze(-1)

        return Model()


def load_data(path: Path):
    from ml_model.train_gate import load_records, metrics_matrix

    rows = load_records(path)
    y = np.array([bool(r.get("buggy")) for r in rows], dtype=np.float32)
    diffs = [r["diff"] for r in rows]
    metrics = metrics_matrix(rows)
    if metrics is not None:
        # Log-scale then standardise: churn counts are heavy-tailed, and a raw
        # `la` of 4000 would dominate a 64-unit tower.
        metrics = np.log1p(np.clip(metrics, 0, None))
        mu, sd = metrics.mean(0), metrics.std(0)
        metrics = (metrics - mu) / np.where(sd < 1e-6, 1.0, sd)
        metrics = metrics.astype(np.float32)
    return rows, diffs, y, metrics


def evaluate(model, loader, device, target_recall: float) -> dict:
    import torch
    from sklearn.metrics import average_precision_score, roc_auc_score

    from ml_model.gate import tune_threshold

    model.eval()
    scores, labels = [], []
    with torch.inference_mode():
        for batch in loader:
            logits = model(batch["input_ids"].to(device),
                           batch["attention_mask"].to(device),
                           batch["metrics"].to(device)
                           if batch["metrics"] is not None else None)
            scores.append(torch.sigmoid(logits).float().cpu().numpy())
            labels.append(batch["labels"].numpy())
    p = np.concatenate(scores)
    y = np.concatenate(labels)
    t = tune_threshold(y, p, target_recall)
    reviewed = p >= t
    return {
        "auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "threshold": float(t),
        "recall": float((reviewed & y.astype(bool)).sum() / max(y.sum(), 1)),
        "saved": 1.0 - float(reviewed.mean()),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jsonl", type=Path,
                    default=ROOT / "data" / "apachejit_commits.jsonl")
    ap.add_argument("--encoder", default=GATE_ENCODER)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-5,
                    help="encoder LR; full fine-tuning wants a small one")
    ap.add_argument("--head-lr", type=float, default=1e-3,
                    help="the head starts random and can move much faster")
    ap.add_argument("--max-tokens", type=int, default=GATE_ENCODER_MAX_TOKENS)
    ap.add_argument("--train-frac", type=float, default=0.8)
    ap.add_argument("--target-recall", type=float, default=GATE_TARGET_RECALL)
    ap.add_argument("--no-metrics", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    torch = require_torch()
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoTokenizer

    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    rows, diffs, y, metrics = load_data(args.jsonl)
    if args.no_metrics:
        metrics = None
    cut = int(len(rows) * args.train_frac)
    print(f"{len(rows)} commits, {y.mean():.1%} buggy, "
          f"train {cut} / test {len(rows) - cut}, device {device}")

    tokenizer = AutoTokenizer.from_pretrained(args.encoder)

    class Commits(Dataset):
        def __init__(self, idx):
            self.idx = idx

        def __len__(self):
            return len(self.idx)

        def __getitem__(self, i):
            j = self.idx[i]
            enc = tokenizer(diffs[j], truncation=True, max_length=args.max_tokens,
                            padding="max_length", return_tensors="pt")
            item = {"input_ids": enc["input_ids"][0],
                    "attention_mask": enc["attention_mask"][0],
                    "labels": torch.tensor(y[j])}
            item["metrics"] = (torch.tensor(metrics[j]) if metrics is not None
                               else torch.zeros(0))
            return item

    def collate(batch):
        out = {k: torch.stack([b[k] for b in batch])
               for k in ("input_ids", "attention_mask", "labels")}
        out["metrics"] = (torch.stack([b["metrics"] for b in batch])
                          if metrics is not None else None)
        return out

    train_loader = DataLoader(Commits(list(range(cut))), batch_size=args.batch_size,
                              shuffle=True, collate_fn=collate)
    test_loader = DataLoader(Commits(list(range(cut, len(rows)))),
                             batch_size=args.batch_size, collate_fn=collate)

    n_metrics = 0 if metrics is None else metrics.shape[1]
    model = FusionClassifier.build(args.encoder, n_metrics).to(device)

    # Two learning rates: the pretrained encoder should drift, the fresh head
    # should sprint. One LR for both either wrecks the encoder or starves the head.
    head_params = [p for n, p in model.named_parameters() if not n.startswith("encoder.")]
    enc_params = [p for n, p in model.named_parameters() if n.startswith("encoder.")]
    optim = torch.optim.AdamW(
        [{"params": enc_params, "lr": args.lr},
         {"params": head_params, "lr": args.head_lr}], weight_decay=0.01)

    pos_weight = torch.tensor([(y[:cut] == 0).sum() / max((y[:cut] == 1).sum(), 1)],
                              device=device)
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    steps = max(1, len(train_loader) * args.epochs)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        optim, max_lr=[args.lr, args.head_lr], total_steps=steps, pct_start=0.1)
    scaler = torch.amp.GradScaler("cuda", enabled=(device == "cuda"))

    best = None
    for epoch in range(1, args.epochs + 1):
        model.train()
        total = 0.0
        for batch in train_loader:
            optim.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=(device == "cuda")):
                logits = model(batch["input_ids"].to(device),
                               batch["attention_mask"].to(device),
                               batch["metrics"].to(device)
                               if batch["metrics"] is not None else None)
                loss = loss_fn(logits.float(), batch["labels"].to(device))
            scaler.scale(loss).backward()
            scaler.unscale_(optim)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(optim)
            scaler.update()
            sched.step()
            total += float(loss)

        res = evaluate(model, test_loader, device, args.target_recall)
        print(f"epoch {epoch}  loss={total / max(len(train_loader), 1):.4f}  "
              f"AUC={res['auc']:.4f}  PR-AUC={res['pr_auc']:.4f}  "
              f"recall={res['recall']:.0%}  saved={res['saved']:.1%}")
        if best is None or res["auc"] > best["auc"]:
            best = res
            args.out.mkdir(parents=True, exist_ok=True)
            torch.save({"state_dict": model.state_dict(),
                        "encoder": args.encoder,
                        "n_metrics": n_metrics,
                        "max_tokens": args.max_tokens,
                        "threshold": res["threshold"],
                        "metrics_used": KAMEI_FEATURES if n_metrics else []},
                       args.out / "gate_encoder.pt")

    print(f"\nbest AUC={best['auc']:.4f} PR-AUC={best['pr_auc']:.4f} "
          f"at threshold {best['threshold']:.4f} "
          f"(recall {best['recall']:.0%}, saves {best['saved']:.1%})")
    print(f"model -> {args.out / 'gate_encoder.pt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
