"""Pre-grade real-commit answers on the classes a machine can decide.

    python bench/grade_real.py --tags v7
    python bench/grade_real.py --tags v7 repair --show

Why this exists
---------------
The 1 Sep grade of the 40 real commits was done entirely by hand, because
`bench/claim_audit.py` reads `f(args) -> value` claims and real-commit answers
carry almost none: ONE answer in 40 across three checkpoints. Thirty wrong
findings were found by eye.

Two of the six taxonomy classes do not need a human, and both were among the
largest in that grade:

  no-such-entity   the finding names an identifier, operator or literal that
                   does not occur in the diff the model was shown. 8 of 32 in
                   the v7 grade. Decidable by string search, and it is the same
                   invariant `dataset_builder/filter_repair_targets.py` enforces
                   on the corpus - so the model is now measured against the rule
                   it was trained on.

  incoherent       a defect asserted about a symbol this diff INTRODUCES. If
                   every occurrence of the name is on an added line, there is no
                   prior behaviour for the change to have broken. 4 of 32 in the
                   v7 grade, and none of them was a whole new file - they were
                   symbols added inside existing files (`NonEmptyStringValueParser`,
                   `AbortWithStatusPureJSON`), so a new-file rule cannot see them.

The other four - `contradicted`, `inverted`, `partial`, `confirmed correct` -
need someone to read the code, and this script leaves them blank rather than
guessing. It narrows the hand-grade; it does not replace it.

A pre-grade of `unjudged` is not a pass. It means no rule fired.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

# Backticked spans are what the contracts ask the model to quote, so they are
# the claims it is accountable for. Prose without backticks is not scored here.
QUOTED = re.compile(r"`([^`\n]{2,80})`")
# Identifier-shaped only: skip prose fragments and whole phrases.
IDENTISH = re.compile(r"^[A-Za-z_$][\w$.]*(\(\))?$")


def introduced(diff: str, name: str) -> bool:
    """True if `name` occurs ONLY on added lines - this diff brings it into being.

    Context lines matter as much as removed ones: a symbol visible in the
    surrounding three lines of context already existed, so a claim about it is
    not incoherent even though the diff does not remove it.
    """
    on_added = on_other = False
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "@@", "diff --git", "index ")):
            continue
        if name not in line:
            continue
        if line.startswith("+"):
            on_added = True
        else:                      # context or removed
            on_other = True
    return on_added and not on_other


def grade_one(pred: dict, diff: str) -> list[tuple[str, str, str]]:
    """(finding_ref, class, evidence) for every finding a rule fires on."""
    out = []
    for i, f in enumerate(pred.get("findings") or []):
        expl = f.get("explanation") or ""
        # no-such-entity: a quoted identifier absent from the diff
        missing = [q for q in QUOTED.findall(expl)
                   if IDENTISH.match(q) and q.rstrip("()") not in diff]
        if missing:
            out.append((f"f{i}", "no-such-entity",
                        f"names {missing[0]!r}, absent from the diff"))
            continue
        # incoherent: every symbol the finding names is introduced by this diff
        names = [q.rstrip("()") for q in QUOTED.findall(expl) if IDENTISH.match(q)]
        if names and all(introduced(diff, n) for n in names):
            out.append((f"f{i}", "incoherent",
                        f"{names[0]!r} occurs only on added lines; no prior behaviour"))
            continue
        out.append((f"f{i}", "unjudged", "needs a human"))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    print(f"\n{'run':<12}{'commits':>8}{'flagged':>9}{'findings':>10}"
          f"{'no-such-entity':>16}{'incoherent':>12}{'unjudged':>10}")
    print("-" * 78)
    detail = []
    for tag in args.tags:
        p = DATA / f"real_commits_{tag}.jsonl"
        if not p.exists():
            print(f"{tag:<12}  (no {p.name})")
            continue
        rows = [json.loads(l) for l in open(p) if l.strip()]
        ct: Counter = Counter()
        flagged = nfind = 0
        for r in rows:
            pred = r.get("predicted") or {}
            if pred.get("findings"):
                flagged += 1
            nfind += len(pred.get("findings") or [])
            for ref, cls, ev in grade_one(pred, r["diff"]):
                ct[cls] += 1
                if cls != "unjudged":
                    detail.append((tag, r["project"], r["rev"][:9], ref, cls, ev))
        print(f"{tag:<12}{len(rows):>8}{flagged:>9}{nfind:>10}"
              f"{ct['no-such-entity']:>16}{ct['incoherent']:>12}{ct['unjudged']:>10}")

    if args.show and detail:
        print(f"\n{'run':<10}{'project':<26}{'rev':<11}{'':<4}{'class':<16}evidence")
        for tag, proj, rev, ref, cls, ev in detail:
            print(f"  {tag:<10}{proj[:24]:<26}{rev:<11}{ref:<4}{cls:<16}{ev}")


if __name__ == "__main__":
    main()
