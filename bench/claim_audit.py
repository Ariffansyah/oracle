"""Find the concrete claims in stored answers and execute the ones that can be.

    python bench/claim_audit.py --tags v6 v6_seed7
    python bench/claim_audit.py --tags v6_seed7 --show      # list every claim

Why this exists
---------------
v3 dropped `effect.before` / `effect.after` because the model cannot know a
concrete value: 15-31% right across four checkpoints, with 69-85% of answers
carrying a claim that running the code contradicts. The field is gone from the
corpus - 0 of 366 v6 targets populate either - but the CLAIM is not. It moved
into the prose, where no metric reads it:

    "count_positive([1, -2, 3]) returns 2 instead of 1"   (TestJIT, 1 Sep)
    "sum_to(5) returns 15 instead of 15"                  (TestJIT, 1 Sep)

`bench/template_audit.py` could not see `effect.check` and that is how a 97%
template reached a training run. This is the same shape of blind spot one field
further on, so it gets its own script rather than a note in a docstring.

The columns
-----------
`with claim`   answers asserting at least one `f(args) -> value`
`verified`     the call was replayed and matched
`CONTRA`       replayed and did NOT match - a claim the code contradicts
`degenerate`   "N instead of N": asserts a change between two identical values.
               Needs no execution and no language support, so this column is
               comparable across every case in the corpus.
`incoherent`   "X instead of Y" about a callee the diff ADDS. There is no prior
               value, so the comparison is false whatever X is - and X is often
               RIGHT, which is why a value check alone cannot catch it. Reads 0
               on every stored run below: it takes a commit that introduces a
               function, and the benchmark has no such clean Python case. It
               fires on TestJIT/pyalgo 30dab2fd, which is where it came from.
`unverifiable` no Python source to run it against. NOT a mark against the model:
               most bench cases are C/Go/Java/JS/PHP/Ruby/Rust/TS, and a real
               commit would need its repo checked out at that revision.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

from llm_explainer.verify import (CONTRADICTED, DEGENERATE, INCOHERENT,
                                  UNVERIFIABLE, VERIFIED, check_against_diff,
                                  check_answer, extract_claims, prose_of)

SETS = {"basic": ("basic_bench", "bench/basic"),
        "mech_heldout": ("heldout_mech", "bench/mechanism_heldout"),
        "clean_heldout": ("heldout_clean", "bench/clean_heldout")}


def cases(root: str) -> dict:
    out = {}
    for d in sorted(glob.glob(str(ROOT / root) + "/*/")):
        meta = os.path.join(d, "meta.json")
        if not os.path.exists(meta):
            continue
        j = json.load(open(meta))
        post = os.path.join(d, f"post.{j.get('ext', '')}")
        pre = os.path.join(d, f"pre.{j.get('ext', '')}")
        j["post"] = open(post).read() if os.path.exists(post) else None
        # The pre-commit side is what makes `incoherent` detectable: a callee
        # the change INTRODUCES has no prior value for an "instead of" claim.
        j["pre"] = open(pre).read() if os.path.exists(pre) else None
        out[os.path.basename(d.rstrip("/"))] = j
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--show", action="store_true", help="list every claim found")
    args = ap.parse_args()

    print(f"\n{'run':<12}{'set':<15}{'answers':>8}{'w/ claim':>9}{'verified':>9}"
          f"{'CONTRA':>8}{'degen':>7}{'incoh':>7}{'unverif':>8}")
    print("-" * 83)
    found = []
    for tag in args.tags:
        for label, (stem, root) in SETS.items():
            p = DATA / f"{stem}_{tag}.jsonl"
            if not p.exists():
                continue
            cs = cases(root)
            rows = [json.loads(l) for l in open(p) if l.strip()]
            ct: collections.Counter = collections.Counter()
            with_claim = 0
            for r in rows:
                c = cs.get(r["id"]) or {}
                py = c.get("language") == "python"
                code = c["post"] if py and c.get("post") else None
                rep = check_answer(r.get("predicted") or {}, code,
                                   pre_code=c.get("pre") if py else None)
                if rep.claims:
                    with_claim += 1
                for cl in rep.claims:
                    ct[cl.status] += 1
                    found.append((tag, label, r["id"], cl))
            print(f"{tag:<12}{label:<15}{len(rows):>8}{with_claim:>9}"
                  f"{ct[VERIFIED]:>9}{ct[CONTRADICTED]:>8}{ct[DEGENERATE]:>7}"
                  f"{ct[INCOHERENT]:>7}{ct[UNVERIFIABLE]:>8}")

        # real commits: no checkout, so only the language-independent columns mean
        # anything here.
        p = DATA / f"real_commits_{tag}.jsonl"
        if p.exists():
            rows = [json.loads(l) for l in open(p) if l.strip()]
            ct = collections.Counter()
            with_claim = 0
            for r in rows:
                # No checkout, but both sides of the diff are in the row, so
                # degenerate and incoherent are still decidable here.
                rep = check_against_diff(r.get("predicted") or {}, r["diff"])
                if rep.claims:
                    with_claim += 1
                for cl in rep.claims:
                    ct[cl.status] += 1
                    found.append((tag, "real_commits", r["rev"][:12], cl))
            print(f"{tag:<12}{'real_commits':<15}{len(rows):>8}{with_claim:>9}"
                  f"{ct[VERIFIED]:>9}{ct[CONTRADICTED]:>8}{ct[DEGENERATE]:>7}"
                  f"{ct[INCOHERENT]:>7}{ct[UNVERIFIABLE]:>8}")

    tot = collections.Counter(c.status for *_, c in found)
    print(f"\ntotal claims {len(found)}: verified {tot[VERIFIED]}, "
          f"contradicted {tot[CONTRADICTED]}, degenerate {tot[DEGENERATE]}, "
          f"incoherent {tot[INCOHERENT]}, unverifiable {tot[UNVERIFIABLE]}")

    if args.show:
        print(f"\n{'run':<11}{'set':<14}{'case':<28}claim")
        for tag, label, cid, c in found:
            inst = f"  (instead of {c.instead_of})" if c.instead_of else ""
            act = f"  ACTUAL={c.actual}" if c.actual is not None else ""
            print(f"  {c.status.upper():<13}{tag:<11}{label:<14}{cid[:26]:<28}"
                  f"{c.call} -> {c.claimed}{inst}{act}")


if __name__ == "__main__":
    main()
