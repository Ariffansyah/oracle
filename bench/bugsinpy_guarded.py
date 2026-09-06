"""The deployed review path, scored on the same rows as the raw arms.

`bench/eval_bugsinpy_arms.py` measures the MODEL: a bare one-key prompt, no
guards, whatever comes out is the answer. That is the right instrument for the
ablation, and it is not what anybody actually reads. What the TUI prints goes
through `oracle_reviewer/core.explain`, which:

  * uses core's own prompt, with the file, the command, and the measured
    before/after laid out as `USER` in core.py
  * rejects the whole answer when the model reports the two runs the wrong way
    round (`swapped`, `contradiction`)
  * then drops SENTENCE BY SENTENCE anything that fails `verify` -- an invented
    number, a claimed removal the diff does not contain, a consequence the run
    never measured
  * prints the measured before/after underneath regardless

So the reviewer withholds prose it cannot support, and the difference between
this and the raw arm is the whole contribution of that guard layer -- which has
never been measured, and which is the likeliest explanation for a hand-test
finding every answer valid while the raw model is grounded 50% of the time.

Two numbers come out that the raw arms cannot produce:

    grounded    same rubric as the arms, on the prose the developer READS
    withheld    how often the guard suppressed something, and why

A withheld explanation is not a failure. It is the tool declining to say
something it cannot support, which is the behaviour the guards exist to produce
-- but it is also prose the developer does not get, so it is counted, not hidden.

Needs the reviewer served (`./serve.sh start`), because it asks the model the
same way the app does.

    python bench/bugsinpy_guarded.py --out data/bip_guarded.json
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bench.eval_bugsinpy_arms import (  # noqa: E402
    diff_of, from_commit_message, invents_exception, names_symbol,
    quotes_signature)
from oracle_reviewer import core  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=pathlib.Path,
                    default=ROOT / "data/bugsinpy_rows_v1.jsonl")
    ap.add_argument("--host", default="http://localhost:8111")
    ap.add_argument("--model", default="oracle-reviewer-3b")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "data" / "bip_guarded.json")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.dataset)]
    if args.limit:
        rows = rows[:args.limit]

    out_rows = []
    n = collections.Counter()
    for i, row in enumerate(rows, 1):
        diff = diff_of(row["messages"][1]["content"])
        # A reproduced BugsInPy bug is exactly core's case 2: the run was
        # failing at the parent and starts passing after the change. That case
        # did not exist in the SYSTEM prompt until the 5 Sep guarded run
        # measured what its absence cost -- 71 of 458 answers asserting the
        # behaviour had not changed, on rows where a test proves it had.
        if row["differs"]:
            risk = "fixes"
            outcome = "the run started PASSING after this change"
        else:
            risk = "none"
            outcome = "the run behaved the same before and after"
        r = core.FileReview(
            path=(row["patch_files"] or ["?"])[0], risk=risk, diff=diff,
            before=row["before"], after=row["after"])
        cmd = (row["run_test"] or ["the project's test"])[0]
        core.explain(args.host, args.model, r, row.get("subject", ""), cmd,
                     outcome)

        expl, exc = r.explanation, row["exception"]
        exc_ok = bool(expl) and bool(exc) and exc in expl
        sig_ok = bool(expl) and quotes_signature(expl, row["before"])
        inv = invents_exception(expl, exc, row["before"]) if expl else None
        sym = bool(expl) and names_symbol(expl, diff)
        grounded = bool((exc_ok or sig_ok) and not inv)

        n["spoke"] += bool(expl)
        n["withheld"] += bool(r.withheld)
        n["withheld_all"] += bool(r.withheld and not expl)
        n["exception"] += exc_ok
        n["signature"] += sig_ok
        n["symbol"] += sym
        n["invented"] += bool(inv)
        n["grounded"] += grounded
        out_rows.append({
            "id": row["id"], "project": row["project"], "exception": exc,
            "before": row["before"], "explanation": expl[:800],
            "withheld": r.withheld, "names_exception": exc_ok,
            "quotes_signature": sig_ok, "invented": inv,
            "from_message": bool(inv) and from_commit_message(
                expl, row.get("subject", ""), exc),
            "names_symbol": sym})
        if i % 20 == 0:
            print(f"  {i}/{len(rows)}", flush=True)

    tot = len(rows)
    pct = lambda a: f"{a}/{tot} ({a / tot:.0%})"
    print(f"\n=== guarded (the prose the TUI prints)  n={tot}")
    print(f"  said anything at all         {pct(n['spoke'])}")
    print(f"  something was withheld       {pct(n['withheld'])}")
    print(f"    ...the whole explanation   {pct(n['withheld_all'])}")
    print(f"  names the real exception     {pct(n['exception'])}")
    print(f"  quotes the real message      {pct(n['signature'])}")
    print(f"  names a changed identifier   {pct(n['symbol'])}")
    print(f"  INVENTS a different failure  {pct(n['invented'])}")
    print(f"  GROUNDED                     {pct(n['grounded'])}")
    spoke = n["spoke"] or 1
    print(f"\n  of the {n['spoke']} it DID explain, grounded "
          f"{n['grounded']}/{n['spoke']} ({n['grounded'] / spoke:.0%}) "
          f"and invented {n['invented']}/{n['spoke']} "
          f"({n['invented'] / spoke:.0%})")
    why = collections.Counter()
    for r in out_rows:
        if r["withheld"]:
            why[r["withheld"][:70]] += 1
    if why:
        print("\n  what the guard dropped, most common first:")
        for w, c in why.most_common(8):
            print(f"    {c:>4}  {w}")
    args.out.write_text(json.dumps({"arm": "guarded", "counts": dict(n),
                                    "n": tot, "rows": out_rows}, indent=1))
    print(f"\n  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
