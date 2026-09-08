"""Stage 1 trained on a VERIFIED label instead of an SZZ heuristic.

    python bench/behaviour_gate.py

Every JIT defect predictor -- JITLine, DeepJIT, CC2Vec, aegis, and this
project's own gate -- is trained on one label: SZZ's "this commit is
bug-inducing", inferred by blaming the lines a later fix touched. Nothing
verifies it, and `bench/direction_probe.py` shows what that costs: on 35
size-matched pairs the SZZ-trained gate cannot tell a defect from its own
repair (14/35, p = 0.31).

This trains the SAME architecture on a label that was MEASURED. Every row of
`exec_sft_v3.jsonl` carries `differs`, established by running the program
before and after the change and comparing output. So the target becomes:

    will running this commit change observable behaviour?

which is the question a cascade actually needs answered -- `bench/exec_filter.py`
records that byte-identical pre/post output establishes nothing, so routing
those commits to Stage 2 is wasted compute.

Only the target changes. Same GraphCodeBERT encoder, same LightGBM head, same
seed, same hyperparameters as `ml_model.train_gate`, so any difference is the
label and not the model.

The triplet evaluation is adversarial by construction: the `refactor` arm has
diffs 2.75x LARGER than the defects it controls for, so a model reading commit
size is pushed to rank it highest. A behaviour-change model must rank it
LOWEST, against that gradient.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import defaultdict

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml_model.gate import Gatekeeper, build_head       # noqa: E402
from bench.direction_probe import collect              # noqa: E402

_DIFF = re.compile(r"```diff\n(.*?)```", re.S)


def rows_of(path: pathlib.Path) -> tuple[list[str], np.ndarray, list[str]]:
    diffs, y, fam = [], [], []
    for line in open(path):
        r = json.loads(line)
        m = _DIFF.search(r["messages"][1]["content"])
        if not m:
            continue
        diffs.append(m.group(1))
        y.append(bool(r["differs"]))
        fam.append(r["family"])
    return diffs, np.array(y, dtype=int), fam


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=pathlib.Path,
                    default=ROOT / "data/exec_sft_v3.jsonl")
    ap.add_argument("--test", type=pathlib.Path,
                    default=ROOT / "data/exec_sft_v3_holdout_cross.jsonl")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--extra", type=pathlib.Path, default=None,
                    help="a multi-language corpus from gen_exec_multilang; "
                         "its rows carry `diff` and `differs` directly")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "data/behaviour_gate.json")
    args = ap.parse_args()

    Xd, y, fam = rows_of(args.train)
    if args.extra:
        ed, ey, ef = [], [], []
        for line in open(args.extra):
            r = json.loads(line)
            ed.append(r["diff"]); ey.append(bool(r["differs"]))
            ef.append(f"{r['family']}@{r['lang']}")
        print(f"+{len(ed)} multi-language rows from {args.extra.name} "
              f"({np.mean(ey):.0%} behaviour-changing, "
              f"{len({f.split('@')[1] for f in ef})} languages)")
        Xd = Xd + ed
        y = np.concatenate([y, np.array(ey, dtype=int)])
        fam = fam + ef
    Td, ty, tfam = rows_of(args.test)
    print(f"train {len(Xd)} rows, {y.mean():.0%} behaviour-changing, "
          f"{len(set(fam))} families")
    print(f"test  {len(Td)} rows, {ty.mean():.0%} behaviour-changing, "
          f"{len(set(tfam))} families, "
          f"{len(set(tfam) & set(fam))} shared with train\n")

    gate = Gatekeeper(None, use_embeddings=True)
    print("encoding...")
    X = gate.features(Xd, progress=lambda d, t: print(f"  {d}/{t}", end="\r"))
    T = gate.features(Td)
    print()
    spw = float((y == 0).sum() / max((y == 1).sum(), 1))
    head = build_head("lightgbm", seed=args.seed, scale_pos_weight=spw)
    head.fit(X, y)
    gate.head = head

    from sklearn.metrics import average_precision_score, roc_auc_score
    p = head.predict_proba(T)[:, 1]
    print(f"held-out CROSS-family: AUC = {roc_auc_score(ty, p):.3f}, "
          f"PR-AUC = {average_precision_score(ty, p):.3f}  "
          f"(base rate {ty.mean():.0%})\n")

    # --- the triplets, the same 35 the SZZ gate was probed on ---
    recs = collect()
    fams = defaultdict(dict)
    for r in recs:
        fams[r["family"]][r["arm"]] = r
    T3 = {f: a for f, a in fams.items()
          if {"introduce", "fix", "refactor"} <= set(a)}
    order = sorted(T3)
    for arm in ("introduce", "fix", "refactor"):
        sc = head.predict_proba(
            gate.features([T3[f][arm]["diff"] for f in order]))[:, 1]
        for f, s in zip(order, sc):
            T3[f][arm]["score"] = float(s)
    col = lambda a: np.array([T3[f][a]["score"] for f in order])
    I, F, R = col("introduce"), col("fix"), col("refactor")
    langs = [T3[f]["introduce"]["lang"] for f in order]

    print(f"{len(order)} triplets ({len(set(langs))} languages; the corpus is "
          f"Python-only, so every non-Python row is cross-language transfer)\n")
    print(f"{'arm':<12}{'mean':>9}{'median':>9}   what it should be")
    for name, v, want in (("introduce", I, "HIGH -- behaviour changes"),
                          ("fix", F, "HIGH -- behaviour changes"),
                          ("refactor", R, "LOW  -- behaviour preserved")):
        print(f"{name:<12}{v.mean():>9.3f}{np.median(v):>9.3f}   {want}")

    from scipy.stats import binomtest, wilcoxon
    print(f"\n{'ordering':<34}{'holds':>8}{'of':>5}{'rate':>8}{'p':>10}")
    for label, a, b in (("introduce > refactor", I, R),
                        ("fix > refactor", F, R),
                        ("introduce > fix  (should be ~50%)", I, F)):
        k = int((a > b).sum()); n = len(a)
        print(f"{label:<34}{k:>8}{n:>5}{k / n:>8.0%}"
              f"{binomtest(k, n, 0.5).pvalue:>10.3g}")
    print("\nPaired Wilcoxon:")
    for label, a, b in (("introduce vs refactor", I, R),
                        ("fix vs refactor", F, R)):
        print(f"  {label:<24} p = {wilcoxon(a, b).pvalue:.3g}")

    py = [i for i, l in enumerate(langs) if l == "python"]
    if py:
        k = int((I[py] > R[py]).sum())
        print(f"\nPython-only subset (in-distribution), introduce > refactor: "
              f"{k}/{len(py)} ({k / len(py):.0%})")

    args.out.write_text(json.dumps(
        {"n": len(order),
         "families": {f: {a: T3[f][a]["score"]
                          for a in ("introduce", "fix", "refactor")}
                      for f in order}}, indent=1))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
