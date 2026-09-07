"""Consistency checks for the v2 exec contract: {differs, before, after, explanation}.

The v2 target orders the fields so the values are decoded before the prose. That
ordering is right, but it leaves `before` as the first thing the model writes --
emitted after it has committed to `differs` and before it has computed anything.
Measured on 519 cross-family holdout rows (data/v2_values_sft.json), the trained
checkpoint fails there in one specific, one-directional way:

    27/514 parsed rows assert differs=true and then emit before == after.
    In 20 of the 21 such rows whose gold values differ, the single value it
    emitted is the gold AFTER. It computed the post-state and back-filled it
    into the pre-state slot.

    The reverse -- differs=false with before != after -- happens 0/514 times.

So the model is not confused about whether behaviour changed; on those rows it is
right. It loses track of which side of the change a value belongs to. Two things
follow, and this module implements both:

  contradiction()  needs no ground truth. `differs` and `before != after` are the
                   same claim stated twice, so they must agree. When they do not,
                   the emission is invalid on its face. Rows it flags are right
                   22% of the time against 44% for rows it clears, so it is also
                   a useful reliability signal where nothing can be repaired.

  swapped()        needs the measured values, which any execution-grounded caller
                   already has. It catches the slip directly rather than by its
                   symptom, including the case where before and after are both
                   present but exchanged.

A caller that has run the code should repair(); one that has not must not present
a self-contradicting result as fact.
"""
from __future__ import annotations

import re

__all__ = ["norm", "contradiction", "swapped", "repair", "direction_reversed",
           "unmeasured_claim", "phantom_removal"]


def norm(v) -> str:
    """Compare values the way the eval does: whitespace-insensitive, as text."""
    return " ".join(str("" if v is None else v).split())


def contradiction(obj: dict) -> str | None:
    """Why this emission contradicts itself, or None if it is coherent.

    Consults no ground truth -- `differs` and `before != after` are the same
    claim, so disagreement is decidable from the object alone.
    """
    if not isinstance(obj, dict):
        return None
    d = obj.get("differs")
    if not isinstance(d, bool) or "before" not in obj or "after" not in obj:
        return None                      # not the v2 contract; nothing to check
    same = norm(obj.get("before")) == norm(obj.get("after"))
    if d and same:
        return "says behaviour differs but reports one value for both sides"
    if not d and not same:
        return "says behaviour is unchanged but reports two different values"
    return None


def swapped(obj: dict, before: str, after: str) -> bool:
    """True when the model put the measured AFTER where BEFORE belongs.

    Requires the measurement to be informative: if the two sides are equal there
    is no direction to get wrong.
    """
    if not isinstance(obj, dict) or norm(before) == norm(after):
        return False
    gb, ga = norm(before), norm(after)
    mb, ma = norm(obj.get("before")), norm(obj.get("after"))
    if mb == ga and ma == gb:
        return True                       # both sides present, exchanged
    return mb == ga and mb == ma          # the observed failure: after in both


def repair(obj: dict, before: str, after: str | None = None) -> tuple[dict, str | None]:
    """Pin the pre-state from the measurement, keep the model's value as `after`.

    Only for callers that actually ran the code -- `before` must be measured, not
    guessed. Returns (object, note) where note describes what was corrected, or
    None if nothing was. The object is copied; the caller's dict is untouched.
    """
    why = contradiction(obj)
    if why is None and not (after is not None and swapped(obj, before, after)):
        return obj, None
    fixed = dict(obj)
    fixed["before"] = before
    if fixed.get("differs") is False and norm(fixed.get("after")) != norm(before):
        fixed["differs"] = True           # its own values outvote its verdict
    return fixed, f"pre-state taken from the measurement ({why or 'sides exchanged'})"


# ------------------------------------------------------------------ the prose
# The reviewer discards the model's before/after and keeps only `explanation`,
# so the slip reaches the user as a sentence with the direction backwards. The
# existing number check cannot see it: both values are quoted from the
# measurement, so nothing looks invented. Direction is what has to be checked.
_FROM_TO = re.compile(
    r"(?:from|was)\s+(?P<a>[^,;]{1,80}?)\s+(?:to|into|and\s+is\s+now|,?\s*now)\s+(?P<b>[^,;.]{1,80})",
    re.I)


def direction_reversed(expl: str, before: str, after: str) -> str | None:
    """Why this sentence states the change backwards, or None.

    Conservative by construction: it fires only when one side of a `from X to Y`
    is found verbatim in the opposite measurement and NOT in its own, so a value
    common to both sides can never trigger it.
    """
    if not expl or norm(before) == norm(after):
        return None
    b, a = norm(before), norm(after)
    for m in _FROM_TO.finditer(expl):
        x, y = norm(m.group("a")).strip("`'\" "), norm(m.group("b")).strip("`'\" ")
        if not x or not y or x == y:
            continue
        if (x in a and x not in b) and (y in b and y not in a):
            return f"states the change as {x!r} -> {y!r}; the measurement is the reverse"
    return None


# ---------------------------------------------------- claims nothing measured
# The SYSTEM prompt tells the model not to assert safety when nothing was
# observed. Observed failure, on a diff changing `range(1, n)` to
# `range(1, n + 1)` against a baseline that was already failing:
#
#   "...which is a non-functional change that does not affect the program's
#    behavior. The project still fails with exit 5: no tests ran in 0.00s."
#
# The second sentence is measured and correct. The first is a safety verdict on
# a genuine off-by-one, produced where the tool established nothing either way,
# and neither the invented-number check nor the direction check can see it --
# it invents no number and states no direction. An instruction the model can
# ignore is not a guarantee; this is the enforcement.
_ASSERTS_SAFE = [
    re.compile(p, re.I) for p in (
        r"\b(?:does|do|did|will|would)\s+not\s+(?:affect|change|alter|impact|break)\b",
        r"\bno\s+(?:effect|impact|functional\s+change|behaviou?ral\s+change)\b",
        r"\bno\s+change\s+in\s+behaviou?r\b",
        r"\bnon-?functional\b",
        r"\bfunctionally\s+equivalent\b",
        r"\b(?:is|are|remains?|stays?)\s+(?:safe|harmless|unaffected)\b",
        r"\bbehaviou?r\s+(?:is|remains?|stays?)\s+(?:the\s+same|unchanged|identical)\b",
        r"\b(?:purely\s+)?cosmetic\b",
    )
]
_ASSERTS_BROKEN = [
    re.compile(p, re.I) for p in (
        r"\bwill\s+(?:fail|crash|throw|break|error|return\s+the\s+wrong)\b",
        r"\b(?:is|introduces|causes|creates)\s+(?:an?\s+)?(?:bug|defect|regression|off-by-one)\b",
        r"\bis\s+(?:incorrect|wrong|broken|buggy)\b",
    )
]
# Attributing a RUNTIME OUTCOME to the change. Distinct from the two lists
# above: this is not a verdict word, it is a causal claim about a run.
# Observed slipping through both of them, on a file whose baseline was already
# failing for an unrelated reason:
#
#   "...causing the program to fail because the loop no longer includes the
#    upper bound. The output remains 0, but the program's exit status changed
#    to 5."
#
# Every number there is in the measurement, so the invented-number check clears
# it, and none of the verdict words appear. But the exit status did not change
# -- it was 5 before the commit too -- and no output of 0 was ever produced.
_ATTRIBUTES_RUN = [
    re.compile(p, re.I) for p in (
        r"\bcaus(?:es|ed|ing)\b[^.]{0,40}?\bto\s+(?:fail|crash|break|error|throw)\b",
        r"\b(?:results?|resulted|resulting)\s+in\b[^.]{0,30}?\b(?:failure|crash|error)\b",
        r"\bleads?\s+to\b[^.]{0,30}?\b(?:failure|crash|error)\b",
        r"\bmak(?:es|ing)\b[^.]{0,30}?\b(?:fail|crash|break)\b",
        r"\bexit\s+(?:status|code)\s+(?:changed|becomes?|is\s+now|went)\b",
        r"\bthe\s+(?:program|run|command|tests?)\s+(?:now\s+)?(?:fails?|crashes?|errors?|passes?|succeeds?)\b",
        # Observed printed as a finding: "The project still fails, so the change
        # did not resolve the issue", on a file whose baseline was already
        # broken. The first clause RESTATES the measurement and is fine (see the
        # `is None` cases in test_exec_contract.py); the second INFERS that the
        # change failed to achieve something, which nothing established. Only
        # the inference is caught here.
        r"\b(?:did|does|do|would|will)\s+not\s+(?:resolve|fix|address|solve)\b",
    )
]
# Claims to have OBSERVED something. Legitimate where output really was compared
# (identical output is a measurement); never legitimate where the baseline was
# already broken, because both runs failed for a reason unrelated to this file.
_CLAIMS_OBSERVED = [
    re.compile(p, re.I) for p in (
        r"\bthe\s+output\s+(?:remains?|stays?|is\s+still|became?|changed|is\s+now)\b",
        r"\bstill\s+(?:prints?|outputs?|returns?)\b",
    )
]


def unmeasured_claim(expl: str, baseline_broken: bool = False) -> str | None:
    """Why this sentence claims more than an unexercised run can support.

    For the cases where the tool observed NOTHING -- identical output, or a
    baseline that was already failing. "This was not exercised, so I cannot
    tell" is the correct answer there; both "it is fine" and "it is a bug" are
    verdicts on evidence that does not exist.

    Says nothing about prose on a measured outcome: after a run that really did
    fail, "will fail" is a report, not a guess.

    `baseline_broken` tightens it. Where the run failed identically on both
    sides for an unrelated reason, statements about what was OBSERVED are
    unsupported too -- the exit status belongs to the broken baseline, not to
    this change. Where output really was compared, "the output is unchanged" is
    a measurement and stays allowed.
    """
    checks = [(_ASSERTS_SAFE, "claims the change is harmless"),
              (_ASSERTS_BROKEN, "claims the change is a defect"),
              (_ATTRIBUTES_RUN, "blames the run's outcome on this change")]
    if baseline_broken:
        checks.append((_CLAIMS_OBSERVED, "reports an observation that was never made"))
    for group, why in checks:
        for rx in group:
            m = rx.search(expl or "")
            if m:
                return f"{why} ({m.group(0)!r}) with nothing measured"
    return None


# ------------------------------------------------- removals that never happened
# Given the real compiler error `h.EventCache.Version undefined`, the model
# explained it as "the `Version` method was removed from the `EventCache`
# interface". Nothing was removed: the diff ADDS a call to a method that does
# not exist. The direction check cannot see this -- there are no measured values
# to be the wrong way round -- and every symbol named really is in the text.
#
# But it is decidable. If prose says a named thing was removed, a line starting
# with `-` should mention it. When none does, the claim is about a deletion the
# diff does not contain.
_GONE = r"(?:removed|deleted|dropped|stripped)"
_KIND = r"(?:method|function|field|call|parameter|argument|variable|property)"
_NAME = r"`?(?P<name>[A-Za-z_][\w.]{2,})`?"
_REMOVED = [
    # passive: "the `Version` method was removed"
    re.compile(rf"{_NAME}\s+{_KIND}?\s*(?:was|were|has been|have been|is|are)"
               rf"\s+{_GONE}", re.I),
    # active: "which removes the `cacheVersion` variable from the `Set` call".
    # The subject is restricted to the CHANGE itself. Without that, "the
    # function removes whitespace" -- a description of runtime behaviour, not of
    # the diff -- would be read as a claim about a deleted line.
    re.compile(rf"(?:the\s+(?:change|commit|diff|edit|patch)|this|it|which)\s+"
               rf"(?:also\s+)?(?:removes|deletes|drops|strips|{_GONE})\s+"
               rf"(?:the\s+)?{_NAME}", re.I),
]


def _code_like(name: str, expl: str) -> bool:
    """Is this a symbol, or just an English word?

    "removes the leading zeros" names no symbol, and looking for `leading` among
    the removed lines would flag a true sentence. A symbol is backticked, or
    carries an underscore or dot, or is camelCase, or is capitalised.
    """
    return (f"`{name}`" in expl or "_" in name or "." in name
            or name[:1].isupper()
            or any(a.islower() and b.isupper() for a, b in zip(name, name[1:])))


# A name introduced by one of these is the OBJECT of a phrase, not the subject
# of the sentence, so a following "is dropped" describes a runtime value rather
# than a deleted line. Observed: "a write racing a `Clear` is dropped" -- a
# correct reading of a cache generation guard -- was rejected as claiming
# `Clear` had been deleted from the diff. The ACTIVE pattern already guards
# against this confusion by restricting its subject to the change itself; the
# passive one had no such guard, and prose about runtime behaviour hits it
# constantly.
_OBJECT_OF = re.compile(
    r"\b(?:with|from|by|against|into|onto|than|via|racing|holding|using|"
    r"calling|matching|carrying|beating|after|before|during|for|to|of|on|in|at)"
    r"\s+(?:an?|the|its|their|any|some)?\s*`?$", re.I)


def phantom_removal(expl: str, diff: str) -> str | None:
    """Why this sentence describes a deletion the diff does not contain."""
    expl = expl or ""
    m = None
    for rx in _REMOVED:
        for cand in rx.finditer(expl):
            if not _code_like(cand.group("name"), expl):
                continue
            if _OBJECT_OF.search(expl[:cand.start("name")]):
                continue          # object of a phrase: not a claim about a line
            m = cand
            break
        if m:
            break
    if m is None:
        return None
    name = m.group("name").split(".")[-1]
    for line in (diff or "").splitlines():
        if line.startswith("-") and not line.startswith("---") and name in line:
            return None
    return (f"says {name!r} was removed, but no removed line in the diff "
            f"mentions it")
