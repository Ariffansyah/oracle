"""Stage 1a: semantic embeddings of a diff, from a pretrained code encoder.

GraphCodeBERT / CodeT5 read the diff itself, which is what separates this from
Kamei-style process metrics: `la = 412` is the same number whether the change is
a captcha guard or a rocket launch, and the encoder is not.

Only the encoder runs here - 125M parameters, a few milliseconds on CPU, tens of
microseconds on GPU. The classifier that consumes these vectors lives in
`gate.py`.

Embeddings are cached by content hash: the same diff is never encoded twice,
which matters when tuning the classifier over a corpus repeatedly.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (GATE_ENCODER, GATE_ENCODER_MAX_TOKENS, GATE_EMBED_CACHE)


class DiffEncoder:
    """Pooled sentence embedding of a diff. Loaded once, reused."""

    def __init__(self, model_name: str = GATE_ENCODER,
                 max_tokens: int = GATE_ENCODER_MAX_TOKENS,
                 cache_path: Path | None = GATE_EMBED_CACHE,
                 device: str | None = None):
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.cache_path = Path(cache_path) if cache_path else None
        self.device = device
        self._model = None
        self._tokenizer = None
        self._cache: dict[str, np.ndarray] = {}
        self._cache_dirty = False
        self._load_cache()

    # --- cache -------------------------------------------------------------
    def _load_cache(self) -> None:
        if self.cache_path and self.cache_path.exists():
            with np.load(self.cache_path) as z:
                self._cache = {k: z[k] for k in z.files}

    def save_cache(self) -> None:
        if self.cache_path and self._cache_dirty:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(self.cache_path, **self._cache)
            self._cache_dirty = False

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()

    # --- model -------------------------------------------------------------
    def _load(self):
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as e:
            raise RuntimeError(
                "the gatekeeper encoder needs torch + transformers:\n"
                "  pip install torch transformers"
            ) from e

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModel.from_pretrained(self.model_name)
        self._model.eval()
        if self.device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model.to(self.device)

    @property
    def dim(self) -> int:
        self._load()
        return int(self._model.config.hidden_size)

    # --- encoding ----------------------------------------------------------
    def encode(self, diffs: list[str], batch_size: int = 16,
               progress=None) -> np.ndarray:
        """(n, hidden_size) float32 embeddings, cached by content."""
        keys = [self._key(d) for d in diffs]
        missing = [i for i, k in enumerate(keys) if k not in self._cache]

        if missing:
            self._load()
            import torch

            for start in range(0, len(missing), batch_size):
                idx = missing[start:start + batch_size]
                batch = [diffs[i] for i in idx]
                enc = self._tokenizer(
                    batch, truncation=True, max_length=self.max_tokens,
                    padding=True, return_tensors="pt").to(self.device)
                with torch.inference_mode():
                    out = self._model(**enc).last_hidden_state
                # Mean pooling over real tokens only; padding would drag the
                # vector toward whatever the pad embedding happens to be.
                mask = enc["attention_mask"].unsqueeze(-1).float()
                pooled = (out * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
                pooled = pooled.float().cpu().numpy()
                for j, i in enumerate(idx):
                    self._cache[keys[i]] = pooled[j]
                self._cache_dirty = True
                if progress:
                    progress(min(start + batch_size, len(missing)), len(missing))

        return np.stack([self._cache[k] for k in keys]).astype(np.float32)


if __name__ == "__main__":
    enc = DiffEncoder(cache_path=None)
    diffs = [
        "diff --git a/a.py b/a.py\n@@ -1 +1 @@\n-if x > 0:\n+if x >= 0:\n",
        "diff --git a/b.py b/b.py\n@@ -1 +1 @@\n-out = []\n+result = []\n",
    ]
    try:
        vecs = enc.encode(diffs)
    except RuntimeError as e:
        print(f"skipped: {e}")
        raise SystemExit(0)

    assert vecs.shape == (2, enc.dim), vecs.shape
    assert vecs.dtype == np.float32
    # Caching must return the identical vector, not merely a close one.
    again = enc.encode([diffs[0]])
    assert np.array_equal(again[0], vecs[0]), "cache returned a different vector"
    # Two different diffs must not collapse to the same point.
    assert not np.allclose(vecs[0], vecs[1]), "encoder is not discriminating"
    print(f"encoder ok: {enc.model_name}, dim {enc.dim}, "
          f"cosine {float(vecs[0] @ vecs[1] / (np.linalg.norm(vecs[0]) * np.linalg.norm(vecs[1]))):.3f}")
