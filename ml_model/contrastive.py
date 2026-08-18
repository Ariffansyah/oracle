"""Contrastive diff encoder: our own code representation for Stage 1.

Pretrains a small transformer encoder from scratch on fix pairs:
    positive = (code_before, code_after) of one file_change — the same change
               in its buggy and fixed versions
    negatives = every other pair in the batch (InfoNCE)

No pretrained model, no tree classifier downstream: the encoder and its
tokenizer are trained here, and detection uses a neural head on the pooled
embeddings. The training signal (fix pairs) is the part that is new.

    python -m ml_model.contrastive --epochs 20 --batch 128
    python -m ml_model.contrastive --resume artifacts/contrastive_encoder.pt
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

syspath = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(syspath))

from config import ROOT
from tokenizers import Tokenizer
from tokenizers.models import BPE
from tokenizers.pre_tokenizers import ByteLevel
from tokenizers.trainers import BpeTrainer

PAIRS = ROOT / "data" / "contrastive_pairs.jsonl"
TOKENIZER_PATH = ROOT / "artifacts" / "code_bpe.json"
CHECKPOINT = ROOT / "artifacts" / "contrastive_encoder.pt"
VOCAB = 32_000
MAX_LEN = 512


# ---------------------------------------------------------------- tokenizer

def train_tokenizer(out: Path = TOKENIZER_PATH) -> Tokenizer:
    tok = Tokenizer(BPE(unk_token="[UNK]"))
    tok.pre_tokenizer = ByteLevel(add_prefix_space=False)
    trainer = BpeTrainer(vocab_size=VOCAB, special_tokens=["[PAD]", "[UNK]"])
    tok.train([str(PAIRS)], trainer)
    tok.enable_truncation(max_length=MAX_LEN)
    tok.enable_padding(pad_id=tok.token_to_id("[PAD]"), pad_token="[PAD]")
    out.parent.mkdir(parents=True, exist_ok=True)
    tok.save(str(out))
    return tok


# ---------------------------------------------------------------- model

class DiffEncoder(nn.Module):
    """Tiny BERT-style encoder over code lines. Mean pooling: a diff of any
    length becomes one vector, which is what the gate head wants."""

    def __init__(self, vocab: int = VOCAB, d_model: int = 384,
                 layers: int = 4, heads: int = 6, ff: int = 1024):
        super().__init__()
        self.emb = nn.Embedding(vocab, d_model, padding_idx=0)
        self.pos = nn.Embedding(MAX_LEN, d_model)
        self.norm = nn.LayerNorm(d_model)
        block = nn.TransformerEncoderLayer(
            d_model, heads, ff, batch_first=True, dropout=0.1)
        self.enc = nn.TransformerEncoder(block, layers)
        self.pool = nn.Linear(d_model, d_model)  # projection head

    def forward(self, ids: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        # ids (B, L) with [PAD]=0; mask = not-pad
        x = self.emb(ids) + self.pos(torch.arange(ids.size(1), device=ids.device))
        x = self.enc(x, src_key_padding_mask=~mask)
        x = self.norm(x.mean(dim=1))
        return F.normalize(self.pool(x), dim=-1)


def info_nce(a: torch.Tensor, b: torch.Tensor, tau: float = 0.1) -> torch.Tensor:
    """Symmetric InfoNCE over the batch: a_i ~ b_i, all other b's are negatives."""
    logits = (a @ b.T) / tau
    labels = torch.arange(a.size(0), device=a.device)
    return (F.cross_entropy(logits, labels) +
            F.cross_entropy(logits.T, labels)) / 2


# ---------------------------------------------------------------- data

def load_pairs(path: Path) -> list[dict]:
    pairs = []
    with open(path) as fh:
        for line in fh:
            if line.strip():
                pairs.append(json.loads(line))
    return pairs


def batches(pairs: list[dict], tok: Tokenizer, batch: int, shuffle: bool):
    idx = list(range(len(pairs)))
    if shuffle:
        import random
        random.shuffle(idx)
    for start in range(0, len(idx), batch):
        chunk = [pairs[i] for i in idx[start:start + batch]]
        enc = tok.encode_batch([p["before"] for p in chunk] +
                               [p["after"] for p in chunk])
        ids = torch.tensor([e.ids for e in enc], dtype=torch.long)
        mask = ids != 0
        yield ids[:len(chunk)], mask[:len(chunk)], \
              ids[len(chunk):], mask[len(chunk):]


# ---------------------------------------------------------------- train

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--device", default="auto",
                    help="auto|cpu|cuda — box has the GPU, laptop has 12 cores")
    ap.add_argument("--resume", type=Path, default=None)
    args = ap.parse_args(argv)

    device = (torch.device("cuda" if torch.cuda.is_available() else "cpu")
              if args.device == "auto" else torch.device(args.device))
    tok = (Tokenizer.from_file(str(TOKENIZER_PATH))
           if TOKENIZER_PATH.exists() else train_tokenizer())
    pairs = load_pairs(PAIRS)
    print(f"{len(pairs)} pairs, device {device}, vocab {tok.get_vocab_size()}")

    model = DiffEncoder(vocab=tok.get_vocab_size()).to(device)
    start_epoch = 0
    if args.resume and args.resume.exists():
        model.load_state_dict(torch.load(args.resume, map_location=device))
        start_epoch = int(args.resume.stem.split("_")[-1])
        print(f"resumed at epoch {start_epoch}")
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(
        opt, T_max=args.epochs)

    t0 = time.time()
    for epoch in range(start_epoch, args.epochs):
        model.train()
        total, steps = 0.0, 0
        for b, m_b, a, m_a in batches(pairs, tok, args.batch, shuffle=True):
            b, m_b, a, m_a = b.to(device), m_b.to(device), a.to(device), m_a.to(device)
            opt.zero_grad()
            loss = info_nce(model(b, m_b), model(a, m_a))
            loss.backward()
            opt.step()
            total += loss.item()
            steps += 1
            if steps % 25 == 0:
                print(f"  epoch {epoch} step {steps} loss {loss.item():.3f}",
                      flush=True)
        sched.step()
        ckpt = CHECKPOINT.with_name(f"contrastive_encoder_e{epoch}.pt")
        torch.save(model.state_dict(), ckpt)
        torch.save(model.state_dict(), CHECKPOINT)
        print(f"epoch {epoch}: loss {total / steps:.3f}  "
              f"{steps * args.batch / (time.time() - t0):.0f} pairs/s")
        t0 = time.time()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
