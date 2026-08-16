"""Explanation quality against the human-written CVE text.

The CVE description in each record's `analysis.summary` is human ground truth
written with knowledge of the bug. The model's findings are the explanation to
judge. Overlap is content-word F1 (harmonic mean of precision and recall):
how much of what the model said is in the human text, and how much of the
human text the model captured.

    python cve_quality.py data/cve_sft220.jsonl data/cve_stock.jsonl
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter

from evaluate import content_words, identifiers


def overlap(a: str, b: str) -> float:
    wa, wb = content_words(a), content_words(b)
    if not wa or not wb:
        return 0.0
    inter = len(wa & wb)
    p = inter / len(wa)
    r = inter / len(wb)
    return 2 * p * r / (p + r) if inter else 0.0


def id_overlap(a: str, b: str) -> float:
    ia, ib = identifiers(a), identifiers(b)
    if not ia or not ib:
        return 0.0
    inter = len(ia & ib)
    return inter / max(len(ia | ib), 1)  # Jaccard, shared names are the signal


def finding_overlaps(path: str) -> list[tuple[str, float, float]]:
    out = []
    for line in open(path):
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("error") or not r.get("predicted", {}).get("findings"):
            continue
        gt = r["analysis"].get("summary", "")
        for f in r["predicted"]["findings"]:
            exp = f.get("explanation", "")
            out.append((r["commit_id"], overlap(exp, gt), id_overlap(exp, gt)))
    return out


def report(name: str, rows: list[tuple[str, float, float]]) -> None:
    vals = [v for _, v, _ in rows]
    idv = [v for _, _, v in rows]
    nz = sum(1 for v in vals if v > 0)
    print(f"=== {name} ===")
    print(f"  findings           {len(rows)}")
    print(f"  word overlap F1    {sum(vals)/len(vals):.3f}   "
          f"median {sorted(vals)[len(vals)//2]:.3f}")
    print(f"  nonzero overlap    {nz/len(vals):.1%}")
    print(f"  identifier Jaccard {sum(idv)/len(idv):.3f}   "
          f"nonzero {sum(1 for v in idv if v>0)/len(idv):.1%}")


def paired_bootstrap(a: list[tuple[str, float, float]],
                     b: list[tuple[str, float, float]],
                     iters: int = 10000, seed: int = 0, idx: int = 1) -> dict:
    ka: dict[str, list[float]] = {}
    for cid, wo, io in a:
        ka.setdefault(cid, []).append((wo, io)[idx])
    kb: dict[str, list[float]] = {}
    for cid, wo, io in b:
        kb.setdefault(cid, []).append((wo, io)[idx])
    keys = sorted(set(ka) & set(kb))
    if not keys:
        return {"n": 0}
    blocks = [k for k in keys]  # one finding set per commit, resampled whole
    mean = lambda rows: sum(rows) / len(rows)
    observed = mean([mean(ka[k]) for k in keys]) - mean([mean(kb[k]) for k in keys])
    rng = random.Random(seed)
    diffs = []
    for _ in range(iters):
        drawn = [rng.choice(blocks) for _ in blocks]
        diffs.append(mean([mean(ka[k]) for k in drawn]) -
                     mean([mean(kb[k]) for k in drawn]))
    diffs.sort()
    return {"n": len(keys), "diff": observed,
            "lo": diffs[int(0.025 * iters)], "hi": diffs[int(0.975 * iters)],
            "p": sum(1 for d in diffs if d <= 0) / iters}


def main(argv=None) -> int:
    if len(argv or sys.argv[1:]) < 2:
        print(__doc__)
        return 2
    paths = argv or sys.argv[1:]
    rows = [finding_overlaps(p) for p in paths]
    for p, r in zip(paths, rows):
        report(p, r)
    if len(paths) == 2:
        for label, idx in (("word overlap", 0), ("identifier Jaccard", 1)):
            s = paired_bootstrap(*rows, idx=idx)
            print(f"\n=== {paths[0]} - {paths[1]} : {label} ===")
            if s["n"]:
                print(f"  paired on         {s['n']} commits")
                print(f"  diff              {s['diff']:+.3f}   "
                      f"95% CI [{s['lo']:+.3f}, {s['hi']:+.3f}]")
                print(f"  bootstrap p       {s['p']:.4f}")
    return 0


if __name__ == "__main__":
    assert overlap("use after free in blk_mq_tag_to_rq", "use after free in blk_mq_tag_to_rq") == 1.0
    assert overlap("buffer overflow in parse", "unrelated text about nothing") == 0.0
    assert id_overlap("fq->flush_rq null check", "race in blk_mq_tag_to_rq around flush_rq") > 0.0
    assert id_overlap("", "anything") == 0.0
    print("cve_quality checks ok")
    raise SystemExit(main())