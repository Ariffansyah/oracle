"""Compare the three BugsInPy arms, paired, with the same test used before.

The arms are run over the same rows in the same order, so every comparison here
is paired and McNemar applies: only the rows where two arms disagree carry
information, and the question is whether the disagreements are lopsided.

    python bench/bugsinpy_compare.py
    python bench/bugsinpy_compare.py --metric names_exception
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DEFAULT_ARMS = "exec,score,diff"


def arm_path(name: str, d: pathlib.Path, prefix: str) -> pathlib.Path:
    """`exec` -> bip_arm_exec.json; `guarded` -> bip_guarded.json."""
    for cand in (d / f"{prefix}{name}.json", d / f"bip_{name}.json"):
        if cand.exists():
            return cand
    return d / f"{prefix}{name}.json"

from bench.eval_bugsinpy_arms import (  # noqa: E402
    diff_of, from_commit_message, invents_exception, names_symbol,
    quotes_signature)


def rescore(arms: dict, rows_path: pathlib.Path) -> None:
    """Recompute every judgement from the stored text, in place.

    The arm files keep the explanation the model produced, so a change to the
    rubric does not need three more hours of GPU. It also means the rubric that
    produced the numbers is always the one in the tree, not whichever version
    happened to be checked out on the night the arms ran -- and the first
    version of `invents_exception` was wrong, counting a correct explanation as
    a fabrication whenever the measured signature named a second class.
    """
    src = {}
    for line in open(rows_path):
        r = json.loads(line)
        src[r["id"]] = r
    for arm in arms:
        for r in arms[arm]["rows"]:
            base = src.get(r["id"])
            if base is None:
                continue
            expl, exc, before = r["explanation"], r["exception"], r["before"]
            r["names_exception"] = bool(expl) and bool(exc) and exc in expl
            r["quotes_signature"] = bool(expl) and quotes_signature(expl, before)
            r["invented"] = (invents_exception(expl, exc, before) if expl
                             else None)
            r["from_message"] = bool(r["invented"]) and from_commit_message(
                expl, base.get("subject", ""), exc)
            r["names_symbol"] = bool(expl) and names_symbol(
                expl, diff_of(base["messages"][1]["content"]))


def mcnemar(a: list[bool], b: list[bool]) -> tuple[int, int, float]:
    """(only-A, only-B, two-sided exact p) over the discordant pairs."""
    from scipy.stats import binomtest

    n01 = sum(1 for x, y in zip(a, b) if x and not y)
    n10 = sum(1 for x, y in zip(a, b) if y and not x)
    if n01 + n10 == 0:
        return n01, n10, 1.0
    return n01, n10, float(binomtest(n01, n01 + n10, 0.5).pvalue)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=pathlib.Path, default=ROOT / "data")
    ap.add_argument("--prefix", default="bip_arm_")
    ap.add_argument("--metric", default="grounded")
    ap.add_argument("--arms", default=DEFAULT_ARMS,
                    help="comma-separated; the first is the reference column")
    ap.add_argument("--rows", type=pathlib.Path,
                    default=ROOT / "data" / "bugsinpy_rows_v1.jsonl")
    ap.add_argument("--no-rescore", action="store_true",
                    help="trust the judgements stored in the arm files")
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    data = {}
    for arm in arms:
        p = arm_path(arm, args.dir, args.prefix)
        if not p.exists():
            print(f"missing {p}", file=sys.stderr)
            return 1
        data[arm] = json.loads(p.read_text())

    if not args.no_rescore:
        if not args.rows.exists():
            print(f"missing {args.rows} — pass --no-rescore to skip rescoring",
                  file=sys.stderr)
            return 1
        rescore(data, args.rows)

    # Pair on ids rather than assume order, and drop any row an arm is missing:
    # a run that died halfway must narrow the comparison, not silently
    # misalign it.
    common = set.intersection(*[{r["id"] for r in data[a]["rows"]} for a in arms])
    ids = [r["id"] for r in data[arms[0]]["rows"] if r["id"] in common]
    for arm in arms:
        by_id = {r["id"]: r for r in data[arm]["rows"]}
        data[arm]["rows"] = [by_id[i] for i in ids]
    n = len(ids)
    short = [a for a in arms if len(data[a]["rows"]) != data[a].get("n", n)]
    if short:
        print(f"note: comparing the {n} rows every arm has; "
              f"{', '.join(short)} had a different total\n")

    def flags(arm: str, metric: str) -> list[bool]:
        rows = data[arm]["rows"]
        if metric == "grounded":
            return [bool((r["names_exception"] or r["quotes_signature"])
                         and not r["invented"]) for r in rows]
        if metric == "invented":
            return [bool(r["invented"]) for r in rows]
        return [bool(r[metric]) for r in rows]

    print(f"n = {n} rows, the same rows in the same order for all "
          f"{len(arms)} arms\n")
    header = f"{'':<32}" + "".join(f"{a:>12}" for a in arms)
    print(header)
    for label, metric in (("names the real exception", "names_exception"),
                          ("quotes the real message", "quotes_signature"),
                          ("names a changed identifier", "names_symbol"),
                          ("INVENTS a different failure", "invented"),
                          ("  ...of those, from the message", "from_message"),
                          ("GROUNDED (right, not invented)", "grounded")):
        cells = []
        for a in arms:
            if metric == "from_message":
                v = sum(bool(r["from_message"]) for r in data[a]["rows"])
            else:
                v = sum(flags(a, metric))
            cells.append(f"{v} ({v / n:.0%})")
        print(f"{label:<32}" + "".join(f"{c:>12}" for c in cells))

    print(f"\nMcNemar on `{args.metric}`, paired over the same {n} rows:")
    print(f"{'comparison':<20}{'only A':>9}{'only B':>9}{'p':>12}")
    for i, a in enumerate(arms):
        for b in arms[i + 1:]:
            n01, n10, p = mcnemar(flags(a, args.metric), flags(b, args.metric))
            verdict = "distinguishable" if p < 0.05 else "NOT distinguishable"
            print(f"{a + ' vs ' + b:<20}{n01:>9}{n10:>9}{p:>12.3g}   {verdict}")

    # the half where the values have to be derived rather than restated
    rows0 = data[arms[0]]["rows"]
    diffs = [bool(r.get("exception")) for r in rows0]
    if any(diffs) and not all(diffs):
        print("\nSplit by whether the failure names an exception class:")
        print(f"{'':<20}{'has a class':>14}{'bare assert':>14}")
        for a in arms:
            f = flags(a, "grounded")
            hi = [x for x, d in zip(f, diffs) if d]
            lo = [x for x, d in zip(f, diffs) if not d]
            print(f"{a:<20}{sum(hi)}/{len(hi)} ({sum(hi)/len(hi):.0%})".ljust(34)
                  + f"{sum(lo)}/{len(lo)} ({sum(lo)/len(lo):.0%})")

    by_proj: dict[str, list[bool]] = {}
    for r, ok in zip(data[arms[0]]["rows"], flags(arms[0], "grounded")):
        by_proj.setdefault(r["project"], []).append(ok)
    print(f"\n{arms[0]}, grounded, by project:")
    for p in sorted(by_proj, key=lambda k: -len(by_proj[k])):
        v = by_proj[p]
        print(f"  {p:<14}{sum(v)}/{len(v)} ({sum(v)/len(v):.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
