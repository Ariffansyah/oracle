"""The v2 contract's self-consistency checks, against the failure they were built for.

    python test_exec_contract.py

The `[27] [9]` case is a verbatim row from data/v2_values_sft.json: the checkpoint
asserted differs=true, emitted the gold AFTER value into both slots, and wrote
prose calling it the unchanged output.
"""

from exec_contract import contradiction, direction_reversed, repair, swapped

# ---------------------------------------------------------------- contradiction
# `differs` and `before != after` are the same claim, so they must agree.
assert "one value for both sides" in contradiction(
    {"differs": True, "before": "[27] [9]", "after": "[27] [9]"})
assert "unchanged" in contradiction({"differs": False, "before": "3", "after": "4"})
assert contradiction({"differs": True, "before": "3", "after": "4"}) is None
assert contradiction({"differs": False, "before": "3", "after": "3"}) is None

# Whitespace is not a disagreement.
assert contradiction({"differs": False, "before": "a  b", "after": "a b"}) is None

# Anything that is not the v2 contract passes through untouched -- the reviewer
# asks for {"explanation"} alone and must not be flagged by this.
assert contradiction({"explanation": "..."}) is None
assert contradiction({"differs": "yes", "before": 1, "after": 2}) is None
assert contradiction("not a dict") is None

# --------------------------------------------------------------------- swapped
assert swapped({"before": "9", "after": "9"}, before="4", after="9")   # the observed slip
assert swapped({"before": "9", "after": "4"}, before="4", after="9")   # sides exchanged
assert not swapped({"before": "4", "after": "9"}, before="4", after="9")
# When the measurement is equal there is no direction to get wrong.
assert not swapped({"before": "4", "after": "4"}, before="4", after="4")

# ---------------------------------------------------------------------- repair
got = {"differs": True, "before": "[27, 9]", "after": "[27, 9]"}
fixed, note = repair(got, before="[27] [9]", after="[27, 9]")
assert fixed["before"] == "[27] [9]"      # pinned to the measurement
assert fixed["after"] == "[27, 9]"        # what the model computed, kept
assert "measurement" in note
assert got["before"] == "[27, 9]"         # the caller's dict is untouched

# Two different values outvote a `differs: false` verdict.
fixed, note = repair({"differs": False, "before": "9", "after": "4"}, before="9")
assert fixed["differs"] is True and note

# A coherent object is returned as-is.
coherent = {"differs": True, "before": "4", "after": "9"}
fixed, note = repair(coherent, before="4", after="9")
assert note is None and fixed is coherent

# ------------------------------------------------------------------- the prose
# The reviewer keeps only `explanation`, so the slip arrives as a backwards
# sentence. Both numbers are quoted from the measurement, so the invented-number
# check cannot see it; only direction can.
assert "reverse" in direction_reversed("the reward changed from 20 to 10",
                                       before="10", after="20")
assert direction_reversed("the reward changed from 10 to 20",
                          before="10", after="20") is None
# A value present on both sides has no decidable direction, so it never fires.
assert direction_reversed("changed from 3 to 4", before="3 4", after="3 4") is None
assert direction_reversed("changed from 4 to 3", before="x", after="x") is None
assert direction_reversed("this command does not cover the change",
                          before="10", after="20") is None

# ------------------------------------------------- the reviewer, end to end
# core.verify() must reject a backwards sentence even though every number in it
# was measured, and explain() must withhold when the structured fields show the
# slip. Both are the paths a user actually sees.
import json as _json
import oracle_reviewer.core as core

measured_before, measured_after = "total 10", "total 20"

assert core.verify("the total changed from 10 to 20", measured_before,
                   measured_after, diff="") is None
assert core.verify("the total changed from 20 to 10", measured_before,
                   measured_after, diff="") is not None   # every number measured

_reply = {}
core.ask = lambda *a, **k: _json.dumps(_reply)

def _run(reply):
    global _reply
    _reply = reply
    r = core.FileReview(path="a.py", risk="change")
    r.before, r.after, r.diff = measured_before, measured_after, "-x = 10\n+x = 20"
    core.explain("h", "m", r, message="bump", cmd="python a.py", outcome="differs")
    return r

# The measured failure: post-state emitted into both slots.
r = _run({"differs": True, "before": "total 20", "after": "total 20",
          "explanation": "the total is 20 before and after the change"})
assert r.explanation == "" and "wrong way round" in r.withheld, r.withheld

# Sides exchanged.
r = _run({"differs": True, "before": "total 20", "after": "total 10",
          "explanation": "the total changed from 20 to 10"})
assert "wrong way round" in r.withheld

# A correct emission is passed through and shown.
r = _run({"differs": True, "before": "total 10", "after": "total 20",
          "explanation": "the total changed from 10 to 20"})
assert r.withheld == "" and r.explanation.startswith("the total changed"), (r.withheld, r.explanation)

# The reviewer's own one-field contract must not be flagged by any of this.
r = _run({"explanation": "the total changed from 10 to 20"})
assert r.withheld == "" and r.explanation

# ------------------------------------------------- claims with nothing measured
# Verbatim from the app, on `range(1, n)` -> `range(1, n + 1)` against a baseline
# that was already failing. The second sentence is measured and true; the first
# is a safety verdict on a real off-by-one, and nothing had been established.
from exec_contract import unmeasured_claim

_REPORTED = ("The loop bound in `sum_to` was changed from `range(1, n)` to "
             "`range(1, n + 1)`, which is a non-functional change that does not "
             "affect the program's behavior. The project still fails with exit "
             "5: no tests ran in 0.00s.")
assert unmeasured_claim(_REPORTED)
assert unmeasured_claim("this is functionally equivalent")
assert unmeasured_claim("the behaviour remains the same")
assert unmeasured_claim("this will crash when n is zero")
assert unmeasured_claim("the change introduces a bug")

# The correct answers for an unexercised change must survive.
assert unmeasured_claim("This command does not cover the change; check callers "
                        "of sum_to.") is None
assert unmeasured_claim("The project still fails with exit 5: no tests ran.") is None
assert unmeasured_claim("Nothing was observed either way.") is None
assert unmeasured_claim("") is None

# core.verify() applies it ONLY where nothing was measured. After a run that
# really did fail, "will fail" is a report rather than a guess.
assert core.verify(_REPORTED, "exit 5: no tests ran", "exit 5: no tests ran",
                   diff="", measured=False) is not None
assert core.verify("the output changed from 10 to 15", "10", "15",
                   diff="", measured=True) is None

# The end-to-end path: prose withheld, and the file records WHICH unclear case
# it is so the UI does not offer "identical output" wording for a dead baseline.
r = core.FileReview(path="calc.py", risk="unclear", why_unclear="baseline")
r.before = r.after = "exit 5: no tests ran in 0.00s"
r.diff = "-    for i in range(1, n):\n+    for i in range(1, n + 1):"
core.ask = lambda *a, **k: _json.dumps({"explanation": _REPORTED})
core.explain("h", "m", r, message="fix off-by-one", cmd="pytest -q",
             outcome="nothing was established either way", measured=False)
# Per SENTENCE: the invented safety claim goes, the measured report stays. This
# used to withhold the whole answer and take the true half with it.
assert "does not affect" not in r.explanation, r.explanation
assert r.explanation == "The project still fails with exit 5: no tests ran in 0.00s."
assert "harmless" in r.withheld, r.withheld

# ------------------------------------------- runtime attribution, nothing run
# Verbatim from the app on `range(1, n + 1)` -> `range(1, n)`, reviewed with a
# `pytest -q` that exited 5 at BOTH commits. It slipped past every check above:
# no verdict word appears, and 1, 5 and 0 are all present in the measurement, so
# the invented-number check clears it. The exit status did not change -- it was
# 5 before the commit -- and no output of 0 was ever produced.
_ATTRIB = ("The loop bound in `sum_to` was reduced from `n + 1` to `n`, causing "
           "the program to fail because the loop no longer includes the upper "
           "bound. The output remains 0, but the program's exit status changed "
           "to 5.")
assert "blames the run" in unmeasured_claim(_ATTRIB, baseline_broken=True)
assert "blames the run" in unmeasured_claim(_ATTRIB)      # true either way
assert unmeasured_claim("this results in a crash")
assert unmeasured_claim("the program now fails")
assert unmeasured_claim("the exit code is now 2")

# Reporting the measurement is not attribution: it did still fail.
assert unmeasured_claim("The project still fails with exit 5: no tests ran.",
                        baseline_broken=True) is None

# Where output really was compared, identical output IS a measurement, so the
# stricter observation check must NOT fire.
assert unmeasured_claim("The output is unchanged.") is None
assert unmeasured_claim("The output remains `[0, 2, 4]`.") is None
# ...but with a dead baseline nothing was observed, so the same words are not.
assert "never made" in unmeasured_claim("The output remains `[0, 2, 4]`.",
                                        baseline_broken=True)

# What the diff alone DOES support must survive: describing the change and its
# logical consequence, attributing nothing to a run.
assert unmeasured_claim(
    "`range(1, n + 1)` became `range(1, n)`. Python's range excludes its upper "
    "bound, so sum_to no longer adds n itself.", baseline_broken=True) is None

# core threads the case through, so the strict form applies only to `baseline`.
assert core.verify(_ATTRIB, "exit 5", "exit 5", diff="", measured=False,
                   case="baseline") is not None
# (the measurement must contain the numbers, or the invented-number check fires
# first -- which is itself correct, just not what this line is testing)
assert core.verify("The output remains `[0, 2, 4]`.", "[0, 2, 4]", "[0, 2, 4]",
                   diff="", measured=False, case="not-exercised") is None
assert core.verify("The output remains `[0, 2, 4]`.", "[0, 2, 4]", "[0, 2, 4]",
                   diff="", measured=False, case="baseline") is not None

# ------------------------------------------------ a removal that never happened
# Given the real compiler error `h.EventCache.Version undefined`, the model
# explained it as "the `Version` method was removed from the `EventCache`
# interface". Nothing was removed: the diff ADDS a call to a method that does
# not exist. No measured value is the wrong way round and no symbol is invented,
# so neither existing check can see it — but a `-` line should mention a thing
# said to be removed, and none does.
from exec_contract import phantom_removal

GO_DIFF = """--- a/handlers.go
+++ b/handlers.go
@@ -5,3 +5,4 @@
-\th.EventCache.Set(key, body)
+\tcacheVersion := h.EventCache.Version()
+\th.EventCache.Set(key, body, cacheVersion)
"""
assert "was removed" in phantom_removal(
    "The `Version` method was removed from the `EventCache` interface.", GO_DIFF)
assert phantom_removal("Version has been deleted", GO_DIFF)

# A real removal is not flagged: `Set(key, body)` really is on a `-` line.
assert phantom_removal("The call to `Set` was removed.", GO_DIFF) is None
# Nor is prose that claims no removal at all.
assert phantom_removal("A call to Version was added.", GO_DIFF) is None
assert phantom_removal("", GO_DIFF) is None

# It applies whether or not anything was measured, so it lives outside the
# unmeasured branch of verify().
assert core.verify("The `Version` method was removed.", "ok", "exit 1",
                   diff=GO_DIFF, measured=True) is not None

# Active voice, which the passive-only pattern missed. Verbatim from the app:
_ACTIVE = ("The change adds a call to `h.EventCache.Version()` in the `ListEvents` "
           "and `GetEvent` handlers, which removes the `cacheVersion` variable "
           "from the `Set` call.")
assert phantom_removal(_ACTIVE, GO_DIFF)
assert phantom_removal("this removes the `Version` method", GO_DIFF)
assert phantom_removal("the commit drops `cacheVersion`", GO_DIFF)

# The subject has to be the CHANGE. "The function removes whitespace" describes
# runtime behaviour, not a deleted line, and must not be read as one.
assert phantom_removal("the function removes whitespace from the input", GO_DIFF) is None
assert phantom_removal("this helper strips trailing slashes", GO_DIFF) is None

# The name has to look like a symbol. "removes the leading zeros" names none,
# and hunting for `leading` among the removed lines would flag a true sentence.
assert phantom_removal("it removes the leading zeros before storing", GO_DIFF) is None
assert phantom_removal("it removes the `leadingZeros` helper", GO_DIFF)   # camelCase

print("ok")

# --------------------------------- the inference that walked past both lists
# Verbatim from a real review of a TypeScript commit. `pnpm run lint` was
# already failing before it, so nothing about the file was measured, and this
# was printed as a finding:
#
#   "The project still fails, so the change did not resolve the issue."
#
# Two clauses, and only one of them is wrong. "The project still fails" restates
# the measured output and is allowed off a live baseline -- that is the
# `is None` case a few lines above, and it must stay. "so the change did not
# resolve the issue" INFERS that the change failed at something, which nothing
# established. Only the inference is caught unconditionally.
_LEAK = "The project still fails, so the change did not resolve the issue."
assert unmeasured_claim(_LEAK, baseline_broken=False), _LEAK
assert unmeasured_claim(_LEAK, baseline_broken=True), _LEAK
for s in ("the change did not resolve the issue",
          "this does not fix the underlying problem",
          "it will not address the race",
          "the patch does not solve it"):
    assert unmeasured_claim(s), s

# On a DEAD baseline the restatement is unsupported too: both runs failed for a
# reason that has nothing to do with this file, so "still fails" is a fact about
# the broken baseline. Live baseline, unexercised change: still allowed.
# The restatement stays allowed on a dead baseline too. It quotes the measured
# output verbatim -- it is the same string the tool prints itself -- and it is
# the half the per-sentence filter exists to keep. Blocking it was tried and it
# broke the end-to-end assertion below, correctly.
_RESTATE = "The project still fails with exit 5: no tests ran."
assert unmeasured_claim(_RESTATE, baseline_broken=False) is None, _RESTATE
assert unmeasured_claim(_RESTATE, baseline_broken=True) is None, _RESTATE

# ------------------------------------------- asserting NO bug, with no evidence
# "introduces a bug" was caught; its negation was not. Observed surviving the
# filter on a Go router commit that added rate limiting to /login and /users,
# printed under a badge that itself read "No Tests Ran — Nothing Measured":
#
#   "The output remains identical, and no new bug was introduced."
#
# Asserting no defect is exactly as unsupported as asserting one, and it is the
# clause a reader carries away from a review that measured nothing.
_NOBUG = "The output remains identical, and no new bug was introduced."
assert unmeasured_claim(_NOBUG), _NOBUG
assert "harmless" in unmeasured_claim(_NOBUG), unmeasured_claim(_NOBUG)
for s in ("No regressions were introduced by this change.",
          "This does not introduce any bugs.",
          "The change should not affect behaviour.",
          "Nothing was broken.",
          "There are no side effects.",
          # A hedge is still a verdict.
          "The change appears correct.",
          "This looks safe.",
          "It seems fine."):
    assert unmeasured_claim(s), s

# The widening must not swallow the honest answers, which are the whole point
# of the unexercised case. "no tests ran" is not "no bugs".
for ok in ("No tests ran over this package.",
           "No test files exist for these routes.",
           "The output is unchanged.",
           "Nothing was observed either way.",
           "This command does not cover the change; check callers of sum_to."):
    assert unmeasured_claim(ok) is None, ok

# Plain description of a diff must not trip any of this.
for ok in ("the `version` field was added to the Cache struct",
           "`Set` gained a third parameter, `version`",
           "the guard returns early when the generation does not match"):
    assert unmeasured_claim(ok, baseline_broken=True) is None, ok

print("unmeasured_claim: inference vs restatement ok")

# ------------------------------- a name in object position is not a deletion
# "a write racing a `Clear` is dropped" is a correct reading of a cache
# generation guard, and it was rejected as claiming `Clear` had been deleted.
# The PASSIVE pattern had no subject restriction, so any backticked name
# followed by "is dropped" matched, whatever its grammatical role. The active
# pattern had guarded against this since it was written; this brings the
# passive one into line. It matters most in explain mode, whose prose is
# mostly about what the code DOES rather than about what the diff shows.
_CACHE_DIFF = ("-func (c *Cache) Set(k string, d []byte) {\n"
               "+func (c *Cache) Set(k string, d []byte, version uint64) {\n")
for ok in ("a write racing a `Clear` is dropped",
           "the entry is dropped when the generation does not match",
           "a request arriving after `Clear` is discarded",
           "the response is dropped for any stale `version`"):
    assert phantom_removal(ok, _CACHE_DIFF) is None, ok

# ...and a genuine claim of deletion is still caught, in both voices.
assert phantom_removal("the `Version` method was removed", _CACHE_DIFF)
assert phantom_removal("the change removes the `Version` method", _CACHE_DIFF)
# A deletion the diff DOES contain stays allowed.
assert phantom_removal("the old `Set` signature was removed", _CACHE_DIFF) is None

print("phantom_removal: object position ok")
