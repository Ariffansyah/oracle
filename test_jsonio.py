"""What the old brace-counting parser lost, and what the new one must not.

    python test_jsonio.py

Run as a plain script -- pytest is not installed in this venv.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from oracle_reviewer.jsonio import first_json, spans  # noqa: E402

OK = []


def check(name, got, want):
    OK.append((name, got == want, got, want))


# --- the five shapes the old parser lost -------------------------------------
check("lone { inside a string",
      first_json('{"before": "SyntaxError: unexpected {", "explanation": "x"}'),
      {"before": "SyntaxError: unexpected {", "explanation": "x"})

check("lone } inside a string",
      first_json('{"before": "got }", "explanation": "x"}'),
      {"before": "got }", "explanation": "x"})

check("raw newline inside a string",
      first_json('{"before": "line1\nline2", "explanation": "x"}'),
      {"before": "line1\nline2", "explanation": "x"})

check("trailing comma",
      first_json('{"before": "A", "explanation": "x",}'),
      {"before": "A", "explanation": "x"})

check("python repr with single quotes",
      first_json("{'before': 'A', 'explanation': 'x'}"),
      {"before": "A", "explanation": "x"})

check("truncated mid-string",
      (first_json('{"before": "KeyError", "explanation": "the model ran out')
       or {}).get("explanation"),
      "the model ran out")

check("truncated mid-object",
      (first_json('{"differs": true, "before": "A", "explanation": "x"')
       or {}).get("explanation"),
      "x")

check("truncated on a dangling key",
      (first_json('{"before": "A", "explanation": "x", "after":')
       or {}).get("explanation"),
      "x")

# --- what already worked, and must keep working ------------------------------
check("plain object", first_json('{"a": 1}'), {"a": 1})
check("prose before", first_json('Sure: {"a": 1}'), {"a": 1})
check("prose after", first_json('{"a": 1} hope that helps'), {"a": 1})
check("markdown fenced", first_json('```json\n{"a": 1}\n```'), {"a": 1})
check("nested object",
      first_json('{"a": {"b": 2}, "explanation": "x"}'),
      {"a": {"b": 2}, "explanation": "x"})
check("brace inside the explanation",
      first_json('{"explanation": "the dict {a: 1} is dropped"}'),
      {"explanation": "the dict {a: 1} is dropped"})
check("escaped quote inside a string",
      first_json(r'{"before": "got \"x\"", "explanation": "y"}'),
      {"before": 'got "x"', "explanation": "y"})
check("no json at all", first_json("I could not determine the answer."), None)
check("empty", first_json(""), None)
check("not a dict", first_json('[1, 2, 3]'), None)

# --- the repairs must not INVENT ---------------------------------------------
# A repair is syntactic. If it changes what the model said, that is the bug this
# file exists to prevent.
src = ('{"before": "TypeError: bad {", "after": "1 passed", '
       '"explanation": "the guard was removed"}')
check("repair preserves every value", first_json(src),
      {"before": "TypeError: bad {", "after": "1 passed",
       "explanation": "the guard was removed"})
check("repair does not fabricate a missing field",
      first_json('{"before": "A"}'), {"before": "A"})

# --- the scanner --------------------------------------------------------------
check("spans skips braces in strings", list(spans('{"a": "}"}')), [(0, 10)])
check("spans finds the second object when the first is junk",
      [t[0] for t in spans('{oops} {"a": 1}')], [0, 7])

# --- the repair LABEL, which the deployed path depends on ---------------------
from oracle_reviewer.jsonio import first_json_ex, REPAIRS_TRUNCATED  # noqa: E402

check("clean parse reports no repair",
      first_json_ex('{"explanation": "x"}')[1], None)
check("newline-in-string is not a truncation",
      first_json_ex('{"explanation": "a\nb"}')[1], None)
check("trailing comma is labelled",
      first_json_ex('{"explanation": "x",}')[1], "trailing-comma")
check("python repr is labelled",
      first_json_ex("{'explanation': 'x'}")[1], "python-repr")
check("truncation is labelled",
      first_json_ex('{"explanation": "cut off here')[1], "truncated")
# No brace anywhere, so no span is offered and only the regex can recover it.
check("regex fallback is labelled",
      first_json_ex('I cannot answer. "explanation": "x" -- sorry')[1],
      "explanation-only")
# The scanner should still PREFER a real object nested in junk over the regex.
check("a valid object inside junk beats the regex fallback",
      first_json_ex('junk {{{ "explanation": "x" }'), ({"explanation": "x"}, None))
check("every truncating label is in REPAIRS_TRUNCATED",
      all(l in REPAIRS_TRUNCATED for l in ("truncated", "explanation-only")), True)
check("a clean parse is NOT treated as truncating",
      None in REPAIRS_TRUNCATED, False)

# --- an object quoted INSIDE the prose ---------------------------------------
# Verbatim shape from youtube-dl-25, the last of the 458 rows that still scored
# "the model said nothing" after the brace fix. The explanation quotes JSON and
# does not escape it, so the string ends at the quote before `duration`; the
# outer object then fails and the scanner finds `{"duration": 0}` -- valid, and
# from the middle of a sentence. Returning that is worse than returning None:
# the caller reads `.get("explanation")`, gets nothing, and a correct
# explanation is scored as silence.
_NESTED = ('{"explanation": "detection in `js_to_json` now uses the group '
           'index, which resolves `AssertionError: \'{"duration": 0}\' != '
           '\'{"duration": "00:01:07"}"` by parsing the integer."}')
got, label = first_json_ex(_NESTED)
check("a nested object is not mistaken for the answer",
      got.get("explanation", "").startswith("detection in `js_to_json`"), True)
check("the whole explanation survives, quotes and all",
      "00:01:07" in got.get("explanation", ""), True)
check("and it is labelled as a recovery", label, "explanation-only")

# The greedy read is used ONLY when the strict one was cut short. A value that
# is followed by `,` or `}` is complete and must be taken as written.
check("a well-formed object still parses normally",
      first_json_ex('{"explanation": "clean"}'), ({"explanation": "clean"}, None))
check("a truncated object still reports truncation",
      first_json_ex('{"explanation": "x", "after": "y"')[1], "truncated")
check("an object with no explanation is still returned",
      first_json_ex('{"a": 1}'), ({"a": 1}, None))

bad = [t for t in OK if not t[1]]
for name, ok, got, want in OK:
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        print(f"         got  {got!r}\n         want {want!r}")
print(f"\n{len(OK) - len(bad)}/{len(OK)} passed")
sys.exit(1 if bad else 0)
