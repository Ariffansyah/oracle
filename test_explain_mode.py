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

# ------------------------------------------- the automatic explain fallback
# Grounded mode refusing an unsupported claim is right, and leaves a file the
# command never touched with no prose at all. Observed on a Go router adding
# rate limiting to /login inside a package with no test files: a correct badge,
# a correct paragraph about what was not established, and not one word about
# the change. The fallback asks the explain-mode QUESTION under the
# grounded-mode FILTER, so a reading is offered without the verdict returning.
_calls = []
# The real hunk, so the `5` the prose quotes is in the diff. Without it the
# invented-number check fires first and correctly -- which is itself worth
# knowing: the fallback does not get a pass on any fabrication check.
ROUTES_DIFF = (
    '--- a/internal/routes/routes.go\n+++ b/internal/routes/routes.go\n'
    '@@ -40,7 +40,7 @@\n'
    '-    authGroup.POST("/login", h.Login)\n'
    '+    authGroup.POST("/login", middleware.RateLimit(pool, "login", 5, '
    'time.Minute), h.Login)\n')
_REASONS = ("The login route now passes through RateLimit with a budget of 5 "
            "per minute, so a sixth attempt inside that window is rejected "
            "before Login runs.")
_VERDICT = "This is harmless and no bug was introduced."


def _stub(answer, grounded_answer=None):
    """Answer the two passes differently, as a real model does.

    The grounded pass is asked what the run proved and offers a verdict, which
    the filter removes. The explain pass is asked what the code does. Using one
    answer for both hides the fallback entirely: a sentence that merely
    DESCRIBES survives grounded mode already -- the unmeasured rule withholds
    verdicts, not descriptions -- so nothing would ever fall back.
    """
    def ask(host, model, prompt, system=""):
        is_explain = system == core.EXPLAIN_SYSTEM
        _calls.append("explain" if is_explain else "grounded")
        body = answer if is_explain else (grounded_answer or _VERDICT)
        return '{"explanation": "%s"}' % body
    return ask


def _unmeasured(answer, fallback=True, grounded=None):
    """Run the unexercised path with a stubbed model; return the FileReview."""
    real, real_flag = core.ask, core.FALLBACK_EXPLAIN
    _calls.clear()
    core.ask, core.FALLBACK_EXPLAIN = _stub(answer, grounded), fallback
    try:
        r = core.FileReview(path="internal/routes/routes.go", risk="unclear",
                            why_unclear="not-exercised", checks="tests",
                            diff=ROUTES_DIFF)
        r.before = r.after = "?  example.com/api/internal/routes  [no test files]"
        core.explain("h", "m", r, "add rate limiting", "go test ./...",
                     "the command reported that it ran NO TESTS", measured=False)
        return r
    finally:
        core.ask, core.FALLBACK_EXPLAIN = real, real_flag


# A reading that REASONS survives, and is labelled as unverified.
r = _unmeasured(_REASONS)
check("fallback asks the model twice", _calls, ["grounded", "explain"])
check("fallback prose is kept", "RateLimit" in (r.explanation or ""), True)
check("fallback prose is banner-tagged", core._tag(r).startswith("("), True)
check("fallback reports no withholding of its OWN prose", r.withheld, "")

# A bare verdict does NOT come back through the fallback. Explain mode drops
# the unmeasured-claim rule; the fallback must not, or it would answer a
# refused "no new bug" with an accepted "this is harmless".
r = _unmeasured(_VERDICT)
check("fallback still refuses a bare verdict", r.explanation, "")
check("fallback reports the refusal", "harmless" in (r.withheld or ""), True)
check("mode reverts when the fallback says nothing", r.mode, "grounded")

# The fallback fires only on real silence. Grounded mode withholds VERDICTS,
# not descriptions -- so when the model already says something supportable
# about an unexercised file, that answer stands and no second call is made.
r = _unmeasured(_VERDICT, grounded=_REASONS)
check("a description survives grounded mode", "RateLimit" in (r.explanation or ""), True)
check("and does not trigger the fallback", _calls, ["grounded"])
check("so it carries no explain banner", core._tag(r), "")

# Switched off, the old behaviour stands exactly.
r = _unmeasured(_REASONS, fallback=False)
check("fallback off: one model call", _calls, ["grounded"])
check("fallback off: no prose", r.explanation, "")

bad = [t for t in OK if not t[1]]
for name, ok, got, want in OK:
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        print(f"         got  {got!r}\n         want {want!r}")
print(f"\n{len(OK) - len(bad)}/{len(OK)} passed")
sys.exit(1 if bad else 0)
