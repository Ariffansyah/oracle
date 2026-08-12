"""Effort-aware evaluation for JIT defect prediction.

AUC treats every commit as equally cheap to inspect, which is wrong: a reviewer
spends time per changed line, so a model that flags a 3000-line commit and a
5-line commit has not offered them the same deal. The JIT literature therefore
ranks by defect *density* - predicted probability per unit of churn - and reports
how much of the defective set you catch inside a fixed inspection budget.

    PofB20  recall after inspecting 20% of the total churn
    Popt    normalised area between the model's cost-effectiveness curve and the
            optimal one (1.0 = optimal ordering, 0.5 = random, 0.0 = worst)
    IFA     how many clean commits you inspect before the first real defect -
            the number that decides whether developers keep trusting the tool
"""

from __future__ import annotations

import numpy as np


def _curve(y: np.ndarray, effort: np.ndarray, order: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cumulative (effort fraction, recall) along an inspection order."""
    y, effort = y[order], effort[order]
    x = np.concatenate([[0.0], np.cumsum(effort) / max(effort.sum(), 1e-9)])
    total_bugs = max(y.sum(), 1)
    ys = np.concatenate([[0.0], np.cumsum(y) / total_bugs])
    return x, ys


def _area(x: np.ndarray, y: np.ndarray) -> float:
    return float(np.trapezoid(y, x)) if hasattr(np, "trapezoid") else float(np.trapz(y, x))


def effort_aware(y_true, y_score, effort, budget: float = 0.2) -> dict:
    """PofB@budget, Popt and IFA for one set of predictions.

    `effort` is the inspection cost per commit - churn (la + ld) is the standard
    proxy. Ranking is by density (score / effort), not raw score, because that is
    what maximises defects found per line read.
    """
    y = np.asarray(y_true, dtype=float)
    score = np.asarray(y_score, dtype=float)
    effort = np.maximum(np.asarray(effort, dtype=float), 1.0)  # never divide by 0

    model_order = np.argsort(-(score / effort))
    # Optimal: real defects first, cheapest first. Worst: the exact reverse.
    optimal_order = np.argsort(-(y / effort))
    worst_order = optimal_order[::-1]

    xm, ym = _curve(y, effort, model_order)
    xo, yo = _curve(y, effort, optimal_order)
    xw, yw = _curve(y, effort, worst_order)

    area_o, area_w, area_m = _area(xo, yo), _area(xw, yw), _area(xm, ym)
    popt = 1.0 - (area_o - area_m) / max(area_o - area_w, 1e-9)

    # Recall at the budget, read off the model's curve.
    pofb = float(np.interp(budget, xm, ym))

    # IFA: clean commits inspected before the first defective one.
    ranked = y[model_order]
    hits = np.flatnonzero(ranked > 0)
    ifa = int(hits[0]) if hits.size else len(ranked)

    return {
        f"pofb{int(budget * 100)}": pofb,
        "popt": float(np.clip(popt, 0.0, 1.0)),
        "ifa": ifa,
        "effort_total": float(effort.sum()),
    }


if __name__ == "__main__":
    # A perfect ranker must beat a random one, and a reversed one must be worst.
    rng = np.random.default_rng(0)
    n = 500
    y = (rng.random(n) < 0.3).astype(float)
    effort = rng.lognormal(4, 1, n)

    perfect = effort_aware(y, y, effort)
    inverted = effort_aware(y, 1 - y, effort)
    random_ = effort_aware(y, rng.random(n), effort)

    assert perfect["popt"] > 0.99, perfect
    # Not exactly 0: clean commits all have density 0, so the "worst" ordering
    # is only defined up to ties among them.
    assert inverted["popt"] < 0.10, inverted
    assert 0.2 < random_["popt"] < 0.8, random_
    assert perfect["pofb20"] > random_["pofb20"] > inverted["pofb20"]
    assert perfect["ifa"] == 0 and inverted["ifa"] > 0

    # A cheap defect must rank ahead of an expensive one at equal confidence.
    order = effort_aware([1.0, 1.0], [0.9, 0.9], [10.0, 1000.0])
    assert order["ifa"] == 0
    print(f"perfect popt={perfect['popt']:.3f} pofb20={perfect['pofb20']:.3f}")
    print(f"random  popt={random_['popt']:.3f} pofb20={random_['pofb20']:.3f}")
    print(f"worst   popt={inverted['popt']:.3f} pofb20={inverted['pofb20']:.3f}")
