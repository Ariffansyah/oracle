"""The two review modes, and the line between them.

    python test_explain_mode.py

grounded  -- execution is the verdict; a claim it did not measure is withheld
explain   -- the diff is the evidence and the run is context, so a verdict read
             off the code is allowed. Every FABRICATION check still applies.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from oracle_reviewer import core  # noqa: E402

OK = []


def check(name, got, want):
    OK.append((name, got == want, got, want))


DIFF = "-func (c *Cache) Set(k string, d []byte) {\n+func (c *Cache) Set(k string, d []byte, version uint64) {\n"
SAFE = "This change does not affect behaviour."
RISK = ("`Set` gained a `version` parameter and returns early when it does not "
        "match, so a write racing a `Clear` is dropped.")

# --- the rule that separates the modes ---------------------------------------
check("grounded withholds a safety verdict it did not measure",
      core.verify(SAFE, "ok", "ok", DIFF, measured=False, mode="grounded")
      is not None, True)
check("explain allows it — that verdict is read off the code",
      core.verify(SAFE, "ok", "ok", DIFF, measured=False, mode="explain"), None)

# --- everything else must survive the mode change ----------------------------
check("explain still rejects an invented number",
      core.verify("the timeout went from 30 to 99 seconds", "ok", "ok", DIFF,
                  measured=False, mode="explain") is not None, True)
check("explain still rejects a removal the diff does not contain",
      core.verify("the `Version` method was removed", "ok", "ok", DIFF,
                  measured=False, mode="explain") is not None, True)
check("explain keeps a real reading of the diff",
      core.verify(RISK, "ok", "ok", DIFF, measured=False, mode="explain"), None)

# --- a measured run is unaffected by the mode --------------------------------
check("grounded on a measured run is unchanged",
      core.verify("the output changed from 10 to 15", "10", "15", diff="",
                  measured=True, mode="grounded"), None)
check("explain on a measured run is unchanged",
      core.verify("the output changed from 10 to 15", "10", "15", diff="",
                  measured=True, mode="explain"), None)

# --- the banner --------------------------------------------------------------
def body(mode):
    r = core.FileReview(path="c.go", risk="co-dependent", before="ok",
                        after="ok", diff=DIFF, moves_with=["h.go"],
                        explanation=RISK)
    r.mode = mode
    return core.review_body(r, "go test ./...")


check("explain-mode prose is labelled", core.EXPLAIN_TAG in body("explain"), True)
check("grounded-mode prose is not", core.EXPLAIN_TAG in body("grounded"), False)
check("the default mode is grounded", core.MODE, "grounded")

bad = [t for t in OK if not t[1]]
for name, ok, got, want in OK:
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        print(f"         got  {got!r}\n         want {want!r}")
print(f"\n{len(OK) - len(bad)}/{len(OK)} passed")
sys.exit(1 if bad else 0)
