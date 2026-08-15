"""Stage 1: the gatekeeper. Cheap, high-recall, and it decides who sees the LLM.

    diff ──► GraphCodeBERT embedding (768) ──┐
                                             ├─► LightGBM / MLP ──► P(defect)
    process metrics (14 Kamei numbers) ──────┘

Design constraint, and the reason the threshold is not 0.5: the two errors are
not symmetric. A false negative is a defect that no part of ORACLE ever looks
at. A false positive costs one LLM call. So the gate is tuned for recall - it
should wave through everything it is not confident about, and only silence the
commits it is sure are safe.

`train_gate.py` picks the threshold that hits `GATE_TARGET_RECALL` on held-out
data, and reports what fraction of LLM calls that saves.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (GATE_HEAD, GATE_MODEL_PATH, GATE_TARGET_RECALL,
                    GATE_THRESHOLD)
from corpus.kamei_metrics import KAMEI_FEATURES


@dataclass
class GateDecision:
    """What Stage 1 concluded, and whether Stage 2 should run."""

    score: float
    threshold: float
    should_review: bool
    reason: str
    top_metrics: list[tuple[str, float]] = field(default_factory=list)

    @property
    def band(self) -> str:
        if self.score != self.score:      # NaN: unscored
            return "UNSCORED"
        if self.score >= 0.75:
            return "HIGH"
        return "MEDIUM" if self.score >= self.threshold else "LOW"


def build_head(kind: str = GATE_HEAD, seed: int = 0, scale_pos_weight: float = 1.0):
    """The classifier over [embedding | metrics]."""
    if kind == "lightgbm":
        import lightgbm as lgb

        return lgb.LGBMClassifier(
            n_estimators=400, learning_rate=0.05, num_leaves=31,
            min_child_samples=20, subsample=0.9, subsample_freq=1,
            colsample_bytree=0.6,   # 768 embedding dims: sample them
            reg_lambda=1.0, scale_pos_weight=scale_pos_weight,
            random_state=seed, verbose=-1,
        )
    if kind == "mlp":
        from sklearn.neural_network import MLPClassifier

        return MLPClassifier(
            hidden_layer_sizes=(256, 64), activation="relu",
            alpha=1e-4, batch_size=64, learning_rate_init=1e-3,
            max_iter=200, early_stopping=True, n_iter_no_change=10,
            random_state=seed,
        )
    raise ValueError(f"unknown gate head {kind!r}; use lightgbm or mlp")


def tune_threshold(y_true, scores, target_recall: float = GATE_TARGET_RECALL) -> float:
    """Lowest threshold that still catches `target_recall` of real defects.

    Sweeping is exact and cheap here, and it makes the recall guarantee explicit
    rather than a hope about a default of 0.5.
    """
    y = np.asarray(y_true).astype(bool)
    s = np.asarray(scores, dtype=float)
    if not y.any():
        return 0.5
    positives = np.sort(s[y])
    # The threshold that keeps exactly `target_recall` of positives above it.
    idx = int((1.0 - target_recall) * len(positives))
    idx = min(max(idx, 0), len(positives) - 1)
    return float(positives[idx])


class Gatekeeper:
    """Trained gate: scores a commit and decides whether Stage 2 runs."""

    def __init__(self, head, threshold: float = GATE_THRESHOLD,
                 encoder=None, use_embeddings: bool = True,
                 n_metrics: int = 0):
        self.head = head
        self.threshold = threshold
        self.use_embeddings = use_embeddings
        # A model trained on [embedding | metrics] must always be fed both, or
        # the columns shift and the score is meaningless. When the metrics are
        # unavailable at inference (a patch file, a repo without history) the
        # slots are zero-filled rather than dropped.
        self.n_metrics = n_metrics
        self._encoder = encoder

    # --- features ----------------------------------------------------------
    @property
    def encoder(self):
        if self._encoder is None and self.use_embeddings:
            from ml_model.encoder import DiffEncoder

            self._encoder = DiffEncoder()
        return self._encoder

    def features(self, diffs: list[str], metrics: np.ndarray | None = None,
                 progress=None) -> np.ndarray:
        """[embedding | metrics] for a batch of commits."""
        parts = []
        if self.use_embeddings:
            parts.append(self.encoder.encode(diffs, progress=progress))
        if metrics is not None:
            parts.append(np.asarray(metrics, dtype=np.float32))
        elif self.n_metrics:
            parts.append(np.zeros((len(diffs), self.n_metrics), dtype=np.float32))
        if not parts:
            raise ValueError("gate needs embeddings, metrics, or both")
        return np.hstack(parts)

    # --- inference ---------------------------------------------------------
    def score(self, diff: str, metrics: np.ndarray | None = None) -> float:
        X = self.features([diff], None if metrics is None else metrics[None, :])
        return float(self.head.predict_proba(X)[0, 1])

    def decide(self, diff: str, metrics: np.ndarray | None = None,
               force: bool = False) -> GateDecision:
        # An empty diff is not a safe diff - it is a diff we failed to read, and
        # scoring it produces a confident number about nothing.
        if not diff or not diff.strip():
            return GateDecision(float("nan"), self.threshold, True,
                                "empty diff — nothing to score, reviewing anyway",
                                [])
        score = self.score(diff, metrics)
        top = []
        if metrics is not None:
            order = np.argsort(-np.abs(np.asarray(metrics, dtype=float)))[:3]
            top = [(KAMEI_FEATURES[i], float(metrics[i])) for i in order]

        if force:
            return GateDecision(score, self.threshold, True, "forced", top)
        if score >= self.threshold:
            return GateDecision(score, self.threshold, True,
                                f"risk {score:.1%} at or above the "
                                f"{self.threshold:.1%} gate", top)
        return GateDecision(score, self.threshold, False,
                            f"risk {score:.1%} below the {self.threshold:.1%} "
                            f"gate — no LLM call made", top)

    # --- persistence -------------------------------------------------------
    def save(self, path: Path = GATE_MODEL_PATH) -> Path:
        import joblib

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"head": self.head, "threshold": self.threshold,
                     "use_embeddings": self.use_embeddings,
                     "n_metrics": self.n_metrics}, path)
        return path

    @classmethod
    def load(cls, path: Path = GATE_MODEL_PATH) -> "Gatekeeper":
        import joblib

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"no gate at {path} — train one:\n"
                f"  python -m ml_model.train_gate --jsonl data/apachejit_commits.jsonl"
            )
        blob = joblib.load(path)
        return cls(blob["head"], blob["threshold"],
                   use_embeddings=blob.get("use_embeddings", True),
                   n_metrics=blob.get("n_metrics", 0))


if __name__ == "__main__":
    # Threshold tuning is the part that must be right: it is what guarantees the
    # gate does not silently drop defects.
    y = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
    s = np.array([0.9, 0.7, 0.4, 0.2, 0.3, 0.1, 0.05, 0.02, 0.01, 0.0])

    t = tune_threshold(y, s, target_recall=1.0)
    assert (s[y.astype(bool)] >= t).all(), "100% recall must keep every positive"

    t75 = tune_threshold(y, s, target_recall=0.75)
    recall = float((s[y.astype(bool)] >= t75).mean())
    assert recall >= 0.75, recall
    assert t75 > t, "a lower recall target should allow a higher threshold"

    # A gate that saves nothing is useless; one that saves everything is a liar.
    saved = float((s < t).mean())
    assert 0.0 <= saved < 1.0

    # Missing metrics at inference must zero-fill, never change the width.
    g = Gatekeeper(None, use_embeddings=False, n_metrics=14)
    assert g.features(["d"], None).shape == (1, 14), "metric slots must be kept"

    # An unreadable diff must not be scored as if it were safe.
    d = g.decide("   ")
    assert d.should_review and d.band == "UNSCORED", d
    assert "empty diff" in d.reason
    print(f"threshold tuning ok: recall 1.0 -> t={t:.3f} (skips {saved:.0%} of commits), "
          f"recall 0.75 -> t={t75:.3f}")
