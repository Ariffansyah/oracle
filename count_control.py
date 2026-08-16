"""The trivial baseline for any diff-direction task: count the lines.

    python count_control.py data/cve_gate.jsonl 0.6667
    python count_control.py data/apachejit_commits.jsonl 0.8

A fix adds a guard, so it carries more `+` lines than `-`; the reverse carries
the mirror image. Ten counting features recover that with no model at all. Run
this beside every detection number from a paired corpus - it is that corpus's
always-buggy baseline, and a learned model that does not clear it has learnt to
count.
"""

from __future__ import annotations

import json
import sys

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score


def features(diff: str) -> list[float]:
    body = [l for l in diff.splitlines()
            if not l.startswith(("diff ", "---", "+++", "@@"))]
    p = sum(1 for l in body if l.startswith("+"))
    m = sum(1 for l in body if l.startswith("-"))
    pc = sum(len(l) for l in body if l.startswith("+"))
    mc = sum(len(l) for l in body if l.startswith("-"))
    return [p, m, p - m, p / max(m, 1), pc, mc, pc - mc, pc / max(mc, 1),
            len(diff), len(body)]


def main(path: str, train_frac: float) -> int:
    rows = [json.loads(l) for l in open(path) if l.strip()]
    rows = [r for r in rows if r.get("diff")]
    X = np.array([features(r["diff"]) for r in rows], dtype=np.float32)
    y = np.array([bool(r.get("buggy")) for r in rows], dtype=int)
    # Positional, matching train_gate.py: chronological where the corpus is
    # ordered, and for the paired corpus it is the repo-disjoint split.
    cut = int(len(rows) * train_frac)
    tr, te = slice(0, cut), slice(cut, len(rows))
    print(f"{len(rows)} commits, {y.mean():.1%} buggy, test n={len(rows) - cut}")

    for label, cols in (("counting only (all 10)", list(range(10))),
                        ("plus-minus lines alone", [2]),
                        ("plus-minus chars alone", [6])):
        clf = HistGradientBoostingClassifier(random_state=0).fit(X[tr][:, cols], y[tr])
        p = clf.predict_proba(X[te][:, cols])[:, 1]
        print(f"{label:26s} AUC={roc_auc_score(y[te], p):.3f}  "
              f"PR-AUC={average_precision_score(y[te], p):.3f}")

    d = X[:, 2]
    print(f"\nmean(plus-minus lines): buggy {d[y == 1].mean():+.2f}   "
          f"clean {d[y == 0].mean():+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "data/cve_gate.jsonl",
                          float(sys.argv[2]) if len(sys.argv) > 2 else 0.6667))
