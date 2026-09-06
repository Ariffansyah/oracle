"""Turn the teacher-explained corpus into the trainable v2 SFT files.

    python -m dataset_builder.build_exec_sft_v2 --audit

Target field order is load-bearing. `differs`, `before` and `after` are emitted
BEFORE `explanation`, so the values are decoded first and the prose is written
conditioned on them. The other order lets the model write a fluent sentence and
then pick numbers that fit it, which is the fabrication this corpus exists to
stop.

`changed` is deliberately NOT trained on. It is one templated string per family
-- exactly the diff-shape -> phrase recitation this project keeps hitting -- and
the teacher-written `explanation` replaces it.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter

SYSTEM = """You are ORACLE. You are given one commit: its message and its diff.

COMPUTE FIRST, THEN EXPLAIN. Work out what the program printed before this \
commit and what it prints after. The commit message describes what the author \
INTENDED and is often wrong about what the change does -- trust the code, not \
the message.

Answer with one JSON object, with the keys in this order:

  "differs"      true if the two versions print different output, else false
  "before"       exactly what the pre-commit version printed
  "after"        exactly what the post-commit version printed
  "explanation"  one or two sentences for a developer: name the construct that \
changed and say what it does to the output, quoting both values

Work the values out first and let the explanation follow from them. Report only \
what the code determines; do not guess at consequences you cannot derive.

You are also given the OUTCOME of running the project's own test. It is \
measured and it is correct. When it says the output was byte-for-byte \
identical, nothing was established about the change: it may never have reached \
the changed code. Do NOT write that such a change is safe, harmless, cosmetic, \
or that behaviour is unchanged -- say what was edited and what a developer \
should check to settle it."""

USER = """## Commit
{message}

## Changes
```diff
{diff}
```

## Outcome of running the project's own test
{outcome}"""

# Why `outcome` is here and `before`/`after` are not.
#
# The deployed prompt (oracle_reviewer.core.USER) hands the model the measured
# before, the measured after AND an outcome sentence. Training handed it a diff
# alone and asked it to work the values out. The gap that actually bit was the
# outcome: `core.review_commit` case 5 routes EVERY byte-identical result to
# "nothing was established either way", and the model had never seen that string
# in any input, so it fell back on what 709 identical-valued training rows had
# taught it -- "behaviour did not change" -- and the guard withheld it.
#
# Adding `outcome` closes that. Adding `before`/`after` too would close the rest
# of the gap and is the obvious next experiment, but it also deletes the
# property this corpus was built around: with the values supplied, the first
# three target fields become copying and only the prose is learned. The 87%
# bench arm came from a model that had to derive them. So this change is the
# narrow one, and full prompt alignment is left as its own measurement rather
# than smuggled in beside a corpus change.
_OUTCOME_FALLBACK = {
    True: "the run started PASSING after this change",
    False: ("the output is byte-for-byte IDENTICAL. That means either the "
            "changed code never ran, or it ran and changed nothing this "
            "command prints -- which of the two is NOT known. Nothing was "
            "established either way"),
}


def frame(s: str) -> str:
    s = re.sub(r"-?\d+", "N", s)
    s = re.sub(r"\b[a-z_][a-z0-9_]*\b", "ID", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def to_sft(rows: list[dict]) -> list[dict]:
    out = []
    for o in rows:
        target = {"differs": bool(o["differs"]), "before": o["before"],
                  "after": o["after"], "explanation": o["explanation"]}
        out.append({"messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER.format(
                message=o["message"], diff=o["diff"],
                # Corpora generated before the outcome field get the string
                # their label implies, so an old file still builds.
                outcome=o.get("outcome")
                or _OUTCOME_FALLBACK[bool(o["differs"])])},
            {"role": "assistant",
             "content": json.dumps(target, ensure_ascii=False)},
        ], "family": o["family"], "category": o["category"],
            "differs": bool(o["differs"])})
    return out


def audit(name: str, rows: list[dict]) -> list[str]:
    """Everything that has silently rotted a corpus in this project before."""
    bad = []
    n = len(rows)
    fam = {}
    for r in rows:
        fam.setdefault(r["family"], Counter())[bool(r["differs"])] += 1
    pure = [f for f, c in fam.items() if len(c) == 1]
    n_pure = sum(sum(fam[f].values()) for f in pure)
    frames = Counter(frame(r["explanation"]) for r in rows)
    top = frames.most_common(1)[0] if frames else ("", 0)
    pos = sum(1 for r in rows if r["differs"])
    # A value quoted in the prose but never measured is fabrication in the
    # TARGET. Both sides are checked -- except a side whose value is a fixed
    # STATUS rather than a measurement. The pytest-shaped corpus reports `after`
    # as "the test passes" on every fix, and demanding that verbatim flags a
    # correct explanation for writing "the test now passes". The informative
    # side is still required, so an explanation that omits the failure it
    # repaired is still rejected. See teach_exec_explain.SENTINELS.
    from dataset_builder.teach_exec_explain import SENTINELS
    quotable = lambda v: str(v).strip() and str(v).strip().lower() not in SENTINELS
    ungrounded = sum(
        1 for r in rows
        if r["differs"] and ((quotable(r["before"])
                              and str(r["before"]) not in r["explanation"])
                             or (quotable(r["after"])
                                 and str(r["after"]) not in r["explanation"])))
    print(f"\n[{name}] {n} rows, {pos / n:.0%} positive, {len(fam)} families")
    print(f"  single-label families        {len(pure)}/{len(fam)}  "
          f"({n_pure}/{n} rows = {n_pure / n:.0%})")
    print(f"  distinct explanation frames  {len(frames)}/{n} = {len(frames) / n:.2f}"
          f"   (most common x{top[1]})")
    print(f"  ungrounded explanations      {ungrounded}/{n}")
    if n_pure / n > 0.35:
        bad.append(f"{name}: {n_pure / n:.0%} of rows in single-label families")
    if len(frames) / n < 0.55:
        bad.append(f"{name}: {len(frames) / n:.2f} distinct frames — reciting")
    if ungrounded:
        bad.append(f"{name}: {ungrounded} explanations miss a measured value")
    if pos == 0 or pos == n:
        bad.append(f"{name}: single-label split")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=pathlib.Path,
                    default=pathlib.Path("data/exec_explain_v2.jsonl"))
    ap.add_argument("--out", type=pathlib.Path,
                    default=pathlib.Path("data/exec_sft_v2.jsonl"))
    ap.add_argument("--audit", action="store_true",
                    help="report and refuse to write on failure")
    args = ap.parse_args()

    problems = []
    for suffix in ("", "_holdout_within", "_holdout_cross"):
        src = args.src.with_name(args.src.stem + suffix + args.src.suffix)
        if not src.exists():
            sys.exit(f"{src} not found — run teach_exec_explain first")
        rows = [json.loads(l) for l in open(src)]
        problems += audit(suffix or "train", rows)
        dst = args.out.with_name(args.out.stem + suffix + args.out.suffix)
        with open(dst, "w") as fh:
            for o in to_sft(rows):
                fh.write(json.dumps(o, ensure_ascii=False) + "\n")
        print(f"  -> {dst} ({len(rows)})")

    if problems:
        print("\nAUDIT FAILURES:")
        for p in problems:
            print("  !!", p)
        if args.audit:
            return 1
    else:
        print("\naudit clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
