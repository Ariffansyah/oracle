"""Guards run per sentence, not per paragraph.

    python test_sentence_filter.py

The checks used to run on the whole explanation, so one false clause suppressed
everything around it. Observed verbatim from the app: a two-sentence answer
whose first sentence invented a removal and whose second correctly named the
compiler error was withheld entire, and the true half went with it.
"""

from oracle_reviewer.core import FileReview, filter_prose, review_body, sentences

GO_DIFF = """--- a/events.go
+++ b/events.go
@@ -82,6 +82,7 @@
+    cacheVersion := h.EventCache.Version()
@@ -119,7 +120,7 @@
-    h.EventCache.Set(cacheKey, body)
+    h.EventCache.Set(cacheKey, body, cacheVersion)
"""
REPORTED = ("The change adds a call to `h.EventCache.Version()` in the `ListEvents` "
            "and `GetEvent` handlers, which removes the `cacheVersion` variable "
            "from the `Set` call. This causes the program to fail because the "
            "`Version` method is undefined on the `*cache.Cache` type.")

kept, dropped = filter_prose(REPORTED, "? [no test files]",
                             "exit 1: h.EventCache.Version undefined", GO_DIFF)
assert kept.startswith("This causes the program to fail")
assert "removes the" not in kept          # the invented clause is gone
assert len(dropped) == 1 and "was removed" in dropped[0]

# Splitting must not break on code or decimals: `h.Cache.Set` and `0.12s` have
# no space after the dot, which is what separates a boundary from a symbol.
assert len(sentences("Calls h.Cache.Set(k, v) now. It failed in 0.12s.")) == 2
assert len(sentences("One sentence only")) == 1
assert sentences("") == []

# Every sentence clean -> nothing withheld.
kept, dropped = filter_prose("The output changed from 10 to 15.", "10", "15", "")
assert kept and not dropped

# Every sentence bad -> nothing kept, and the caller falls back to withholding.
kept, dropped = filter_prose("This is safe. It does not affect behavior.",
                             "10", "15", "", measured=False)
assert kept == "" and len(dropped) == 2

# Repeated identical reasons collapse: several sentences failing the same check
# is one fact about the answer, not several.
r = FileReview(path="x", risk="change")
r.before, r.after, r.diff = "10", "15", ""
r.explanation = "The output changed from 10 to 15."
r.withheld = "claims the change is harmless ('is safe') with nothing measured"
body = review_body(r, "python main.py")
assert "The output changed" in body
assert "Part of the explanation was withheld" in body

print("ok")
