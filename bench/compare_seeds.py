#!/usr/bin/env python3
"""Compare two corpora across a matched pair of seeds, and report RANGES.

    python bench/compare_seeds.py                          # v3 vs v2, the default
    python bench/compare_seeds.py --base v2_pilot2 v2_seed7 --new v3 v3_seed7

Why this script exists
----------------------
On 28 Aug two checkpoints were trained on an IDENTICAL corpus with identical
steps, differing only by `--seed 42` against `--seed 7`. Seed alone moved 24 of
101 cases and the headline by 10. Every checkpoint comparison this project had
published was a single-seed point estimate, and the ones with gaps under ~10
cases were therefore unsupported.

So a corpus effect is only readable where BOTH seeds move the same way by more
than the spread the seed pair shows on its own. That rule is `_readable()`
below, and it is the whole point of the file. A single-seed delta printed
without its band is not a result, and this script will not produce one.

The headline metric
-------------------
`fully` reproduces `basic_bench.py:413` — `verdict_ok and (identified or not
buggy)`, so clean cases pass by not being flagged. It gives 76/101 and 86/101
for the two v2 seeds, matching what is written down in docs/. Summing raw
`identified` does NOT reproduce those (it gives 44 and 47): that is a buggy-only
count, and it is reported separately as `locus`. If a change here stops
reproducing 76 and 86 on the v2 pair, the metric drifted — fix that before
reading any delta.

Direction
---------
`_readable()` answers "is this movement bigger than seed noise", NOT "is this
movement good". For `false_alarm` and `fabricated` a readable DROP is the win;
for every other metric a readable RISE is.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

SETS = {"basic": "basic_bench",
        "mech_heldout": "heldout_mech",
        "clean_heldout": "heldout_clean"}

# `observable` is v2-only: v3 retired the field, so it reads 0 for every v3/v4/v6
# tag and its column is dead weight in a v3 comparison. `check_useful` replaced
# it as the contract's own metric and was missing from this table entirely,
# which meant the one number the suggestion contract exists to move was not in
# the comparison that decides whether the contract moved anything.
METRICS = ("fully", "locus", "direction", "observable", "check_useful",
           "false_alarm", "fabricated", "errored")

# The 5 bench/basic cases that add a function and are clean. Held out of the v3
# corpus (verified 29 Aug: 0 occurrences in data/sft_v3_extract.jsonl), so they
# test transfer rather than memorisation.
HELD = ["go-extract-helper", "java-extract-method", "js-extract-helper",
        "php-extract-helper", "py-extract-helper"]
# Of those, the only two that false-alarm on BOTH v2 seeds, and so the only two
# where movement can be attributed to the corpus. Both seeds score "3 of 5" but
# NOT the same 3: `go` and `java` each flip on the seed by themselves, and `js`
# is already quiet on both, so it has no headroom.
STABLE_TARGET = {"php-extract-helper", "py-extract-helper"}
# Stable false alarms that are NOT extract-shaped. If these go quiet too, the
# model got globally more timid rather than better at this shape.
CONTROL = {"c-const", "py-comprehension"}


def load(stem: str, tag: str) -> list[dict] | None:
    p = DATA / f"{stem}_{tag}.jsonl"
    if not p.exists():
        return None
    with p.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def fully_ok(r: dict) -> bool:
    return bool(r.get("verdict_ok") and (r.get("identified") or not r.get("buggy")))


def tally(rows: list[dict]) -> dict:
    return dict(
        n=len(rows),
        fully=sum(1 for r in rows if fully_ok(r)),
        locus=sum(1 for r in rows if r.get("identified")),
        direction=sum(1 for r in rows if r.get("effect_direction_ok")),
        observable=sum(1 for r in rows if r.get("effect_observable_ok")),
        # Graded on buggy cases only (None on clean), so this is out of a
        # smaller denominator than the rest of the column - printed as a count
        # for consistency, read against `n_check`.
        check_useful=sum(1 for r in rows if r.get("effect_check_useful")),
        n_check=sum(1 for r in rows
                    if r.get("effect_check_useful") is not None),
        hedged=sum(1 for r in rows
                   if str(r.get("effect_confidence") or "").lower() == "possible"),
        false_alarm=sum(1 for r in rows if r.get("false_alarm")),
        fabricated=sum(1 for r in rows if r.get("effect_fabricated")),
        errored=sum(1 for r in rows if r.get("error")),
    )


def band(a: int, b: int) -> str:
    return f"{a}" if a == b else f"{min(a, b)}-{max(a, b)}"


def _readable(base: tuple[int, int], new: tuple[int, int]) -> str:
    """Is the corpus effect bigger than the seed noise on this metric.

    Both seeds must move the SAME way, and the smaller of the two moves must
    clear the spread the base seed pair shows on its own (floored at 2, so a
    metric that happens to be seed-stable still needs a real move to count).
    """
    spread = abs(base[0] - base[1])
    moved = (new[0] - base[0], new[1] - base[1])
    if moved == (0, 0):
        return "no - unchanged"
    same_way = (moved[0] > 0 and moved[1] > 0) or (moved[0] < 0 and moved[1] < 0)
    if not same_way:
        return "no - seeds disagree"
    if min(abs(moved[0]), abs(moved[1])) <= max(spread, 2):
        return f"no - inside seed band (+-{max(spread, 2)})"
    return f"YES ({moved[0]:+d}/{moved[1]:+d})"


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", nargs=2, metavar=("SEED42", "SEED7"),
                    default=["v2_pilot2", "v2_seed7"],
                    help="file tags for the baseline seed pair")
    ap.add_argument("--new", nargs=2, metavar=("SEED42", "SEED7"),
                    default=["v3", "v3_seed7"],
                    help="file tags for the new seed pair")
    args = ap.parse_args()
    b42, b7 = args.base
    n42, n7 = args.new

    print("=" * 78)
    print(f"{n42}/{n7} vs {b42}/{b7} - read over two seeds, never a point estimate")
    print("=" * 78)

    for label, stem in SETS.items():
        base = {s: load(stem, s) for s in (b42, b7)}
        new = {s: load(stem, s) for s in (n42, n7)}
        if not all(base.values()):
            print(f"\n--- {label} --- baseline incomplete, skipped")
            continue
        tb = {s: tally(rows) for s, rows in base.items()}
        tn = {s: tally(rows) for s, rows in new.items() if rows}
        print(f"\n--- {label} ({tb[b42]['n']} cases) ---")
        print(f"{'metric':<12}{'base/42':>9}{'base/7':>8}{'band':>8}"
              f"{'new/42':>9}{'new/7':>8}{'band':>8}   readable?")
        for m in METRICS:
            a, b = tb[b42][m], tb[b7][m]
            if len(tn) == 2:
                c, d = tn[n42][m], tn[n7][m]
                # A metric the BASE contract does not have is not a measurable
                # improvement, it is a schema difference. v2 has no `check`, so
                # `check_useful` reads 0 there and every comparison against it
                # would print YES for free.
                verdict = (
                    "n/a - base contract has no `check`"
                    if m == "check_useful" and tb[b42]["n_check"] == 0
                       and tb[b7]["n_check"] == 0
                    else _readable((a, b), (c, d)))
                print(f"{m:<12}{a:>9}{b:>8}{band(a, b):>8}"
                      f"{c:>9}{d:>8}{band(c, d):>8}   {verdict}")
            else:
                got = next(iter(tn.values()), None)
                c = got[m] if got else "-"
                print(f"{m:<12}{a:>9}{b:>8}{band(a, b):>8}"
                      f"{c:>9}{'-':>8}{'-':>8}   awaiting second seed")
        # check_useful's denominator, and the calibration field. Neither is a
        # pass/fail number, so they sit under the table rather than in it - but
        # a `check_useful` read without its denominator, or a confidence column
        # that is a constant, is how v4's near-constant `likely` went unnoticed
        # until the audit.
        nb = f"{tb[b42]['n_check']}/{tb[b7]['n_check']}"
        hb = f"{tb[b42]['hedged']}/{tb[b7]['hedged']}"
        if len(tn) == 2:
            nn = f"{tn[n42]['n_check']}/{tn[n7]['n_check']}"
            hn = f"{tn[n42]['hedged']}/{tn[n7]['hedged']}"
        else:
            nn = hn = "-"
        print(f"{'  (of)':<12}{nb:>17}{'':>8}{nn:>17}"
              f"   cases check_useful was graded on")
        print(f"{'  possible':<12}{hb:>17}{'':>8}{hn:>17}"
              f"   answers hedged to `possible`")

    # ---- noise floor, measured from the baseline pair ----------------------
    print("\n" + "=" * 78)
    print(f"NOISE FLOOR, measured ({b42} vs {b7} - identical corpus, seed the only")
    print("variable). An effect smaller than this on a set is not readable there.")
    print("=" * 78)
    for label, stem in SETS.items():
        a, b = load(stem, b42), load(stem, b7)
        if not (a and b):
            continue
        ib = {r["id"]: r for r in b}
        flips = sum(1 for r in a
                    if r["id"] in ib and fully_ok(r) != fully_ok(ib[r["id"]]))
        print(f"  {label:<14}{flips:>3} of {len(a):>3} cases flip on seed alone"
              f"   headline {tally(a)['fully']} -> {tally(b)['fully']}")

    # ---- the stated prediction --------------------------------------------
    print("\n" + "=" * 78)
    print("THE PREDICTION: false alarms on the held-out extract cases -> ~0")
    print("=" * 78)
    cols = [(b42, load("basic_bench", b42)), (b7, load("basic_bench", b7)),
            (n42, load("basic_bench", n42)), (n7, load("basic_bench", n7))]

    def cell(rows, cid):
        if rows is None:
            return "-"
        r = next((x for x in rows if x["id"] == cid), None)
        return "?" if r is None else ("ALARM" if r.get("false_alarm") else "quiet")

    print(f"{'case':<22}" + "".join(f"{name:>12}" for name, _ in cols))
    for cid in HELD:
        line = f"{cid:<22}" + "".join(f"{cell(rows, cid):>12}" for _, rows in cols)
        print(line + ("  <- STABLE TARGET" if cid in STABLE_TARGET
                      else "  (seed-unstable)"))
    print("\nCONTROL - stable false alarms that are NOT extract-shaped. These must")
    print("NOT move; if they do, the model got globally timid rather than better at")
    print("this shape, which predicts a matching recall cost on the buggy sets.")
    for cid in sorted(CONTROL):
        print(f"{cid:<22}" + "".join(f"{cell(rows, cid):>12}" for _, rows in cols))
    print()


if __name__ == "__main__":
    main()
