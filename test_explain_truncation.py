"""`explain` against malformed model output — the deployed review path.

    python test_explain_truncation.py

Covers the two behaviours the lenient parser changed:

  * an answer whose measured value quotes a brace now REACHES the developer;
    the old brace-counting parser blanked it and reported "no explanation"
  * an answer the model did not finish is NOT shown as a finished sentence,
    which is the risk leniency introduces and the reason the parser reports
    HOW it recovered

The model is stubbed. This is about what `core` does with an answer, not about
what the model says, so it needs no server and no GPU.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from oracle_reviewer import core  # noqa: E402

OK = []


def check(name, got, want):
    OK.append((name, got == want, got, want))


def run(raw, before="TypeError: bad {", after="1 passed"):
    """Drive explain() with `raw` as the model's reply."""
    orig = core.ask
    core.ask = lambda *a, **k: raw
    try:
        r = core.FileReview(path="a.py", risk="change", before=before,
                            after=after, diff="- old\n+ new\n")
        core.explain("h", "m", r, "msg", "pytest -q", "the run changed")
        return r
    finally:
        core.ask = orig


# --- the bug this whole change is about --------------------------------------
r = run('{"differs": true, "before": "TypeError: bad {", "after": "1 passed",'
        ' "explanation": "the guard was removed, so the run now fails."}')
check("brace in the measured value no longer blanks the review",
      r.explanation, "the guard was removed, so the run now fails.")

# --- the risk leniency introduces --------------------------------------------
r = run('{"differs": true, "before": "TypeError: bad {", "after": "1 passed",'
        ' "explanation": "the guard was removed, so the value is no longer')
check("an unfinished clause is not shown", r.explanation, "")
check("and the developer is told why",
      "cut off" in r.withheld, True)

r = run('{"differs": true, "before": "TypeError: bad {", "after": "1 passed",'
        ' "explanation": "the guard was removed. the value is no longer')
check("a completed sentence survives a truncated tail",
      r.explanation, "the guard was removed.")
check("and the dropped tail is reported",
      "cut off" in r.withheld, True)

# --- what must not change ----------------------------------------------------
r = run('{"differs": true, "before": "TypeError: bad {", "after": "1 passed",'
        ' "explanation": "the guard was removed, so the run now fails."}')
check("a clean answer carries no truncation note",
      "cut off" in r.withheld, False)

r = run('{"differs": true, "before": "1 passed", "after": "TypeError: bad {",'
        ' "explanation": "the guard was removed, so the run now fails."}')
check("a swapped answer is still refused entire", r.explanation, "")
check("and says so", "wrong way round" in r.withheld, True)

r = run("the model said nothing resembling json")
check("unparseable is still empty", r.explanation, "")

bad = [t for t in OK if not t[1]]
for name, ok, got, want in OK:
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        print(f"         got  {got!r}\n         want {want!r}")
print(f"\n{len(OK) - len(bad)}/{len(OK)} passed")
sys.exit(1 if bad else 0)
