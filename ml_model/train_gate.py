"""Train Stage 1 on real commits, and report what it actually buys.

    python -m ml_model.train_gate --jsonl data/apachejit_commits.jsonl

Reports the three numbers that decide whether the gate is worth having:

  recall        share of real defects that still reach the LLM. Below the
                target this gate is dangerous, not cheap.
  LLM calls     share of commits the gate silences. This is the saving.
  AUC / PR-AUC  ranking quality, comparable to the JIT literature.

`--ablate` trains three variants - metrics only, embeddings only, both - which
is the experiment that shows whether reading the code adds anything over the
process metrics that Kamei-style models have used since 2013.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import GATE_HEAD, GATE_MODEL_PATH, GATE_TARGET_RECALL, ROOT
from corpus.kamei_metrics import KAMEI_FEATURES
from ml_model.gate import Gatekeeper, build_head, tune_threshold


def load_records(path: Path) -> list[dict]:
    rows = [json.loads(l) for l in open(path) if l.strip()]
    rows = [r for r in rows if r.get("diff")]
    if not rows:
        raise SystemExit(f"{path} has no usable records")
    return rows


def metrics_matrix(rows: list[dict], csv_path: Path | None = None) -> np.ndarray | None:
    """The 14 Kamei numbers per commit.

    Fetched records carry a diff but not necessarily the metrics, so they are
    joined back from the ApacheJIT CSV by commit id. Rows with no match get
    zeros rather than being dropped - the embedding still carries signal.
    """
    # Mixed corpora happen: early fetches carried metrics, later ones did not.
    if all(r.get("features") for r in rows):
        return np.array([[float(r["features"].get(k, 0.0)) for k in KAMEI_FEATURES]
                         for r in rows], dtype=np.float32)

    csv_path = csv_path or (ROOT / "data" / "apachejit_total.csv")
    if not csv_path.exists():
        return None

    from corpus.apachejit import load_rows, row_values

    by_id = {r["commit_id"]: r for r in load_rows(csv_path)}
    matched = 0
    out = []
    for r in rows:
        src = by_id.get(r.get("commit_id", ""))
        if src is None:
            out.append([0.0] * len(KAMEI_FEATURES))
            continue
        matched += 1
        values = row_values(src)
        out.append([float(values[k]) for k in KAMEI_FEATURES])
    print(f"  joined process metrics for {matched}/{len(rows)} commits")
    return np.array(out, dtype=np.float32) if matched else None


def evaluate(name: str, head, X_te, y_te, target_recall: float) -> dict:
    from sklearn.metrics import average_precision_score, roc_auc_score

    p = head.predict_proba(X_te)[:, 1]
    threshold = tune_threshold(y_te, p, target_recall)
    reviewed = p >= threshold
    caught = int((reviewed & y_te.astype(bool)).sum())
    total_pos = int(y_te.sum())

    out = {
        "name": name,
        "auc": roc_auc_score(y_te, p) if 0 < y_te.sum() < len(y_te) else float("nan"),
        "pr_auc": average_precision_score(y_te, p),
        "threshold": threshold,
        "recall": caught / max(total_pos, 1),
        "llm_calls": float(reviewed.mean()),
        "saved": 1.0 - float(reviewed.mean()),
    }
    print(f"{name:22s} AUC={out['auc']:.3f}  PR-AUC={out['pr_auc']:.3f}  "
          f"t={threshold:.3f}  recall={out['recall']:.1%}  "
          f"LLM calls={out['llm_calls']:.1%}  saved={out['saved']:.1%}")
    return out


def train_variant(name: str, Xtr, ytr, Xte, yte, head_kind: str, seed: int,
                  target_recall: float):
    spw = float((ytr == 0).sum() / max((ytr == 1).sum(), 1))
    head = build_head(head_kind, seed=seed, scale_pos_weight=spw)
    head.fit(Xtr, ytr)
    return head, evaluate(name, head, Xte, yte, target_recall)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jsonl", type=Path,
                    default=ROOT / "data" / "apachejit_commits.jsonl")
    ap.add_argument("--out", type=Path, default=Path(GATE_MODEL_PATH))
    ap.add_argument("--head", choices=("lightgbm", "mlp"), default=GATE_HEAD)
    ap.add_argument("--target-recall", type=float, default=GATE_TARGET_RECALL)
    ap.add_argument("--train-frac", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--exclude", type=Path,
                    help="drop commits whose commit_id appears in this jsonl. "
                         "The eval set belongs here: gate.joblib was trained "
                         "on apachejit_commits.jsonl, which contains all 200 "
                         "of labelled_heldout.jsonl, so every gate number "
                         "measured on that set was leaked.")
    ap.add_argument("--ablate", action="store_true",
                    help="also train metrics-only and embeddings-only variants")
    ap.add_argument("--no-embeddings", action="store_true",
                    help="process metrics only (the 2013 baseline)")
    args = ap.parse_args(argv)

    if not args.jsonl.exists():
        raise SystemExit(f"{args.jsonl} not found — fetch commits first:\n"
                         f"  python -m corpus.fetch --limit 2500")

    rows = load_records(args.jsonl)
    if args.exclude:
        drop = {json.loads(l)["commit_id"]
                for l in open(args.exclude) if l.strip()}
        before = len(rows)
        rows = [r for r in rows if r.get("commit_id") not in drop]
        print(f"excluded {before - len(rows)} of {before} commits found in "
              f"{args.exclude} ({len(drop)} ids)")
        if not rows:
            raise SystemExit("--exclude removed every commit")
    y = np.array([bool(r.get("buggy")) for r in rows], dtype=int)
    diffs = [r["diff"] for r in rows]
    metrics = metrics_matrix(rows)
    print(f"{len(rows)} commits, {y.mean():.1%} buggy"
          + (f", {metrics.shape[1]} process metrics" if metrics is not None
             else ", no process metrics in this corpus"))

    # Chronological where possible: a random split lets the model see the future.
    order = np.arange(len(rows))
    cut = int(len(rows) * args.train_frac)
    tr, te = order[:cut], order[cut:]
    if y[tr].sum() == 0 or y[te].sum() == 0:
        raise SystemExit("split leaves one side with no defects — need more data")

    gate = Gatekeeper(None, use_embeddings=not args.no_embeddings)
    variants: list[tuple[str, np.ndarray]] = []

    if args.ablate:
        if metrics is not None:
            variants.append(("metrics only", np.asarray(metrics)))
        emb = Gatekeeper(None, use_embeddings=True).features(
            diffs, None, progress=lambda d, t: print(f"  encoding {d}/{t}", end="\r"))
        print()
        variants.append(("embeddings only", emb))
        if metrics is not None:
            variants.append(("embeddings + metrics", np.hstack([emb, metrics])))
    else:
        X = gate.features(
            diffs, metrics,
            progress=lambda d, t: print(f"  encoding {d}/{t}", end="\r"))
        print()
        variants.append(("gate", X))

    best, best_head, best_eval = None, None, None
    for name, X in variants:
        head, res = train_variant(name, X[tr], y[tr], X[te], y[te],
                                  args.head, args.seed, args.target_recall)
        # Rank by what the gate is for: saving calls while keeping recall.
        if best is None or res["saved"] > best_eval["saved"]:
            best, best_head, best_eval = name, head, res

    if gate.use_embeddings:
        gate.encoder.save_cache()

    n_metrics = 0 if metrics is None else int(metrics.shape[1])
    if best == "metrics only":
        trained = Gatekeeper(best_head, threshold=best_eval["threshold"],
                             use_embeddings=False, n_metrics=n_metrics)
    elif best == "embeddings only":
        trained = Gatekeeper(best_head, threshold=best_eval["threshold"],
                             use_embeddings=True, n_metrics=0)
    else:
        trained = Gatekeeper(best_head, threshold=best_eval["threshold"],
                             use_embeddings=not args.no_embeddings,
                             n_metrics=n_metrics)
    path = trained.save(args.out)
    print(f"\nbest: {best}")
    print(f"gate -> {path}  (threshold {best_eval['threshold']:.3f}, "
          f"recall {best_eval['recall']:.1%}, "
          f"skips {best_eval['saved']:.1%} of commits)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
