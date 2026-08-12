"""JIT risk classifier - LightGBM, CatBoost or XGBoost behind one interface.

The booster is a swap-in choice, so the claim "CatBoost beats XGBoost here" is
something you measure rather than assume:

    python -m ml_model.classifier --benchmark        # all three, same split
    python -m ml_model.classifier --booster catboost # train and save one

CatBoost is the default. ApacheJIT carries `project` as a genuine categorical
(15 Apache projects) and CatBoost handles it natively with ordered target
statistics; the others need it encoded away, which either leaks or discards it.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shap

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ARTIFACTS, RISK_MODEL_PATH
from ml_model.kamei_metrics import CommitFeatures, KAMEI_FEATURES

BOOSTERS = ("catboost", "lightgbm", "xgboost")
DEFAULT_MODEL_PATH = Path(RISK_MODEL_PATH)
RISK_BANDS = ((0.75, "HIGH"), (0.5, "MEDIUM"), (0.0, "LOW"))


def risk_band(score: float) -> str:
    return next(label for cutoff, label in RISK_BANDS if score >= cutoff)


@dataclass
class Contribution:
    feature: str
    value: float
    contribution: float

    def __str__(self) -> str:
        return f"{self.feature} = {self.value:g} ({self.contribution:+.2f})"


@dataclass
class RiskResult:
    score: float
    band: str
    top_contributions: list[Contribution]

    @property
    def drivers(self) -> list[Contribution]:
        return [c for c in self.top_contributions if c.contribution > 0]


def build(booster: str, seed: int = 0, scale_pos_weight: float = 1.0):
    """An untrained model of the requested kind, with sane defaults."""
    if booster == "lightgbm":
        import lightgbm as lgb

        return lgb.LGBMClassifier(
            n_estimators=600, learning_rate=0.05, num_leaves=63,
            min_child_samples=40, subsample=0.9, subsample_freq=1,
            colsample_bytree=0.9, reg_lambda=1.0,
            scale_pos_weight=scale_pos_weight, random_state=seed, verbose=-1,
        )
    if booster == "catboost":
        from catboost import CatBoostClassifier

        return CatBoostClassifier(
            iterations=600, learning_rate=0.05, depth=6, l2_leaf_reg=3.0,
            loss_function="Logloss", eval_metric="AUC",
            scale_pos_weight=scale_pos_weight, random_seed=seed, verbose=0,
            allow_writing_files=False,
        )
    if booster == "xgboost":
        import xgboost as xgb

        return xgb.XGBClassifier(
            n_estimators=600, max_depth=5, learning_rate=0.05,
            subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0,
            scale_pos_weight=scale_pos_weight, eval_metric="logloss",
            random_state=seed,
        )
    raise ValueError(f"unknown booster {booster!r}, expected one of {BOOSTERS}")


def train(X, y, booster: str = "catboost", path: Path = DEFAULT_MODEL_PATH,
          seed: int = 0, balance: bool = True) -> "RiskModel":
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y)
    # ApacheJIT is ~26% buggy; without this the model under-predicts the class
    # the whole tool exists to find.
    spw = float((y == 0).sum() / max((y == 1).sum(), 1)) if balance else 1.0
    model = build(booster, seed=seed, scale_pos_weight=spw)
    model.fit(X, y)
    return RiskModel(model, booster).save(path)


class RiskModel:
    def __init__(self, model, booster: str):
        self.model = model
        self.booster = booster
        self._explainer = None

    # --- persistence -------------------------------------------------------
    def save(self, path: Path = DEFAULT_MODEL_PATH) -> "RiskModel":
        import pickle

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump({"booster": self.booster, "model": self.model}, fh)
        return self

    @classmethod
    def load(cls, path: Path = DEFAULT_MODEL_PATH) -> "RiskModel":
        import pickle

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"no model at {path} — train one:\n"
                f"  python -m ml_model.apachejit --csv data/apachejit_total.csv"
            )
        with open(path, "rb") as fh:
            blob = pickle.load(fh)
        return cls(blob["model"], blob["booster"])

    # --- inference ---------------------------------------------------------
    def predict_proba(self, X) -> np.ndarray:
        return self.model.predict_proba(np.asarray(X, dtype=np.float64))[:, 1]

    def score(self, commit: CommitFeatures, top_k: int = 5) -> RiskResult:
        row = np.asarray([commit.vector()], dtype=np.float64)
        prob = float(self.predict_proba(row)[0])

        if self._explainer is None:
            self._explainer = shap.TreeExplainer(self.model)
        values = np.asarray(self._explainer.shap_values(row))
        if values.ndim == 3:  # some versions return (n, features, classes)
            values = values[..., -1]
        values = values[0]

        order = np.argsort(-np.abs(values))[:top_k]
        return RiskResult(
            score=prob,
            band=risk_band(prob),
            top_contributions=[
                Contribution(KAMEI_FEATURES[i], row[0, i], float(values[i]))
                for i in order
            ],
        )


def benchmark(csv_path: Path, seed: int = 0, train_frac: float = 0.8) -> dict:
    """Train every booster on the identical chronological split and compare."""
    from sklearn.metrics import (average_precision_score, brier_score_loss,
                                 roc_auc_score)

    from ml_model.apachejit import load, time_split
    from ml_model.effort_metrics import effort_aware

    X, y, when = load(csv_path)
    (Xtr, ytr), (Xte, yte), cut = time_split(X, y, when, train_frac)
    la = Xte[:, KAMEI_FEATURES.index("la")]
    ld = Xte[:, KAMEI_FEATURES.index("ld")]
    effort = la + ld

    import datetime as dt
    print(f"{len(y)} commits, {y.mean():.1%} buggy — train {len(ytr)}, "
          f"test {len(yte)}, split at {dt.date.fromtimestamp(cut)}\n")

    results = {}
    for name in BOOSTERS:
        import time
        started = time.time()
        model = train(Xtr, ytr, booster=name, path=ARTIFACTS / f"bench_{name}.model",
                      seed=seed)
        p = model.predict_proba(Xte)
        results[name] = {
            "auc": roc_auc_score(yte, p),
            "pr_auc": average_precision_score(yte, p),
            "brier": brier_score_loss(yte, p),
            "fit_s": time.time() - started,
            **effort_aware(yte, p, effort),
        }
        r = results[name]
        print(f"{name:9s} AUC={r['auc']:.4f}  PR-AUC={r['pr_auc']:.4f}  "
              f"Brier={r['brier']:.4f}  Popt={r['popt']:.4f}  "
              f"PofB20={r['pofb20']:.4f}  IFA={r['ifa']:<3d} ({r['fit_s']:.0f}s)")

    best = max(results, key=lambda k: results[k]["auc"])
    print(f"\nbest AUC: {best}")
    best_popt = max(results, key=lambda k: results[k]["popt"])
    print(f"best Popt (effort-aware): {best_popt}")
    return results


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path,
                    default=Path(__file__).resolve().parent.parent / "data" / "apachejit_total.csv")
    ap.add_argument("--booster", choices=BOOSTERS, default="catboost")
    ap.add_argument("--benchmark", action="store_true", help="compare all three")
    ap.add_argument("--out", type=Path, default=DEFAULT_MODEL_PATH)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    if not args.csv.exists():
        raise SystemExit(f"{args.csv} not found — download ApacheJIT first")

    if args.benchmark:
        benchmark(args.csv, seed=args.seed)
        return

    from ml_model.apachejit import load, time_split

    X, y, when = load(args.csv)
    (Xtr, ytr), _, _ = time_split(X, y, when)
    train(Xtr, ytr, booster=args.booster, path=args.out, seed=args.seed)
    print(f"{args.booster} model -> {args.out}")


if __name__ == "__main__":
    main()
