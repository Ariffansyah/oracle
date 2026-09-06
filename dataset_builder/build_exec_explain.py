"""Turn the executed value corpus into a COMPUTE-THEN-EXPLAIN corpus.

    python -m dataset_builder.build_exec_explain --audit
    python -m dataset_builder.build_exec_explain --out data/exec_explain.jsonl

Why this exists
---------------
`gen_exec_corpus.py --sft` trains values and nothing else: the target is
`{"differs", "before", "after"}`, so the checkpoint it produces cannot fill the
`summary`/`findings` contract the benches score or the `effect` block the TUI
draws. It computes, but it does not explain.

This builder keeps the computation and appends the prose AFTER it, in one
target, in that order:

    {"differs": true, "before": "105", "after": "91",
     "effect": {"trigger": "aggregate(14)",
                "check": "run aggregate(14): 105 before, 91 after"}}

Order is the mechanism, not a formatting choice. The values are emitted first,
so every prose token is conditioned on numbers the model has already committed
to. Prose-first is how the 1 Sep hand-grade got 18 of its 32 wrong findings:
10 `contradicted` and 8 `inverted` are before/after values invented to fit a
sentence that was already written.

`differs: false` carries `effect: null` -- no finding at all. That is the false
alarm suppressed IN the target rather than by `bench/exec_filter.py` after the
fact, so the model learns the restraint instead of having it imposed.

On templating
-------------
`changed` ("range(1, n + 1) -> range(1, n)") stays untrained here for the same
reason `gen_exec_corpus` refuses it: one string per family teaches diff-shape ->
phrase. Both prose fields here are built only from things that VARY per sample --
the driver call, and the two executed values. The sentence frame is shared, but
the frame alone says nothing: it cannot be produced without computing the values
that fill it. The audit below reports distinctness per family so that claim is
checked rather than asserted.
"""
import argparse, collections, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

SYSTEM = """You are ORACLE. You are given one commit diff of a program that \
prints a result.

COMPUTE FIRST, THEN EXPLAIN. Work out what the program printed before this \
commit and what it prints after. Only then describe it. Answer with one JSON \
object, in this order:

  "differs"  true if the two versions print different output, else false
  "before"   exactly what the pre-commit version printed
  "after"    exactly what the post-commit version printed
  "effect"   null if "differs" is false. Otherwise an object:
               "trigger"  the call that exposes the difference
               "check"    how to see it, naming both values

If the program raises, give the exception type and message. Every value in \
"effect" must be one you derived above; do not name a call or a number you did \
not compute. If nothing changed, say so and stop -- "effect" is null."""

USER = """## Changes
```diff
{diff}
```"""

CALL = re.compile(r"print\(")


def driver_call(diff: str) -> str | None:
    """The last `print(...)` in the diff, balanced. `_drv` appends the driver at
    the end of the file, so with full diff context this is the call whose output
    the model must predict. With the generator's old n=3 context it is missing
    from 22% of rows -- build the corpus with --context large."""
    ms = list(CALL.finditer(diff))
    if not ms:
        return None
    i = ms[-1].end()
    depth, j = 1, i
    while j < len(diff) and depth:
        depth += (diff[j] == "(") - (diff[j] == ")")
        j += 1
    return diff[i:j - 1].strip() or None


def target(row: dict, call: str) -> dict:
    """Values first, prose second, and no prose at all when nothing changed."""
    differs = row["differs"] if isinstance(row["differs"], bool) else \
              json.loads(row["messages"][-1]["content"])["differs"]
    said = json.loads(row["messages"][-1]["content"])
    before, after = said["before"], said["after"]
    out = {"differs": differs, "before": before, "after": after}
    if not differs:
        out["effect"] = None
    else:
        # Both fields carry only per-sample facts: the call, and the two values.
        out["effect"] = {"trigger": call,
                         "check": f"run {call}: {before} before, {after} after"}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=pathlib.Path,
                    default=ROOT / "data/exec_sft_ctx.jsonl",
                    help="values-only corpus; its _holdout_* siblings come too")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "data/exec_explain.jsonl")
    ap.add_argument("--audit", action="store_true", help="print, write nothing")
    ap.add_argument("--min-call-rate", type=float, default=1.0, metavar="R",
                    help="refuse to write if fewer than this fraction of rows "
                         "expose their driver call (default 1.0: all of them)")
    ap.add_argument("--min-distinct-check", type=float, default=0.5, metavar="R",
                    help="refuse if distinct `check` strings fall below this "
                         "fraction of positives -- the templating tripwire")
    ap.add_argument("--max-per-target", type=int, default=4, metavar="K",
                    help="keep at most K rows sharing one exact target. Five "
                         "families return a BOOLEAN or a fixed guard value, so "
                         "randomising their inputs does not move the output: "
                         "115/1095 rows carry one constant answer per family, "
                         "which is memorisable without computing anything.")
    args = ap.parse_args()

    splits = [("", args.src)] + [
        (s, args.src.with_name(args.src.stem + s + args.src.suffix))
        for s in ("_holdout_within", "_holdout_cross")]

    built, stats = {}, {}
    for name, path in splits:
        if not path.exists():
            sys.exit(f"FAILED: {path} does not exist")
        rows = [json.loads(l) for l in open(path)]
        out, nocall = [], 0
        for r in rows:
            diff = r["messages"][1]["content"]
            call = driver_call(diff)
            if call is None:
                nocall += 1
                continue
            t = target(r, call)
            out.append({"messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": USER.format(diff=diff)},
                {"role": "assistant", "content": json.dumps(t, ensure_ascii=False)},
            ], "family": r["family"], "category": r["category"],
                "differs": t["differs"]})
        # Cap identical targets so a family with a constant answer cannot be
        # learned by recognising the family. Deterministic: input order.
        seen, capped = collections.Counter(), []
        for r in out:
            key = (r["family"], r["messages"][-1]["content"])
            if seen[key] >= args.max_per_target:
                continue
            seen[key] += 1
            capped.append(r)
        built[name] = capped
        stats[name] = (len(rows), nocall, len(out) - len(capped))

    # ---- gates that refuse to write -------------------------------------
    for name, (n, nocall, dup) in stats.items():
        rate = (n - nocall) / n if n else 0
        tag = name or "train"
        print(f"  {tag:16} {n:5} rows   driver call visible {rate:5.1%}"
              f"   no-call {nocall}   over-cap dropped {dup}")
        if rate < args.min_call_rate:
            sys.exit(f"FAILED: {tag} exposes the driver call in only {rate:.1%} "
                     f"of rows. Rebuild the source with "
                     f"`gen_exec_corpus.py --context 400`: at the default n=3 "
                     f"the diff hides the call and before/after are not "
                     f"derivable from the input at all.")

    print()
    for name, rows in built.items():
        tag = name or "train"
        pos = [r for r in rows if r["differs"]]
        checks = {json.loads(r["messages"][-1]["content"])["effect"]["check"]
                  for r in pos}
        ratio = len(checks) / len(pos) if pos else 1.0
        nulls = len(rows) - len(pos)
        print(f"  {tag:16} {len(rows):5}   positives {len(pos):4} "
              f"({100*len(pos)//max(len(rows),1)}%)   effect:null {nulls:4}   "
              f"distinct `check` {ratio:.0%}")
        if ratio < args.min_distinct_check:
            sys.exit(f"FAILED: {tag} has {ratio:.0%} distinct `check` strings. "
                     f"Prose that repeats across samples is prose the model can "
                     f"emit without computing anything.")

    # Per-family tripwire: one family whose prose never varies is the recitation
    # failure in miniature, and the aggregate ratio above can hide it.
    worst = []
    for name, rows in built.items():
        byfam = collections.defaultdict(set)
        for r in rows:
            if not r["differs"]:
                continue
            byfam[r["family"]].add(
                json.loads(r["messages"][-1]["content"])["effect"]["check"])
        for fam, cs in byfam.items():
            worst.append((len(cs), fam, name or "train"))
    worst.sort()
    print(f"\n  least varied families: "
          + ", ".join(f"{f}={n}" for n, f, _ in worst[:4]))
    # After capping, a family may legitimately hold one constant target -- but
    # only up to --max-per-target rows of it. More than that is recitation.
    for name, rows in built.items():
        byfam = collections.Counter(r["family"] for r in rows if r["differs"])
        dist = collections.defaultdict(set)
        for r in rows:
            if r["differs"]:
                dist[r["family"]].add(r["messages"][-1]["content"])
        for fam, cnt in byfam.items():
            if len(dist[fam]) == 1 and cnt > args.max_per_target:
                sys.exit(f"FAILED: {fam} keeps {cnt} rows of ONE target after "
                         f"capping at {args.max_per_target} — that is a "
                         f"template, not an explanation.")

    if args.audit:
        print("\n  --- three targets ---")
        for r in built[""][:2] + [x for x in built[""] if not x["differs"]][:1]:
            print("   ", r["messages"][-1]["content"])
        print("\n  audit only, nothing written")
        return

    for name, rows in built.items():
        path = args.out.with_name(args.out.stem + name + args.out.suffix)
        with open(path, "w") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"-> {path}  ({len(rows)})")


if __name__ == "__main__":
    main()
