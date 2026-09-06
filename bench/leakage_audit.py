"""Count language-foreign vocabulary in answers about a given language.

    python bench/leakage_audit.py --tags v6 v6_seed7
    python bench/leakage_audit.py --tags v6 v7 --show

Why this exists
---------------
On 1 Sep, `sft-v6-suggest-seed7` reviewing a PYTHON diff suggested checking
"that zero comes back instead of Infinity". `Infinity` is JavaScript: Python
raises on `min([])` and has no such value. The corpus explains it - `Infinity`
appears in 9 of 366 v6 targets, all from `js-math-min-empty`, which was the ONLY
case teaching the empty-guard mechanism with that observable.

That is a corpus-coverage hypothesis, and it makes a prediction: give each
language its own case for each mechanism and the borrowed vocabulary should
fall. v7 does that - 366 -> 474 records, py/js/java 51% -> 62%, nine new
execute-verified cases. This measures whether the prediction holds.

The metric
----------
For every answer, take the language of the CASE it reviews, then count terms
that belong to a different language. Terms are chosen to be unambiguous: a token
that simply cannot appear in correct prose about the case's language.

  `Infinity` in a Python answer          leakage
  `ValueError` in a JavaScript answer    leakage
  `NullPointerException` in a Python answer   leakage
  `null` anywhere                        NOT counted - it is real in JS, Java,
                                         PHP and Ruby prose, so it separates
                                         nothing

This is deliberately narrow. It undercounts - paraphrased leakage ("returns
positive infinity") is invisible to it - so a fall here is evidence and a flat
line is not proof of absence.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

# Unambiguous per-language vocabulary. Each term must be impossible in correct
# prose about another language, which is why `null`, `NaN` (JS and Java both),
# `TypeError` (Python and JS both) and `int` are absent.
MARKERS = {
    "javascript": [r"\bInfinity\b", r"\bundefined\b", r"\bMath\.\w+", r"===",
                   r"\bconsole\.log\b", r"\btypeof\b", r"\bNumber\.\w+"],
    "python": [r"\bValueError\b", r"\bZeroDivisionError\b", r"\bIndexError\b",
               r"\bAttributeError\b", r"\bNone\b", r"\b__\w+__\b",
               r"\bdef \w+", r"\bself\b"],
    "java": [r"\bNullPointerException\b", r"\bArrayList\b", r"\bSystem\.out\b",
             r"\bConcurrentModificationException\b", r"\bNoSuchElementException\b",
             r"\bArithmeticException\b", r"\bInteger\.\w+", r"\bCollections\.\w+"],
}
# CASE-SENSITIVE, all of them. These are identifiers, and folding case made
# `\bMath\.\w+` match Python's own `math.floor` - a correct Python term scored
# as JavaScript leakage. That inflated the v6 baseline from ~0 to 7%.
COMPILED = {L: [re.compile(p) for p in pats] for L, pats in MARKERS.items()}

SETS = {"basic": ("basic_bench", "bench/basic"),
        "mech_heldout": ("heldout_mech", "bench/mechanism_heldout"),
        "clean_heldout": ("heldout_clean", "bench/clean_heldout")}


def case_langs(root: str) -> dict:
    out = {}
    for d in sorted(glob.glob(str(ROOT / root) + "/*/")):
        m = os.path.join(d, "meta.json")
        if os.path.exists(m):
            out[os.path.basename(d.rstrip("/"))] = json.load(open(m)).get("language")
    return out


def prose(row: dict) -> str:
    p = row.get("predicted") or {}
    parts = [p.get("summary") or "", ((p.get("effect") or {}).get("check") or "")]
    parts += [f.get("explanation") or "" for f in (p.get("findings") or [])]
    return "\n".join(parts)


def foreign_hits(text: str, own: str) -> list[str]:
    """Markers of languages OTHER than `own` occurring in the text."""
    hits = []
    for lang, pats in COMPILED.items():
        if lang == own:
            continue
        for p in pats:
            for m in p.finditer(text):
                hits.append(f"{lang}:{m.group(0)}")
    return hits


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--show", action="store_true", help="list every leaked term")
    args = ap.parse_args()

    print(f"\n{'run':<12}{'set':<15}{'answers':>8}{'scored':>8}"
          f"{'w/ leak':>9}{'terms':>7}   most common")
    print("-" * 78)
    detail = []
    for tag in args.tags:
        tot_ans = tot_scored = tot_leak = tot_terms = 0
        for label, (stem, root) in SETS.items():
            p = DATA / f"{stem}_{tag}.jsonl"
            if not p.exists():
                continue
            langs = case_langs(root)
            rows = [json.loads(l) for l in open(p) if l.strip()]
            c: Counter = Counter()
            n_leak = n_scored = 0
            for r in rows:
                own = langs.get(r["id"])
                # Only the three languages have marker sets; a Ruby or Rust case
                # has nothing to be foreign TO, so it is not scored.
                if own not in MARKERS:
                    continue
                n_scored += 1
                hits = foreign_hits(prose(r), own)
                if hits:
                    n_leak += 1
                    c.update(hits)
                    detail.append((tag, label, r["id"], own, hits))
            top = f"{c.most_common(1)[0][0]} x{c.most_common(1)[0][1]}" if c else "-"
            print(f"{tag:<12}{label:<15}{len(rows):>8}{n_scored:>8}"
                  f"{n_leak:>9}{sum(c.values()):>7}   {top}")
            tot_ans += len(rows); tot_scored += n_scored
            tot_leak += n_leak; tot_terms += sum(c.values())
        rate = f"{100*tot_leak/tot_scored:.0f}%" if tot_scored else "-"
        print(f"{tag:<12}{'TOTAL':<15}{tot_ans:>8}{tot_scored:>8}"
              f"{tot_leak:>9}{tot_terms:>7}   {rate} of scored answers leak\n")

    if args.show:
        print(f"\n{'run':<11}{'set':<14}{'case':<26}{'lang':<12}leaked")
        for tag, label, cid, own, hits in detail:
            print(f"  {tag:<11}{label:<14}{cid[:24]:<26}{own:<12}{', '.join(sorted(set(hits)))}")


if __name__ == "__main__":
    main()
