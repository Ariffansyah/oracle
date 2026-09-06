"""The honest attempt at prompting the UNTRAINED model into the same job.

`bench/eval_bugsinpy_arms.py` gives every arm the same short SYSTEM, so `base`
vs `exec` isolates the adapter with the prompt held fixed. That answers "is the
fine-tune doing anything", and NOT the question a reviewer asks next: could a
better prompt on the base model have done the same job?

This module is that better prompt, and it is written to WIN. It states the
output shape exactly, names the two failure modes observed in the base arm's own
output -- vague consequence-prose, and asserting that nothing changed -- and
carries three worked examples.

The examples are HAND-WRITTEN and deliberately not BugsInPy rows. Using corpus
rows as demonstrations would leak the evaluation set into the prompt and the
comparison would be worthless. They cover the three shapes the corpus contains:
an exception with a message, an assertion comparing two values, and a bare
assertion naming no exception class -- the last being where the `exec` arm is
weakest (15/60 grounded).

Used by `--prompt strong`. `--prompt plain` is the default and is what produced
every published arm.
"""

SYSTEM = """You are a code reviewer. You are given one commit from a real project, and the MEASURED output of running that project's own test before and after the change.

Write the one or two sentences a developer needs. Answer with one JSON object and one key, "explanation".

Rules, in order of importance:

1. QUOTE THE MEASURED FAILURE VERBATIM. The `before:` line contains the exact text the test produced. Copy it into your sentence character for character, inside backticks. Do not paraphrase it, do not summarise it, do not describe it in your own words. If `before:` says `TypeError: 'int' object is not subscriptable`, then your sentence contains `TypeError: 'int' object is not subscriptable`.

2. If `before:` names no exception class -- a bare `assert x == y` -- quote the two values that were compared instead. There is always something literal to quote.

3. Name the line the diff changed, and say which `+` line removes the cause. A line prefixed `+` was ADDED; a line prefixed `-` was removed. Never say something was removed unless a `-` line shows it being removed.

4. NEVER write that the change has no effect, does not affect behaviour, is cosmetic, or is only a refactor. The measurement shows the test went from failing to passing, so any such sentence is false.

5. Do not write vague consequence-prose. "prevents potential errors", "makes the code more robust", "ensures correctness", "resolves the issue" are worthless to a developer. The quoted failure is the content.

6. Never mention a number or a name that is not in the measurement or the diff."""

_EX1_USER = '''## Commit
fix off-by-one in Window.mean

## Changes
```diff
--- a/stats/window.py
+++ b/stats/window.py
@@ -12,7 +12,7 @@ class Window:
     def mean(self, n):
         values = self._buffer
-        return values[n] / n
+        return values[n - 1] / n
```

## Measured by running the project's own test
before: IndexError: list index out of range
after:  the test passes'''

_EX1_BOT = '''{"explanation": "Indexing `values[n]` read one past the end of the buffer, so the test failed with `IndexError: list index out of range`; the `+` line changes the index to `n - 1` so the last element is read instead."}'''

_EX2_USER = '''## Commit
normalise header casing before lookup

## Changes
```diff
--- a/http/headers.py
+++ b/http/headers.py
@@ -30,7 +30,7 @@ class Headers:
     def get(self, name):
-        return self._store[name]
+        return self._store[name.lower()]
```

## Measured by running the project's own test
before: AssertionError: assert None == 'application/json'
after:  the test passes'''

_EX2_BOT = '''{"explanation": "`self._store[name]` missed the lower-cased key, so `get` returned nothing and the test failed with `AssertionError: assert None == 'application/json'`; the `+` line lower-cases `name` before the lookup."}'''

_EX3_USER = '''## Commit
keep the line separator when joining

## Changes
```diff
--- a/text/render.py
+++ b/text/render.py
@@ -8,4 +8,4 @@ def render(parts):
-    return "".join(parts)
+    return "\\n".join(parts)
```

## Measured by running the project's own test
before: assert 'ab' == 'a\\nb'
after:  the test passes'''

_EX3_BOT = '''{"explanation": "Joining the parts with `\\"\\"` produced `'ab'` where the test expected `'a\\nb'`; the `+` line joins with a newline separator instead."}'''

FEWSHOT = [(_EX1_USER, _EX1_BOT), (_EX2_USER, _EX2_BOT), (_EX3_USER, _EX3_BOT)]


def messages(user: str) -> list[dict]:
    """The full chat turn list: system, the worked examples, then the row."""
    out = [{"role": "system", "content": SYSTEM}]
    for u, a in FEWSHOT:
        out.append({"role": "user", "content": u})
        out.append({"role": "assistant", "content": a})
    out.append({"role": "user", "content": user})
    return out
