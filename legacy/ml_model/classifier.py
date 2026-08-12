"""XGBoost JIT defect-risk classifier with SHAP attribution.

`train()` fits on a labelled feature table; with no dataset available it fits on
a synthetic one so the pipeline is runnable out of the box.  `RiskModel.score()`
returns the defect probability plus the top SHAP contributions behind it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shap
import xgboost as xgb

from config import KAMEI_FEATURES, MODEL_PATH, SHAP_TOP_K, risk_band
from ml_model.kamei_metrics import CommitFeatures

# Sign of each feature's *expected* correlation with defect risk, used only to
# generate the synthetic training set (larger/more scattered changes by
# inexperienced authors are riskier; experience lowers risk).
_RISK_SIGN = {
    "ns": +1, "nd": +1, "nf": +1, "entropy": +1, "la": +1, "ld": +1, "lt": +1,
    "fix": +1, "ndev": +1, "age": -1, "nuc": +1, "exp": -1, "rexp": -1, "sexp": -1,
}


@dataclass
class Contribution:
    feature: str
    value: float
    contribution: float  # SHAP value in log-odds space

    def __str__(self) -> str:
        return f"{self.feature} = {self.value:g} ({self.contribution:+.2f})"


@dataclass
class RiskResult:
    score: float
    band: str
    top_contributions: list[Contribution]
    base_value: float

    @property
    def drivers(self) -> list[Contribution]:
        """Contributions that push the prediction *towards* defective."""
        return [c for c in self.top_contributions if c.contribution > 0]


def synthetic_dataset(n: int = 4000, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Plausible (X, y) for offline smoke tests only.

    The shipped model is trained on ApacheJIT — see `ml_model/apachejit.py`.
    This exists so `train()` works with no corpus present; its labels come from
    the hand-written `_RISK_SIGN` below, so anything it predicts is an assertion
    of mine, not an empirical result.
    """
    rng = np.random.default_rng(seed)
    X = np.column_stack([
        rng.integers(1, 5, n),                       # ns
        rng.integers(1, 10, n),                      # nd
        rng.integers(1, 20, n),                      # nf
        rng.random(n),                               # entropy
        rng.lognormal(3.5, 1.2, n),                  # la
        rng.lognormal(3.0, 1.2, n),                  # ld
        rng.lognormal(6.0, 1.0, n),                  # lt
        rng.random(n) < 0.35,                        # fix
        rng.integers(1, 12, n),                      # ndev
        rng.exponential(90, n),                      # age
        rng.integers(1, 100, n),                     # nuc
        rng.lognormal(4.0, 1.5, n),                  # exp
        rng.exponential(20, n),                      # rexp
        rng.lognormal(3.0, 1.5, n),                  # sexp
    ]).astype(np.float64)

    z = np.zeros(n)
    for i, name in enumerate(KAMEI_FEATURES):
        col = X[:, i]
        col = np.log1p(col) if col.max() > 20 else col
        col = (col - col.mean()) / (col.std() or 1)
        z += _RISK_SIGN[name] * col
    z = z / np.sqrt(len(KAMEI_FEATURES)) * 2.2 - 0.6
    p = 1 / (1 + np.exp(-z))
    y = (rng.random(n) < p).astype(int)
    return X, y


def train(X=None, y=None, path: Path = MODEL_PATH, seed: int = 0) -> "RiskModel":
    """Fit the booster and persist it to ``path``."""
    if X is None or y is None:
        X, y = synthetic_dataset(seed=seed)
    booster = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        eval_metric="logloss",
        random_state=seed,
    )
    booster.fit(np.asarray(X, dtype=np.float64), np.asarray(y))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(path))
    return RiskModel(booster)


class RiskModel:
    """Loaded booster + SHAP explainer."""

    def __init__(self, booster: xgb.XGBClassifier):
        self.booster = booster
        self._explainer = shap.TreeExplainer(booster)

    @classmethod
    def load(cls, path: Path = MODEL_PATH, train_if_missing: bool = True) -> "RiskModel":
        if not Path(path).exists():
            if not train_if_missing:
                raise FileNotFoundError(f"no model at {path}; run `python main.py train`")
            return train(path=path)
        booster = xgb.XGBClassifier()
        booster.load_model(str(path))
        return cls(booster)

    def score(self, commit: CommitFeatures, top_k: int = SHAP_TOP_K) -> RiskResult:
        row = np.asarray([commit.vector()], dtype=np.float64)
        prob = float(self.booster.predict_proba(row)[0, 1])
        shap_values = np.asarray(self._explainer.shap_values(row))[0]
        order = np.argsort(-np.abs(shap_values))[:top_k]
        return RiskResult(
            score=prob,
            band=risk_band(prob),
            base_value=float(np.ravel(self._explainer.expected_value)[0]),
            top_contributions=[
                Contribution(KAMEI_FEATURES[i], row[0, i], float(shap_values[i]))
                for i in order
            ],
        )


if __name__ == "__main__":
    from ml_model.kamei_metrics import mock_commit

    model = train()
    risky = model.score(mock_commit(seed=1, risky=True))
    safe = model.score(mock_commit(seed=1, risky=False))
    assert 0.0 <= risky.score <= 1.0
    assert len(risky.top_contributions) == SHAP_TOP_K
    assert risky.score > safe.score, f"risky {risky.score} !> safe {safe.score}"
    print(f"risky={risky.score:.3f} ({risky.band})  safe={safe.score:.3f} ({safe.band})")
    print(" | ".join(str(c) for c in risky.top_contributions))
