"""Execute the model's concrete claims and see whether they hold.

    from llm_explainer.verify import check_answer
    report = check_answer(analysis_dict, diff, language="python")

Why this exists
---------------
The v3 contract dropped `before`/`after` because a model that cannot run the
code cannot know a concrete value: across four checkpoints and 101 executable
cases those fields were right 15-31% of the time, and 69-85% of answers carried
a concrete claim that running the code contradicts.

Dropping the field did not stop the model making the claim. It moved it into the
prose. Observed 1 Sep on TestJIT/pyalgo, from `sft-v6-suggest-seed7`:

    "count_positive([1, -2, 3]) returns 2 instead of 1"   <- 2 IS correct
    "sum_to(5) returns 15 instead of 15"                  <- identical values

So the claim is still there, still concrete, still checkable - just no longer in
a field anything reads. This extracts those claims and runs them.

What it does NOT do
-------------------
This is a MEASUREMENT, not a filter. `bench/check_field_audit.py` and the
grounding rule in `evaluate.py` are the cautionary precedent: `grounded()`
looked like an obvious output filter and, measured against the hand grades,
removed 100% of the true positives to remove 25% of the false ones. Anything
here should be scored before it is ever allowed to suppress an answer.

Scope, honestly
---------------
Only Python, only when the callee is defined in the code it is handed, and only
for calls whose arguments are literals. A claim about axios or Spring Boot is
reported `unverifiable`, not `wrong` - the distinction matters, because most
claims on real commits will land there and counting them as failures would
overstate the result.

Executing model-suggested calls means executing code. Everything runs in a
subprocess with a timeout and no arguments the caller did not supply; it is
still only safe for code you already trust, which in this repo means the
synthetic bench cases and TestJIT, not arbitrary upstream commits.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from dataclasses import dataclass, field

# `f(args)` followed by a claimed value. The call may be backticked; the value
# may be backticked, quoted, or bare. Nested parens in the args are not matched
# on purpose - `f(g(1))` is rare here and admitting it costs a lot of false
# matches on ordinary prose.
_CLAIM = re.compile(
    r"`?\b([A-Za-z_]\w*)\(([^()]*)\)`?\s*"
    r"(?:returns?|return|==|=|evaluates? to|yields?|gives?|produces?)\s+"
    r"`?([^\s,.;`)]+)`?",
    re.I,
)

# "X instead of Y" - the shape that carries the contradiction. Captured so a
# claim whose two halves are identical ("15 instead of 15") is visible as its
# own defect rather than silently scoring as correct.
_INSTEAD = re.compile(r"`?([^\s,.;`)]+)`?\s+instead of\s+`?([^\s,.;`)]+)`?", re.I)

VERIFIED = "verified"
CONTRADICTED = "contradicted"
UNVERIFIABLE = "unverifiable"
DEGENERATE = "degenerate"     # "N instead of N" - claims a change to the same value
# "X instead of Y" about a function this diff ADDS. There is no prior value for
# a function that did not exist, so the comparison cannot be true whatever X is.
# Found the first time this ran on live output: the model wrote
# "count_positive([1, -2, 3]) returns 2 instead of 1" on the commit that adds
# count_positive. 2 is CORRECT, so a value check alone scores it `verified` and
# misses that the finding is fabricated - it reports right behaviour as a bug.
INCOHERENT = "incoherent"


@dataclass
class Claim:
    call: str            # "count_positive([1, -2, 3])"
    func: str            # "count_positive"
    args: str            # "[1, -2, 3]"
    claimed: str         # "2"
    instead_of: str | None = None
    status: str = UNVERIFIABLE
    actual: str | None = None
    note: str = ""


@dataclass
class Report:
    claims: list[Claim] = field(default_factory=list)

    @property
    def contradicted(self) -> int:
        return sum(1 for c in self.claims if c.status == CONTRADICTED)

    @property
    def verified(self) -> int:
        return sum(1 for c in self.claims if c.status == VERIFIED)

    @property
    def degenerate(self) -> int:
        return sum(1 for c in self.claims if c.status == DEGENERATE)

    @property
    def incoherent(self) -> int:
        return sum(1 for c in self.claims if c.status == INCOHERENT)

    def __bool__(self) -> bool:
        return bool(self.claims)


def prose_of(analysis: dict) -> str:
    """Summary plus every finding explanation - where concrete claims now live.

    `effect.check` is included because the v6 `check` field is a sentence about
    what to run, and a sentence about what to run can assert a value too.
    """
    parts = [analysis.get("summary") or ""]
    eff = analysis.get("effect") or {}
    parts.append(eff.get("check") or "")
    for f in analysis.get("findings") or []:
        parts.append(f.get("explanation") or "")
    return "\n".join(p for p in parts if p)


def extract_claims(text: str) -> list[Claim]:
    """Every `f(literal args) -> value` assertion in the text."""
    out: list[Claim] = []
    for m in _CLAIM.finditer(text):
        func, args, claimed = m.group(1), m.group(2).strip(), m.group(3).strip()
        # Only literal arguments can be replayed; a call on a local variable
        # cannot be reconstructed from prose and is not a failure of the model.
        try:
            ast.literal_eval(f"({args},)" if args else "()")
        except (ValueError, SyntaxError):
            continue
        c = Claim(call=f"{func}({args})", func=func, args=args, claimed=claimed)
        tail = text[m.end():m.end() + 60]
        inst = _INSTEAD.match(tail.strip()) or _INSTEAD.search(
            text[max(0, m.start() - 5):m.end() + 60])
        if inst:
            c.instead_of = inst.group(2)
        out.append(c)
    return out


# `def name(` as a fallback for code that does not parse. A diff fragment - or
# a multi-file diff flattened into one string - is usually not a valid module,
# and refusing to look at it costs the `incoherent` verdict entirely.
_DEF = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+([A-Za-z_]\w*)[ \t]*\(",
                  re.MULTILINE)


def _defs(code: str) -> set[str]:
    """Function names defined in `code`, tolerating fragments."""
    try:
        return {n.name for n in ast.walk(ast.parse(code))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    except SyntaxError:
        return set(_DEF.findall(code))


def _run(code: str, timeout: float) -> tuple[bool, str]:
    """Run a snippet in a subprocess. Returns (ok, stdout-or-error)."""
    try:
        p = subprocess.run([sys.executable, "-I", "-c", code],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s"
    if p.returncode != 0:
        return False, (p.stderr.strip().splitlines() or ["non-zero exit"])[-1]
    return True, p.stdout.strip()


def verify_python(claims: list[Claim], code: str, timeout: float = 5.0,
                  pre_code: str | None = None) -> None:
    """Replay each claim against `code`, setting status/actual in place.

    `code` must define the callee. Anything else is left `unverifiable` - the
    common case on real commits, and not a mark against the model.

    `pre_code` is the pre-commit side. Given it, an "X instead of Y" claim about
    a function that only exists AFTER the change is marked `incoherent`: the
    comparison has no prior value to be against. Checking the value alone is not
    enough, because the model can quote the right number and still be wrong
    about what it means.
    """
    # The degenerate check needs no code and must run even when nothing parses:
    # a multi-file diff concatenates fragments from several files and is not
    # valid Python, and aborting there silently downgraded "15 instead of 15"
    # to `unverifiable` - the one verdict that needs no execution at all.
    for c in claims:
        if c.instead_of is not None and c.claimed == c.instead_of:
            c.status = DEGENERATE
            c.note = f"claims {c.claimed} instead of {c.instead_of} - same value"

    defined = _defs(code)
    before = _defs(pre_code) if pre_code else set()

    for c in claims:
        if c.status == DEGENERATE:
            continue
        if (c.instead_of is not None and pre_code is not None
                and c.func in defined and c.func not in before):
            c.status = INCOHERENT
            c.note = (f"{c.func} is added by this diff - there is no prior "
                      f"value for it to return {c.instead_of} instead of")
            continue
        if c.func not in defined:
            c.note = f"{c.func} is not defined in the code under test"
            continue
        ok, out = _run(f"{code}\n\nprint(repr({c.call}))", timeout)
        if not ok:
            c.note = f"could not execute: {out}"
            continue
        c.actual = out
        # Compare on value, not on spelling: "2" and "2.0" and "'2'" are
        # different strings and the same answer to a reader.
        try:
            same = ast.literal_eval(out) == ast.literal_eval(c.claimed)
        except (ValueError, SyntaxError):
            same = out.strip("'\"") == c.claimed.strip("'\"")
        c.status = VERIFIED if same else CONTRADICTED


def check_answer(analysis: dict, code: str | None = None,
                 timeout: float = 5.0, pre_code: str | None = None) -> Report:
    """Extract the answer's concrete claims and, given code, execute them."""
    claims = extract_claims(prose_of(analysis))
    if code:
        verify_python(claims, code, timeout, pre_code)
    else:
        for c in claims:
            if c.instead_of is not None and c.claimed == c.instead_of:
                c.status = DEGENERATE
                c.note = f"claims {c.claimed} instead of {c.instead_of} - same value"
    return Report(claims=claims)


def added_python(diff: str) -> str:
    """The post-commit side of a diff, as runnable Python.

    Added and context lines only: a removed line is not in the program any more,
    and including it would define the function twice with the older body last.
    """
    out = []
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "diff --git", "index ", "@@")):
            continue
        if line.startswith("-"):
            continue
        out.append(line[1:] if line.startswith("+") else line)
    return "\n".join(out)


def removed_python(diff: str) -> str:
    """The pre-commit side of a diff, as runnable Python.

    The twin of `added_python`, and the thing that makes an `incoherent` verdict
    possible without checking the repository out: a function present in the
    added side and absent from this one is introduced by the change, so any
    "X instead of Y" claim about it has no prior value to be against.
    """
    out = []
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "diff --git", "index ", "@@")):
            continue
        if line.startswith("+"):
            continue
        out.append(line[1:] if line.startswith("-") else line)
    return "\n".join(out)


def check_against_diff(analysis: dict, diff: str, timeout: float = 5.0) -> Report:
    """`check_answer`, taking both sides of the code straight from the diff.

    Convenience for callers that have a diff and no checkout - the TUI, mainly.
    Never raises: a verifier fault must not take the review down with it, since
    an unannotated answer is still worth reading and a crashed pane is not.
    """
    try:
        return check_answer(analysis, added_python(diff), timeout,
                            pre_code=removed_python(diff))
    except Exception:
        return Report(claims=[])


def _selftest() -> None:
    src = ("def count_positive(xs):\n"
           "    c = 0\n"
           "    for x in xs:\n"
           "        if x > 0:\n"
           "            c += 1\n"
           "    return c\n"
           "\n"
           "def sum_to(n):\n"
           "    return sum(range(1, n + 1))\n")

    # the real 1 Sep output: the claimed value is wrong, the true answer is 2
    r = check_answer({"summary": "count_positive([1, -2, 3]) returns 1",
                      "findings": []}, src)
    assert r.claims and r.claims[0].status == CONTRADICTED, r.claims
    assert r.claims[0].actual == "2", r.claims[0].actual

    # a correct claim must pass
    r = check_answer({"summary": "count_positive([1, -2, 3]) returns 2",
                      "findings": []}, src)
    assert r.claims[0].status == VERIFIED, r.claims[0]

    # "15 instead of 15" is caught without running anything
    r = check_answer({"summary": "sum_to(5) returns 15 instead of 15",
                      "findings": []}, src)
    assert r.claims[0].status == DEGENERATE, r.claims[0]

    # the 1 Sep TUI case: the VALUE is right (2) but count_positive is added by
    # the diff, so "instead of 1" cannot be true. A value check alone says
    # `verified` here, which is why this status exists.
    pre = "def sum_to(n):\n    return sum(range(1, n + 1))\n"
    r = check_answer({"summary": "count_positive([1, -2, 3]) returns 2 instead of 1",
                      "findings": []}, src, pre_code=pre)
    assert r.claims[0].status == INCOHERENT, r.claims[0]
    # without pre_code it is only a value check, and the value is right
    r = check_answer({"summary": "count_positive([1, -2, 3]) returns 2 instead of 1",
                      "findings": []}, src)
    assert r.claims[0].status == VERIFIED, r.claims[0]

    # a callee that is not in the code is unverifiable, NOT wrong
    r = check_answer({"summary": "divide(1, 0) returns 0", "findings": []}, src)
    assert r.claims[0].status == UNVERIFIABLE, r.claims[0]

    # prose with no concrete claim yields no claims at all
    r = check_answer({"summary": "This looks like a logic error in stats.py.",
                      "findings": []}, src)
    assert not r.claims, r.claims

    # non-literal arguments are skipped rather than guessed at
    assert not extract_claims("count_positive(xs) returns c")

    # the diff's post-commit side is runnable
    diff = ("--- a/s.py\n+++ b/s.py\n@@ -1,2 +1,2 @@\n"
            "-def f():\n-    return 1\n+def f():\n+    return 2\n")
    r = check_answer({"summary": "f() returns 1", "findings": []},
                     added_python(diff))
    assert r.claims[0].status == CONTRADICTED and r.claims[0].actual == "2"

    print("verify selftest ok")


if __name__ == "__main__":
    _selftest()
