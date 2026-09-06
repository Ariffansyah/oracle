"""Exec corpus whose measured values are PYTEST FAILURES, not printed scalars.

    python -m dataset_builder.gen_exec_pytest --n 6 --out data/exec_pytest.jsonl
    python -m dataset_builder.gen_exec_pytest --n 2 --audit    # print, write nothing

Why this exists
---------------
`gen_exec_corpus` generates programs that PRINT a result, so a training row's
`before` is a string like "27". Measured on 5 Sep, that corpus has a median
`before` of 3 characters against BugsInPy's 55, and its longest value (53) is
below BugsInPy's median. The checkpoint trained on it copies short scalars well
and long failure signatures badly -- the gap that made `sft+strong` fabricate a
signature 20 times where `base+strong` fabricated 11.

So this generator keeps everything that works in `gen_exec_corpus` -- the same
36 families, the same per-sample slot randomisation, the same rule that
EXECUTION decides the label rather than the family's intent -- and changes only
what the program is asked to do. Each pair is run inside a pytest test:

    def test_program():
        with redirect_stdout(buf):
            exec(SOURCE, ns)          # a raise here IS the signature
        assert buf.getvalue().strip() == EXPECTED

which makes pytest's own assertion rewriting produce the two shapes BugsInPy
actually contains, in their natural proportions:

    AssertionError: assert '9' == '27'        a wrong value
    ZeroDivisionError: division by zero       a raise

DIRECTION. BugsInPy rows are fixes: the test fails at the parent and passes
after. So the assertion is pinned to the POST program's output, making `post`
pass by construction and `pre` fail exactly when the two differ. `before` is
then a real failure signature and `after` is "the test passes" -- the same shape
`core.explain` is handed in production, and the same shape the reviewer must
learn to quote from.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import re
import subprocess
import sys
import tempfile
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dataset_builder.gen_exec_corpus import (  # noqa: E402
    FAMILIES, _break, _commit_msg, _preserve, frame, unified)

PASS = "the test passes"

# Quoted from oracle_reviewer/core.py so the corpus trains on the exact string
# the deployed prompt supplies. If either drifts, the model meets an outcome it
# has never seen and falls back on what the values look like -- which is the
# failure this class of row exists to fix.
NOT_EXERCISED = ("the output is byte-for-byte IDENTICAL. That means either "
                 "the changed code never ran, or it ran and changed nothing "
                 "this command prints -- which of the two is NOT known. "
                 "Nothing was established either way")
FIXED_IT = "the run started PASSING after this change"

# The harness the generated program is executed inside. `exec` rather than a
# subprocess so a raise surfaces as pytest's own one-line signature instead of
# a CalledProcessError wrapping a traceback.
HARNESS = '''import contextlib, io, pathlib

SOURCE = pathlib.Path(__file__).with_name("prog.py").read_text()
EXPECTED = {expected!r}


def test_program():
    buf = io.StringIO()
    ns = {{"__name__": "__main__"}}
    with contextlib.redirect_stdout(buf):
        exec(compile(SOURCE, "prog.py", "exec"), ns)
    assert buf.getvalue().strip() == EXPECTED
'''

# pytest --tb=line prints one line per failure: "/path/test_x.py:12: Error: msg".
# The part after the last ": " that starts at the error class is what BugsInPy
# stores, so that is what is kept.
_LINE = re.compile(r"^/.*?:\d+:\s*(?P<sig>\S.*)$", re.M)


def pytest_python() -> str:
    """An interpreter that can import pytest. The project venv often cannot."""
    for exe in (sys.executable, "python3", "python"):
        try:
            if subprocess.run([exe, "-c", "import pytest"],
                              capture_output=True, timeout=30).returncode == 0:
                return exe
        except Exception:
            continue
    raise SystemExit("no interpreter with pytest found; pip install pytest")


PY_TEST = ""


def signature(wd: pathlib.Path, source: str, expected: str) -> str | None:
    """Run `source` under pytest pinned to `expected`; None if it passes.

    Each call gets its OWN directory. Reusing one path made CPython serve a
    stale `__pycache__` entry for `test_prog.py` whenever two writes landed in
    the same mtime second, so the harness asserted a PREVIOUS sample's expected
    value -- observed as `assert '3' == '7'` where the program had printed 3.
    `-p no:cacheprovider` disables pytest's cache, not the interpreter's, and
    PYTHONDONTWRITEBYTECODE closes the same hole from the other side.
    """
    d = pathlib.Path(tempfile.mkdtemp(dir=wd))
    (d / "prog.py").write_text(source)
    (d / "test_prog.py").write_text(HARNESS.format(expected=expected))
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    p = subprocess.run(
        [PY_TEST or sys.executable, "-m", "pytest", "-q", "--no-header", "--tb=line",
         "-p", "no:cacheprovider", str(d / "test_prog.py")],
        capture_output=True, text=True, cwd=d, timeout=60, env=env)
    if p.returncode == 0:
        return None
    m = _LINE.search(p.stdout)
    if m:
        return re.sub(r"\s+", " ", m.group("sig")).strip()[:400]
    # A collection error or a timeout is not a measured behaviour difference.
    return ""


def run_value(wd: pathlib.Path, source: str) -> str | None:
    """What the program prints, or None if it raises. Used to pin the assert."""
    (wd / "prog.py").write_text(source)
    p = subprocess.run([sys.executable, str(wd / "prog.py")],
                       capture_output=True, text=True, cwd=wd, timeout=60)
    return p.stdout.strip() if p.returncode == 0 else None



# --------------------------------------------------------- the unexercised case
# `core.review_commit` case 5 routes EVERY byte-identical result to
# `not-exercised`, and its outcome string says so: "either the changed code
# never ran, or it ran and changed nothing this command prints -- which of the
# two is NOT known". The corpus had only the second kind, and taught the model
# to answer "behaviour did not change, the output is still X" -- true of a
# generated pair that was actually run, and wrong of the deployed case, where
# not being run is equally consistent with what was observed. The model then
# produces the trained sentence on a real commit and the guard withholds it.
#
# This makes the first kind. The mutation is real and sits in a function the
# harness never calls, so the test passes on both sides for a reason the diff
# cannot show -- which is the situation, not a defect in the sample.
#
# It indents the program into a function body, which also moves the diff off
# column zero. BugsInPy diffs are inside functions; the generated ones were not.
_UNEXERCISED_TAG = "ready"


def unexercised(src: str) -> str:
    """`src` as the body of a function nothing calls, beside a main that prints."""
    body = "\n".join(("    " + l) if l.strip() else l for l in src.splitlines())
    return (f"def _configure():\n{body}\n\n\n"
            f"print({_UNEXERCISED_TAG!r})\n")

def write_splits(out: list[dict], stem: pathlib.Path, seed: int,
                 holdout_families: int, holdout_frac: float) -> None:
    """train / within-family / cross-family, the same three `gen_exec_corpus`
    makes and for the same reasons:

      within  families the model trained on, VALUES it never saw
      cross   defect shapes held out entirely -- "does it GENERALISE?"

    Families are held out from BOTH the differing and the non-differing pool: a
    cross-family set of only broken shapes measures recall and calls it
    generalisation.
    """
    fams = sorted({o["family"] for o in out})
    pos_f = sorted({o["family"] for o in out if o["differs"]})
    neg_f = [f for f in fams if f not in pos_f]
    rs = random.Random(seed + 1)
    k_b = max(1, round(holdout_families * len(pos_f) / max(1, len(fams))))
    k_c = max(1, holdout_families - k_b)
    held = set(rs.sample(pos_f, min(k_b, len(pos_f))) +
               rs.sample(neg_f, min(k_c, len(neg_f))))
    cross = [o for o in out if o["family"] in held]
    rest = [o for o in out if o["family"] not in held]
    within = []
    for lab in (True, False):
        pool = [o for o in rest if o["differs"] == lab]
        rs.shuffle(pool)
        within += pool[:round(len(pool) * holdout_frac)]
    wid = {id(o) for o in within}
    train = [o for o in rest if id(o) not in wid]

    bal = lambda g: f"{len(g):>5} ({100*sum(o['differs'] for o in g)/max(1,len(g)):.0f}% positive)"
    print(f"\n  train            {bal(train)}   "
          f"{len({o['family'] for o in train})} families")
    print(f"  holdout within   {bal(within)}   values unseen, families seen")
    print(f"  holdout cross    {bal(cross)}   {len(held)} families never trained on")
    print(f"    held-out families: {', '.join(sorted(held))}")
    for name, g in (("train", train), ("within", within), ("cross", cross)):
        if not g:
            sys.stdout.flush()
            raise SystemExit(f"FAILED: {name} split is empty")
        if not any(o["differs"] for o in g) or all(o["differs"] for o in g):
            sys.stdout.flush()
            raise SystemExit(f"FAILED: {name} split has only one label — it "
                             f"cannot measure both recall and false alarms")
    for suffix, g in (("", train), ("_holdout_within", within),
                      ("_holdout_cross", cross)):
        dst = stem.with_name(stem.stem + suffix + stem.suffix)
        dst.write_text("\n".join(json.dumps(o) for o in g) + "\n")
        print(f"  -> {dst} ({len(g)})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split-from", type=pathlib.Path,
                    help="split an already-generated corpus and exit")
    ap.add_argument("--holdout-families", type=int, default=6)
    ap.add_argument("--holdout-frac", type=float, default=0.15)
    ap.add_argument("--n", type=int, default=6, help="samples per family")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--context", type=int, default=3)
    ap.add_argument("--preserve-rate", type=float, default=0.15)
    ap.add_argument("--break-rate", type=float, default=0.15)
    ap.add_argument("--unexercised-rate", type=float, default=0.12, metavar="F",
                    help="fraction of samples whose change sits in a function "
                         "the test never calls — the deployed not-exercised "
                         "case, which the corpus had no example of. Each one "
                         "is drawn from a would-be POSITIVE, so it costs a "
                         "positive: 0.12 holds the balance near v3's 39%%")
    ap.add_argument("--min-frame-ratio", type=float, default=0.35)
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--out", type=pathlib.Path)
    args = ap.parse_args()

    if args.split_from:
        rows = [json.loads(l) for l in open(args.split_from)]
        print(f"splitting {len(rows)} rows from {args.split_from}")
        write_splits(rows, args.out or args.split_from, args.seed,
                     args.holdout_families, args.holdout_frac)
        return
    global PY_TEST
    PY_TEST = pytest_python()
    r = random.Random(args.seed)
    out, stats = [], Counter()
    with tempfile.TemporaryDirectory() as td:
        wd = pathlib.Path(td)
        for cat, fam, buggy in FAMILIES:
            for _ in range(args.n):
                pre, post, changed = fam(r)
                pick = r.random()
                if pick < args.preserve_rate:
                    alt = _preserve(r, pre)
                    if alt: post, changed = alt
                elif pick < args.preserve_rate + args.break_rate:
                    alt = _break(r, pre)
                    if alt: post, changed = alt

                # A share of samples become the not-exercised case: the same
                # real mutation, moved inside a function the harness never
                # calls. Both sides then pass, and the reason they pass is
                # invisible to the command -- which is the deployed situation.
                unexercised_row = (pre != post
                                   and r.random() < args.unexercised_rate)
                if unexercised_row:
                    pre, post = unexercised(pre), unexercised(post)

                # Pin the assertion to what the FIXED side prints. If that side
                # raises there is no value to pin and the sample is unusable.
                expected = run_value(wd, post)
                if expected is None:
                    stats["post-raises"] += 1
                    continue
                after = signature(wd, post, expected)
                if after is not None:
                    stats["post-not-green"] += 1   # non-determinism; drop it
                    continue
                before = signature(wd, pre, expected)
                if before == "":
                    stats["pre-unparsed"] += 1
                    continue

                differs = before is not None
                if unexercised_row and differs:
                    # The mutation escaped into the module body somehow; the
                    # sample is no longer the case it was built to be.
                    stats["unexercised-still-differs"] += 1
                    continue
                # The corpus is stated in the FIX direction, so the diff shown
                # is pre -> post and `before` carries the failure.
                out.append({
                    "family": fam.__name__,
                    "category": ("unexercised" if unexercised_row
                                 else cat if differs else "clean"),
                    # The deployed `outcome`, verbatim from core.review_commit.
                    # It is the ONLY input that separates a run-and-identical
                    # row from a never-reached one, which is the point: the
                    # model has to learn to read it rather than infer safety
                    # from two equal values.
                    "outcome": (NOT_EXERCISED if not differs
                                else FIXED_IT),
                    "changed": changed, "differs": differs,
                    "diff": unified(pre, post, f"{fam.__name__}.py",
                                    args.context),
                    "before": before if differs else PASS,
                    "after": PASS,
                    "message": _commit_msg(r, pre),
                })
                stats["ok"] += 1

    if not out:
        for k, v in sorted(stats.items()):
            print(f"  {k}: {v}")
        raise SystemExit("no samples survived; nothing to write")
    frames = Counter(frame(o["diff"]) for o in out)
    sigs = [o["before"] for o in out if o["differs"]]
    import statistics as st
    print(f"{len(out)} pairs, {len(FAMILIES)} families")
    print(f"  distinct diff FRAMES (slots stripped) : {len(frames)}")
    # Three classes, not two. The two identical-output kinds are one label and
    # one outcome string but different situations, and the split has to be
    # visible: an all-unexercised negative pool would teach "say nothing was
    # established" as the answer to every non-difference.
    nx = sum(1 for o in out if o["category"] == "unexercised")
    same = sum(1 for o in out if not o["differs"])
    print(f"  differs / same by EXECUTION           : "
          f"{sum(o['differs'] for o in out)} / {same}"
          f"   ({100*sum(o['differs'] for o in out)/max(1,len(out)):.0f}% positive)")
    print(f"    of the same: ran-and-identical {same - nx}, never-reached {nx}")
    if sigs:
        ln = sorted(len(s) for s in sigs)
        withcls = sum(1 for s in sigs if re.match(r"^[A-Za-z_][A-Za-z0-9_]*Error", s))
        print(f"  signature length  median {st.median(ln):.0f}  mean "
              f"{sum(ln)/len(ln):.0f}  max {max(ln)}   (BugsInPy: 55 / 66 / 400)")
        print(f"  names an exception class              : {withcls}/{len(sigs)} "
              f"({100*withcls/len(sigs):.0f}%)   (BugsInPy: 87%)")
        print(f"  distinct signatures                   : {len(set(sigs))}/{len(sigs)}")
    for k, v in sorted(stats.items()):
        if k != "ok":
            print(f"  {k}: {v}")
    ratio = len(frames) / max(1, len(out))
    if ratio < args.min_frame_ratio:
        sys.stdout.flush()
        raise SystemExit(
            f"\nFAILED: frame ratio {ratio:.2f} < {args.min_frame_ratio}.")
    if args.audit:
        for o in out[:3]:
            print("\n" + "=" * 70)
            print(o["diff"][:400])
            print(f"  before: {o['before']!r}\n  after:  {o['after']!r}")
    if args.out:
        args.out.write_text("\n".join(json.dumps(o) for o in out) + "\n")
        print(f"  wrote {args.out}")
        write_splits(out, args.out, args.seed, args.holdout_families,
                     args.holdout_frac)


if __name__ == "__main__":
    main()
