"""Can Stage 1 tell introducing a defect from repairing it?

    python bench/direction_probe.py

Every JIT defect predictor in the literature is trained on one label: SZZ's
"this commit is bug-inducing". Nothing in that label, or in the AUC computed
over it, asks a model to separate a defect from its own repair -- the fix
commit is simply not in the negative class in a way that tests it.

This probe asks. Each fixture family supplies three commits over the SAME code:

    introduce   clean -> buggy      behaviour changes, for the worse
    fix         buggy -> clean      behaviour changes, for the better
    refactor    clean -> clean      behaviour PRESERVED (a rename)

A model with defect signal should rank introduce above the other two. A model
reading commit shape should rank them together, because all three are small
edits to the same lines. That is the hypothesis being tested, and the
refactor arm is the control: it changes tokens and changes nothing else.

The gate is scored on its EMBEDDING channel only. Synthetic fixtures have no
repository history, so the 14 process metrics do not exist for them -- see
`Gatekeeper.features`, which zero-fills. Zero-filling a channel the head was
trained to use would measure the zero-fill, so the head here is retrained on
ApacheJIT embeddings alone. That arm scores AUC 0.768 on ApacheJIT's own
chronological split, against 0.829 for embeddings+metrics.
"""
from __future__ import annotations

import argparse
import difflib
import json
import pathlib
import sys
from collections import defaultdict

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml_model.gate import Gatekeeper, build_head          # noqa: E402
from ml_model.train_gate import load_records              # noqa: E402


def unified(pre: str, post: str, name: str) -> str:
    return "".join(difflib.unified_diff(
        pre.splitlines(keepends=True), post.splitlines(keepends=True),
        fromfile=f"a/{name}", tofile=f"b/{name}"))


def read_pair(d: pathlib.Path, ext: str) -> str | None:
    pre, post = d / f"pre.{ext}", d / f"post.{ext}"
    if not (pre.exists() and post.exists()):
        return None
    return unified(pre.read_text(), post.read_text(), f"prog.{ext}")


def collect() -> list[dict]:
    """One record per (family, arm) with its diff."""
    out = []
    for meta_p in sorted((ROOT / "bench/mechanism_pilot").glob("*/meta.json")):
        m = json.loads(meta_p.read_text())
        diff = read_pair(meta_p.parent, m["ext"])
        if diff:
            out.append({"family": m["id"], "arm": "introduce",
                        "lang": m["language"], "diff": diff})
    for meta_p in sorted((ROOT / "bench/clean_direction").glob("*/meta.json")):
        m = json.loads(meta_p.read_text())
        diff = read_pair(meta_p.parent, m["ext"])
        if diff:
            out.append({"family": m["parent"],
                        "arm": "fix" if m["label"] == "fix" else "refactor",
                        "lang": m["language"], "diff": diff})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", type=pathlib.Path,
                    default=ROOT / "data/apachejit_commits.jsonl")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "data/direction_probe.json")
    args = ap.parse_args()

    recs = collect()
    fams = defaultdict(dict)
    for r in recs:
        fams[r["family"]][r["arm"]] = r
    triplets = {f: a for f, a in fams.items()
                if {"introduce", "fix", "refactor"} <= set(a)}
    print(f"{len(recs)} fixtures, {len(fams)} families, "
          f"{len(triplets)} complete triplets\n")
    if not triplets:
        print("no complete triplets — nothing to probe")
        return 1

    rows = load_records(args.jsonl)
    y = np.array([bool(r.get("buggy")) for r in rows], dtype=int)
    cut = int(len(rows) * 0.8)
    gate = Gatekeeper(None, use_embeddings=True)
    print("encoding ApacheJIT diffs (embedding channel only)...")
    X = gate.features([r["diff"] for r in rows],
                      progress=lambda d, t: print(f"  {d}/{t}", end="\r"))
    print()
    spw = float((y[:cut] == 0).sum() / max((y[:cut] == 1).sum(), 1))
    head = build_head("lightgbm", seed=args.seed, scale_pos_weight=spw)
    head.fit(X[:cut], y[:cut])
    gate.head = head

    order = sorted(triplets)
    for arm in ("introduce", "fix", "refactor"):
        diffs = [triplets[f][arm]["diff"] for f in order]
        Xf = gate.features(diffs)
        for f, s in zip(order, head.predict_proba(Xf)[:, 1]):
            triplets[f][arm]["score"] = float(s)

    def col(arm):
        return np.array([triplets[f][arm]["score"] for f in order])
    I, F, R = col("introduce"), col("fix"), col("refactor")

    print(f"n = {len(order)} triplets, same code in all three arms\n")
    print(f"{'arm':<12}{'mean':>9}{'median':>9}{'min':>9}{'max':>9}")
    for name, v in (("introduce", I), ("fix", F), ("refactor", R)):
        print(f"{name:<12}{v.mean():>9.3f}{np.median(v):>9.3f}{v.min():>9.3f}{v.max():>9.3f}")

    # THE SIZE CONTROL. It runs before the result, and the result is not
    # printed without it, because the first version of this probe was confounded:
    # a rename touches every use of the identifier, so the refactor arm's diffs
    # are 2.75x larger than the defects they are the control for. Any model
    # reading commit size would "prefer" them for that reason alone.
    def changed(d):
        return sum(1 for l in d.splitlines()
                   if l[:1] in "+-" and l[:3] not in ("+++", "---"))
    SZ = {a: np.array([changed(triplets[f][a]["diff"]) for f in order])
          for a in ("introduce", "fix", "refactor")}
    print(f"{'':<12}{'diff lines':>12}{'median':>9}   size-matched to `introduce`?")
    for a in ("introduce", "fix", "refactor"):
        v = SZ[a]
        if a == "introduce":
            note = "-"
        else:
            same = int((v == SZ["introduce"]).sum())
            note = (f"YES, {same}/{len(order)} identical" if same == len(order)
                    else f"NO -- larger on {int((v > SZ['introduce']).sum())}/{len(order)}")
        print(f"{a:<12}{v.mean():>12.1f}{np.median(v):>9.0f}   {note}")

    from scipy.stats import binomtest, spearmanr, wilcoxon
    rho, prho = spearmanr(np.concatenate([SZ[a] for a in SZ]),
                          np.concatenate([col(a) for a in SZ]))
    print(f"\nSpearman(diff size, gate score) over all {3 * len(order)} "
          f"fixtures: rho = {rho:.3f}, p = {prho:.3g}")

    print(f"\n{'ordering':<34}{'holds':>8}{'of':>5}{'rate':>8}{'p':>10}")
    for label, a, b in (("introduce > refactor", I, R),
                        ("introduce > fix", I, F),
                        ("fix > refactor", F, R)):
        k = int((a > b).sum()); n = len(a)
        p = binomtest(k, n, 0.5).pvalue
        print(f"{label:<34}{k:>8}{n:>5}{k / n:>8.0%}{p:>10.3g}")
    print("\nPaired Wilcoxon on the score itself:")
    for label, a, b in (("introduce vs refactor", I, R),
                        ("introduce vs fix", I, F)):
        try:
            print(f"  {label:<24} p = {wilcoxon(a, b).pvalue:.3g}")
        except ValueError as e:
            print(f"  {label:<24} {e}")

    print("\nWHAT THIS LICENSES")
    print("  `introduce vs fix` is the clean test: the two arms edit the same")
    print("  lines of the same file and have IDENTICAL diff sizes, so nothing")
    print("  about commit shape separates them. Whatever the gate scores there")
    print("  is defect signal or it is nothing.")
    print("  `introduce vs refactor` is CONFOUNDED by size and must be reported")
    print("  as suggestive only, however large its p-value looks.")

    args.out.write_text(json.dumps(
        {"n": len(order),
         "families": {f: {a: triplets[f][a]["score"] for a in
                          ("introduce", "fix", "refactor")} for f in order}},
        indent=1))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
