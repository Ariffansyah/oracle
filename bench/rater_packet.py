"""A blinded packet for a second rater, and the agreement number it produces.

Every mechanism figure in this project has exactly one rater. For a claim that
is entirely about explanation quality, that is the weakest evidence supporting
the strongest claim, and it is the cheapest of the remaining gaps to close:
inter-rater agreement on 20 cases is an afternoon of someone else's time.

The packet is blinded on purpose. It shows the diff and the model's answer, and
it withholds two things:

  * `meta.json`'s `note`, which states the true mechanism outright. A rater who
    reads it is checking the model against an answer key rather than against the
    program, and will agree with rater one for the wrong reason.
  * rater one's grade, for the same reason.

What it *does* give is the command to run each side, because a mechanism claim
that was not executed is not graded here - that discipline is the whole point of
the benchmark and it applies to the humans too.

    python bench/rater_packet.py --emit  data/basic_bench_oracle46.jsonl
    python bench/rater_packet.py --score rater2.csv

Rater one's grades below are transcribed from `docs/RESULTS.md`, "The hand-grade
(25 Aug): 31/46, not 41/46", which names all 15 non-clean cases explicitly; the
other 31 are locus+mechanism correct by that table's own arithmetic.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# right locus, wrong or inverted causal claim
R1_MECHANISM = {
    "c-int-division", "c-strcpy-bound", "go-accum-reset", "php-concat-operator",
    "py-dict-mutate", "rb-string-mutate", "rs-int-division", "rs-overflow",
    "ts-reduce-empty", "py-pop-guard",
}
# wrong outright
R1_WRONG = {
    "go-nil-map", "java-concurrent-modify", "js-reverse-index",
    "py-annotate-only", "rs-rename-local",
}

GRADES = ("locus", "mechanism", "wrong")


def rater_one(case_id: str) -> str:
    if case_id in R1_MECHANISM:
        return "mechanism"
    if case_id in R1_WRONG:
        return "wrong"
    return "locus"


def emit(rows_path: Path, n: int, seed: int, out: Path) -> None:
    from bench.basic_bench import diff_of, load_cases

    cases = {c["id"]: c for c in load_cases()}
    rows = [json.loads(l) for l in rows_path.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r["id"] in cases]
    rng = random.Random(seed)
    rng.shuffle(rows)
    picked = rows[:n]

    lines = [
        "# Second-rater packet",
        "",
        f"{len(picked)} cases drawn from `{rows_path.name}` with seed {seed}.",
        "",
        "For each case, decide what the model's explanation got right:",
        "",
        "- **locus** — names the right construct AND the causal claim is true",
        "- **mechanism** — names the right construct, but the stated cause is",
        "  wrong, inverted, or names the wrong error",
        "- **wrong** — neither",
        "",
        "**Run both sides before grading a mechanism claim.** Each case gives the",
        "command. If you did not execute it, leave the grade blank rather than",
        "guess — a blank is data, a guess is noise.",
        "",
        "Record answers as `case_id,grade` in a CSV, then:",
        "",
        "    python bench/rater_packet.py --score rater2.csv",
        "",
        "---",
        "",
    ]
    for r in picked:
        c = cases[r["id"]]
        pred = r.get("predicted") or {}
        findings = pred.get("findings") or []
        lines.append(f"## `{c['id']}`  ({c['language']})\n")
        lines.append(f"Run it:  `cd bench/basic/{c['id']} && "
                     f"<run> pre.{c['ext']}` then the same for `post.{c['ext']}`\n")
        lines.append("```diff")
        lines.append(diff_of(c).strip())
        lines.append("```\n")
        lines.append(f"**Model summary:** {pred.get('summary', '(none)')}\n")
        if findings:
            for j, f in enumerate(findings, 1):
                lines.append(f"**Finding {j}** ({f.get('category')}): "
                             f"{f.get('explanation')}\n")
        else:
            lines.append("**Findings:** none reported\n")
        lines.append(f"`{c['id']}` grade: ______\n")
        lines.append("---\n")
    out.write_text("\n".join(lines))
    print(f"{len(picked)} cases -> {out}")
    print("Blinded: meta.json notes and rater one's grades are not in the file.")


def score(csv_path: Path) -> int:
    pairs: list[tuple[str, str]] = []
    skipped = 0
    with open(csv_path) as fh:
        for row in csv.reader(fh):
            if len(row) < 2 or not row[0].strip() or row[0].startswith("#"):
                continue
            cid, g = row[0].strip(), row[1].strip().lower()
            if not g:
                skipped += 1
                continue
            if g not in GRADES:
                raise SystemExit(f"{cid}: grade {g!r} not one of {GRADES}")
            pairs.append((rater_one(cid), g))
    if not pairs:
        raise SystemExit(f"no filled grades in {csv_path}")

    n = len(pairs)
    agree = sum(a == b for a, b in pairs)
    po = agree / n
    # Cohen's kappa: agreement above what the two raters' marginals predict.
    pe = sum((sum(a == g for a, _ in pairs) / n) *
             (sum(b == g for _, b in pairs) / n) for g in GRADES)
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0

    print(f"{n} cases graded by both ({skipped} left blank)")
    print(f"  raw agreement   {agree}/{n} = {po:.1%}")
    print(f"  Cohen's kappa   {kappa:.3f}")
    print("\n  confusion (rows = rater one, cols = rater two):")
    print("            " + "".join(f"{g:>11}" for g in GRADES))
    for a in GRADES:
        cells = "".join(f"{sum(1 for x, y in pairs if x == a and y == g):>11}"
                        for g in GRADES)
        print(f"  {a:<10}{cells}")
    if kappa < 0.6:
        print("\n  kappa below 0.6 is weak agreement — the disagreements are the "
              "\n  interesting data, not a problem to average away. Read them.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emit", type=Path, metavar="ROWS.jsonl")
    ap.add_argument("--score", type=Path, metavar="RATER2.csv")
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20260826)
    ap.add_argument("--out", type=Path, default=ROOT / "data/rater_packet.md")
    args = ap.parse_args(argv)

    if args.score:
        return score(args.score)
    if args.emit:
        emit(args.emit, args.n, args.seed, args.out)
        return 0
    ap.error("give --emit ROWS.jsonl or --score RATER2.csv")


if __name__ == "__main__":
    sys.exit(main())
