"""Search for a better gatekeeper: encoders x heads x feature sets.

    python -m ml_model.sweep_gate --jsonl data/apachejit_commits.jsonl

Reports AUC, PR-AUC and - the number that actually matters - how many LLM calls
each variant saves at the target recall. Ranking by AUC alone would pick a model
that is good at ordering commits it never has to decide about.

Encoders are cached separately, so re-running only pays for what is new.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ARTIFACTS, GATE_MODEL_PATH, GATE_TARGET_RECALL, ROOT
from ml_model.encoder import DiffEncoder
from ml_model.gate import Gatekeeper, build_head, tune_threshold
from ml_model.train_gate import load_records, metrics_matrix

ENCODERS = [
    "microsoft/graphcodebert-base",   # code + data-flow pretraining
    "microsoft/unixcoder-base",       # unified cross-modal, usually strongest
    "microsoft/codebert-base",        # the original baseline
]


def diff_stats(diffs: list[str]) -> np.ndarray:
    """Cheap surface features the encoder truncates away.

    A 512-token window sees the head of a diff; these summarise the whole of it,
    which is exactly the signal that gets cut off on long changes.
    """
    out = []
    for d in diffs:
        lines = d.splitlines()
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        files = sum(1 for l in lines if l.startswith("diff --git"))
        hunks = sum(1 for l in lines if l.startswith("@@"))
        tests = sum(1 for l in lines if "test" in l.lower() and l.startswith("+++"))
        out.append([
            added, removed, files, hunks, tests,
            added + removed,
            added / max(added + removed, 1),          # add/delete balance
            len(d) / max(len(lines), 1),              # mean line length
            sum(1 for l in lines if l.startswith("+") and "if " in l),
            sum(1 for l in lines if l.startswith("-") and "if " in l),
            sum(1 for l in lines if l.startswith("+") and "null" in l.lower()),
            sum(1 for l in lines if l.startswith("+") and "catch" in l.lower()),
        ])
    return np.array(out, dtype=np.float32)


def evaluate(name: str, head, Xte, yte, target_recall: float) -> dict:
    from sklearn.metrics import average_precision_score, roc_auc_score

    p = head.predict_proba(Xte)[:, 1]
    t = tune_threshold(yte, p, target_recall)
    reviewed = p >= t
    recall = float((reviewed & yte.astype(bool)).sum() / max(yte.sum(), 1))
    return {"name": name, "auc": float(roc_auc_score(yte, p)),
            "pr_auc": float(average_precision_score(yte, p)),
            "threshold": float(t), "recall": recall,
            "saved": 1.0 - float(reviewed.mean()), "head": head}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jsonl", type=Path,
                    default=ROOT / "data" / "apachejit_commits.jsonl")
    ap.add_argument("--out", type=Path, default=Path(GATE_MODEL_PATH))
    ap.add_argument("--target-recall", type=float, default=GATE_TARGET_RECALL)
    ap.add_argument("--train-frac", type=float, default=0.8)
    ap.add_argument("--encoders", default=",".join(ENCODERS))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--save-best", action="store_true")
    args = ap.parse_args(argv)

    rows = load_records(args.jsonl)
    y = np.array([bool(r.get("buggy")) for r in rows], dtype=int)
    diffs = [r["diff"] for r in rows]
    metrics = metrics_matrix(rows)
    stats = diff_stats(diffs)
    cut = int(len(rows) * args.train_frac)
    tr, te = np.arange(cut), np.arange(cut, len(rows))
    print(f"{len(rows)} commits, {y.mean():.1%} buggy, "
          f"train {len(tr)} / test {len(te)}\n")

    results = []
    for model_name in [e.strip() for e in args.encoders.split(",") if e.strip()]:
        short = model_name.split("/")[-1]
        cache = ARTIFACTS / f"emb_{short}.npz"
        try:
            enc = DiffEncoder(model_name=model_name, cache_path=cache)
            emb = enc.encode(diffs, progress=lambda d, t: print(
                f"  {short}: encoding {d}/{t}", end="\r"))
            enc.save_cache()
            print(f"  {short}: {emb.shape[1]}-d embeddings ready" + " " * 20)
        except Exception as e:
            print(f"  {short}: unavailable ({type(e).__name__}: {str(e)[:60]})")
            continue

        feature_sets = {
            "emb": emb,
            "emb+stats": np.hstack([emb, stats]),
        }
        if metrics is not None:
            feature_sets["emb+metrics"] = np.hstack([emb, metrics])
            feature_sets["emb+metrics+stats"] = np.hstack([emb, metrics, stats])

        for fname, X in feature_sets.items():
            for head_kind in ("lightgbm", "mlp"):
                spw = float((y[tr] == 0).sum() / max((y[tr] == 1).sum(), 1))
                head = build_head(head_kind, seed=args.seed,
                                  scale_pos_weight=spw)
                head.fit(X[tr], y[tr])
                res = evaluate(f"{short} | {fname} | {head_kind}",
                               head, X[te], y[te], args.target_recall)
                res["n_metrics"] = (metrics.shape[1] if metrics is not None
                                    and "metrics" in fname else 0)
                res["encoder"] = model_name
                results.append(res)
                print(f"    {res['name']:52s} AUC={res['auc']:.3f}  "
                      f"PR-AUC={res['pr_auc']:.3f}  recall={res['recall']:.0%}  "
                      f"saved={res['saved']:.1%}")

    if not results:
        raise SystemExit("no encoder was usable")

    results.sort(key=lambda r: -r["auc"])
    print(f"\nbest AUC:   {results[0]['name']}  {results[0]['auc']:.4f}")
    by_saved = max(results, key=lambda r: r["saved"])
    print(f"best saving: {by_saved['name']}  {by_saved['saved']:.1%} of LLM calls "
          f"at {by_saved['recall']:.0%} recall")

    if args.save_best:
        best = results[0]
        gate = Gatekeeper(best["head"], threshold=best["threshold"],
                          use_embeddings=True, n_metrics=best["n_metrics"])
        print(f"saved -> {gate.save(args.out)}")
        print("note: set ORACLE_GATE_ENCODER to the winning encoder, or the "
              "gate will be fed vectors from a different model at inference:")
        print(f"  export ORACLE_GATE_ENCODER={best['encoder']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
