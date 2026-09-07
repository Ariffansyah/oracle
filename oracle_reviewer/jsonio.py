"""Recovering the model's JSON answer, including when it is malformed.

There were five byte-identical copies of `first_json` in this tree (bench x3,
`review.py`, `core.py`), and all five lost an answer the same way: they matched
braces by counting `{` and `}` over the RAW TEXT, with no notion of a string
literal. So an answer whose measured `before` quoted a failure containing a lone
brace -- `SyntaxError: unexpected {` -- had its object cut at the wrong index,
failed to parse, and was scored as "the model produced nothing".

Measured on the 458 BugsInPy rows: 18 rows produced no explanation, 16 of them
on BOTH seeds, and a brace in the measured before/after is 8x enriched among
them (33% against a 4% base rate). That is not model noise. It is this function.

It also mattered in production, not just in the bench: `oracle_reviewer.core`
and `review.py` carried the same copy, so a review of a commit whose failure
message contained a brace silently printed no prose.

Five recoverable shapes, in the order they are tried:

  1. valid JSON                        -- the normal case
  2. control characters in a string    -- `strict=False`; a real newline inside
                                          a quoted traceback is not legal JSON
                                          but is exactly what a 3B emits
  3. trailing comma before } or ]      -- a very common small-model slip
  4. a Python repr with single quotes  -- `ast.literal_eval`, not a quote swap
  5. truncated mid-answer              -- close the open string and the open
                                          braces, then reparse

and if all of those fail, the `explanation` field is pulled out by regex, which
is the one field every caller actually reads.

Nothing here invents content. Every repair is syntactic; if a repair changes
what the model SAID, that is a bug in this file.
"""
from __future__ import annotations

import ast
import json
import re

__all__ = ["first_json", "first_json_ex", "spans", "loads_lenient",
           "REPAIRS_TRUNCATED"]

# Repairs after which the recovered prose may STOP MID-CLAUSE. A caller that
# displays the explanation to a person has to trim the tail; a caller that only
# scores it does not care. `oracle_reviewer.core` is the first kind.
REPAIRS_TRUNCATED = ("truncated", "truncated+trailing-comma", "explanation-only")

_EXPL = re.compile(r'"explanation"\s*:\s*"((?:[^"\\]|\\.)*)"', re.S)


def spans(text: str):
    """Yield (start, end) of every top-level {...} that is balanced OUTSIDE
    string literals. `end` is exclusive. A run that never closes yields the
    tail, so a truncated answer is still offered to the repairs."""
    i, n = 0, len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth, in_str, esc = 0, False, False
        for j in range(i, n):
            c = text[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    yield i, j + 1
                    break
        else:
            yield i, n          # never closed -- truncated
        i += 1


def _close(frag: str) -> str:
    """Close an answer the model ran out of tokens in the middle of."""
    depth, in_str, esc = 0, False, False
    for c in frag:
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
    if in_str:
        frag = frag.rstrip("\\") + '"'
    # a dangling `"key":` with no value cannot be closed into anything true
    frag = re.sub(r',\s*"[^"]*"\s*:\s*$', "", frag.rstrip().rstrip(","))
    return frag + "}" * max(0, depth)


def _loads(frag: str):
    """(dict, repair-label) or (None, None). Never raises.

    The label names what had to be done, because it changes what a caller may
    do with the result: a truncated recovery can end mid-clause, and prose that
    ends mid-clause must not be shown to a developer as a finished sentence.
    """
    for label, attempt in (
        (None, lambda s: json.loads(s, strict=False)),
        ("trailing-comma",
         lambda s: json.loads(re.sub(r",\s*([}\]])", r"\1", s), strict=False)),
        ("python-repr", lambda s: ast.literal_eval(s)),
        ("truncated", lambda s: json.loads(_close(s), strict=False)),
        ("truncated+trailing-comma",
         lambda s: json.loads(re.sub(r",\s*([}\]])", r"\1", _close(s)),
                              strict=False)),
    ):
        try:
            v = attempt(frag)
        except Exception:
            continue
        if isinstance(v, dict):
            return v, label
    return None, None


def loads_lenient(frag: str):
    """Every repair, in order. Returns a dict or None. Never raises."""
    return _loads(frag)[0]


def first_json_ex(text: str) -> tuple[dict | None, str | None]:
    """(first JSON object, repair-label). The label is None when it parsed as
    given, and one of REPAIRS_TRUNCATED when the result may be incomplete."""
    if not text:
        return None, None
    for a, b in spans(text):
        v, label = _loads(text[a:b])
        if v is not None:
            return v, label
    m = _EXPL.search(text)          # last resort: the one field callers read
    if m:
        # Nothing here carries `before`/`after`, so `contradiction` and
        # `swapped` cannot run on it. That is why it is labelled: a caller that
        # relies on those checks is being handed prose they never saw.
        try:
            return ({"explanation": json.loads(f'"{m.group(1)}"', strict=False)},
                    "explanation-only")
        except Exception:
            return {"explanation": m.group(1)}, "explanation-only"
    return None, None


def first_json(text: str) -> dict | None:
    """The first JSON object in `text`, repaired if it has to be.

    Same contract as the five copies it replaces: a dict, or None. It differs
    only by returning a dict in cases where they returned None. Callers that
    SHOW the prose to a person want `first_json_ex` instead.
    """
    return first_json_ex(text)[0]
