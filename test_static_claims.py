"""Facts the diff settles on its own — and, mostly, the ones it does not.

    python test_static_claims.py

The tool's rule is that risk is measured, not guessed. A static claim is allowed
only because the diff decides it outright. So the negative cases matter more
than the positive one: anything the pattern does not match exactly must return
None and fall back to "nothing was established", because a static claim reads
with the same authority as a measured one.
"""

from oracle_reviewer.static_claims import ui_text_change

head = "diff --git a/x.tsx b/x.tsx\n--- a/x.tsx\n+++ b/x.tsx\n@@ -1,3 +1,3 @@\n"
d = lambda body: head + body

# THE case: same element, same attributes, different visible text.
got = ui_text_change(d(' <select>\n'
                       '-  <option value="BANKJATIM">BankJatim</option>\n'
                       '+  <option value="BANKJATIM">Bank Jatim</option>\n'
                       ' </select>\n'))
assert got and len(got) == 1
tag, attrs, before, after = got[0]
assert (tag, before, after) == ("option", "BankJatim", "Bank Jatim")
assert got[0].value == "BANKJATIM"

# The submitted value changing is NOT a text-only change.
assert ui_text_change(d('-  <option value="BANKJATIM">BankJatim</option>\n'
                        '+  <option value="BANK_JATIM">BankJatim</option>\n')) is None

# Both changing is not either.
assert ui_text_change(d('-  <option value="A">Alpha</option>\n'
                        '+  <option value="B">Beta</option>\n')) is None

# An ADDED element is new behaviour, not a relabel.
assert ui_text_change(d(' <select>\n'
                        '+  <option value="DANA">Dana</option>\n')) is None
assert ui_text_change(d('-  <option value="DANA">Dana</option>\n')) is None

# A different element is not a relabel.
assert ui_text_change(d('-  <option value="A">Alpha</option>\n'
                        '+  <label value="A">Beta</label>\n')) is None

# Interpolated text is not plain text -- what it renders is not in the diff.
assert ui_text_change(d('-  <span>{payoutProvider === "GOPAY" ? "a" : "b"}</span>\n'
                        '+  <span>{isEWallet ? "a" : "b"}</span>\n')) is None

# Whitespace-only is nothing to report.
assert ui_text_change(d('-  <option value="A">Alpha</option>\n'
                        '+  <option value="A">Alpha </option>\n')) is None

# Real logic must never be filed as a text change. This is the other commit
# from the same file: it adds options AND rewrites a condition.
assert ui_text_change(d('-    if (payoutProvider === "GOPAY") {\n'
                        '+    if (isEWallet) {\n')) is None
assert ui_text_change(d('+  const isEWallet = ["GOPAY"].includes(p);\n')) is None

# A mixed diff -- one relabel plus one logic line -- must NOT be reported as a
# text change on the strength of the half that matches.
assert ui_text_change(d('-  <option value="A">Alpha</option>\n'
                        '+  <option value="A">Alpha One</option>\n'
                        '-    if (a === "GOPAY") {\n'
                        '+    if (b) {\n')) is None

# Several relabels at once are fine, and every value is reported.
got = ui_text_change(d('-  <option value="A">Alpha</option>\n'
                       '+  <option value="A">Alpha One</option>\n'
                       ' <br/>\n'
                       '-  <option value="B">Beta</option>\n'
                       '+  <option value="B">Beta Two</option>\n'))
assert got and len(got) == 2 and [c.value for c in got] == ["A", "B"]

# An element with no value attribute is still a relabel, just without the
# claim about what gets submitted.
got = ui_text_change(d('-  <h1>Old</h1>\n+  <h1>New</h1>\n'))
assert got and got[0].value is None

assert ui_text_change("") is None
assert ui_text_change(head) is None

# ------------------------------------------------------- restating the change
# `ui_text_change` answers one shape of diff completely. Most diffs are not that
# shape, and for those the review used to say only that nothing was established
# — true, but it left the reader to reconstruct the edit themselves. What is
# always available without a run is what the edit DID, token for token.
from oracle_reviewer.static_claims import describe, one_change

assert one_change("for i in range(1, n):", "for i in range(1, n + 1):") == ("n):", "n + 1):")

# An operator alone is the edit but not the meaning. `<=` -> `<` used to report
# as "removed `=`", because `<=` tokenised as two characters. Operators are one
# token now, and a span with no operand widens right until it has one.
assert one_change("for i := 1; i <= n; i++ {", "for i := 1; i < n; i++ {") == ("<= n", "< n")
assert one_change("if (a == b) {", "if (a != b) {") == ("== b", "!= b")
assert one_change("total = total + i", "total = total - i") == ("+ i", "- i")
# A span that already names an operand is left alone.
assert one_change("reward = kills * 10", "reward = kills * 20") == ("10", "20")
assert one_change('if (p === "GOPAY") {', "if (isEWallet) {") == ('p === "GOPAY"', "isEWallet")
assert one_change("reward = kills * 10", "reward = kills * 20") == ("10", "20")
assert one_change("a = 1", "a = 1") is None                 # nothing changed
assert one_change("a = 1; b = 2", "a = 9; b = 8") is None   # two spans, not one

# The whole point of one span: naming the first of several would describe the
# line inaccurately, so it declines instead.
assert describe("@@ -1,1 +1,1 @@\n-a = 1; b = 2\n+a = 9; b = 8\n") == ["line 1: rewritten"]

got = describe('@@ -113,1 +114,1 @@\n-    if (payoutProvider === "GOPAY") {\n'
               '+    if (isEWallet) {\n')
# 114, not 113: the hunk is @@ -113,7 +114,7 @@ and the citation is the NEW file.
assert got == ['line 114: `payoutProvider === "GOPAY"` became `isEWallet`'], got

# Blank lines added or removed are not worth a sentence.
assert describe("@@ -1,1 +1,2 @@\n c\n+\n") == []

# Lines paired by POSITION within a run do not necessarily correspond. Calling
# two unrelated lines a rewrite would invent a relationship, so they are
# reported separately.
# Measured ratios: an edited condition scores 0.367 and pairs; this unrelated
# replacement scores 0.211 and does not.
got = describe("@@ -1,2 +1,2 @@\n-import os\n+const x = veryDifferentThing(1, 2, 3)\n")
assert got == ["line 1: removed `import os`",
               "line 1: added `const x = veryDifferentThing(1, 2, 3)`"], got

# Pure additions and deletions are named as such.
assert describe("@@ -0,0 +1,1 @@\n+def add(a, b):\n") == ["line 1: added `def add(a, b):`"]
assert describe("@@ -1,1 +0,0 @@\n-def add(a, b):\n") == ["line 1: removed `def add(a, b):`"]

# Long diffs are cut rather than dumped.
many = "@@ -1,9 +1,9 @@\n" + "".join(f"-x{i} = 1\n+x{i} = 2\n" for i in range(9))
out = describe(many)
assert len(out) == 7 and out[-1] == "…", out

assert describe("") == []

# ------------------------------------------------ grouping and broadening
# Six added <option> lines are ONE fact, not six. Spending the budget on them
# pushed the line that mattered past the cut.
from oracle_reviewer.static_claims import broadened

EW = """@@ -32,6 +32,7 @@
   );
+  const isEWallet = ["GOPAY", "DANA", "SHOPEEPAY"].includes(payoutProvider);
 
@@ -113,7 +114,7 @@
 
-    if (payoutProvider === "GOPAY") {
+    if (isEWallet) {
       const goPayNum = formData.get("x") as string;
@@ -287,19 +288,23 @@
                   <option value="GOPAY">GoPay</option>
+                  <option value="DANA">Dana</option>
+                  <option value="SHOPEEPAY">Shoppe Pay</option>
                   <option value="BCA">BCA</option>
+                  <option value="BRI">BRI</option>
                 </select>
"""
got = describe(EW)
assert got[0].startswith('the `payoutProvider === "GOPAY"` test became `isEWallet`'), got[0]
assert "`DANA`, `SHOPEEPAY`" in got[0]
assert any("added 3 `<option>` entries" in g for g in got), got
# the sentence subsumes the const definition and the substitution, so neither
# is repeated underneath it
assert not any("const isEWallet" in g for g in got), got
assert not any("became `isEWallet`" in g for g in got[1:]), got

name, sentence = broadened(EW)
assert name == "isEWallet"

# Both halves must be in THIS diff, or nothing is claimed. A substitution whose
# definition is not added here could be anything at all.
assert broadened("@@ -1,1 +1,1 @@\n-    if (p === \"GOPAY\") {\n+    if (isEWallet) {\n") is None
# A definition with no substitution is not a broadening either.
assert broadened('@@ -1,0 +1,1 @@\n+  const x = ["A"].includes(p);\n') is None
# The subject has to match: `q === "A"` is not widened by a test on `p`.
assert broadened('@@ -1,2 +1,2 @@\n+  const x = ["A","B"].includes(p);\n'
                 '-  if (q === "A") {\n+  if (x) {\n') is None
# Nor when the list adds nothing beyond the value already tested.
assert broadened('@@ -1,2 +1,2 @@\n+  const x = ["A"].includes(p);\n'
                 '-  if (p === "A") {\n+  if (x) {\n') is None

# Long lines are cut on a boundary with an ellipsis, never mid-token.
long_add = describe("@@ -0,0 +1,1 @@\n+  const isEWallet = "
                    '["GOPAY", "DANA", "SHOPEEPAY"].includes(payoutProvider);\n')[0]
assert long_add.endswith("…`"), long_add
assert "includes(pa`" not in long_add, long_add   # the mid-token cut it replaced

# Grouping only collapses a RUN of the same tag; different tags stay separate.
got = describe('@@ -0,0 +1,3 @@\n+  <option value="A">Alpha</option>\n'
               '+  <li value="B">Beta</li>\n')
assert len(got) == 2, got

# --------------------------------------------------------------- clipping
# A replaced JSON description put 900 characters on one summary line: the
# added/removed branches were clipped and the "became" branch was not.
# Shaped like the real one: the new value KEEPS the old text and appends to it,
# which is what an expanded description looks like.
base = "Go + Gin API for managing events, users, and tickets, backed by Postgres."
got = describe(f'@@ -1,1 +1,1 @@\n-    "description": "{base}"\n'
               f'+    "description": "{base}\\n\\n### Authentication\\n\\n' + "x" * 800 + '"\n')[0]
assert len(got) < 120, len(got)
assert "much longer value (" in got, got          # says the size instead

# A merely long-ish replacement is still quoted, just cut on a boundary.
got = describe('@@ -1,1 +1,1 @@\n-    { "name": "System" },\n'
               '+    { "name": "System", "description": "Liveness and database connectivity" },\n')[0]
assert got.endswith("…`"), got
assert len(got) < 110, len(got)

# Short changes are untouched by any of this.
assert describe('@@ -1,1 +1,1 @@\n-  "version": "1.0.0"\n+  "version": "1.1.0"\n') \
    == ["line 1: `0` became `1`"]

# ------------------------------------------------- matching within a run
# `split` pairs a run of changes by POSITION, which is right for rendering two
# columns and wrong for describing them. Two `servers` entries that swap order
# were paired against each other and reported as two rewrites.
SWAP = """@@ -9,3 +9,3 @@
   "servers": [
-    { "url": "http://localhost:8080", "description": "Local" },
-    { "url": "https://eventapi.arpthef.my.id", "description": "production" }
+    { "url": "https://eventapi.arpthef.my.id", "description": "Production" },
+    { "url": "http://localhost:8080", "description": "Local development" }
   ],
"""
got = describe(SWAP)
# Cited at where each line now IS, and listed in new-file order: similarity
# matching can pair them back to front, so the run is sorted before emitting.
assert got == ["line 10: `production` became `Production`",
               'line 11: `Local" }` became `Local development" }`'], got

# Reordering a list moves the trailing comma, so the last entry gains or loses
# one. Counting that as a second edited span turned every reorder into
# "rewritten".
assert one_change('  { "a": 1 },', '  { "a": 2 }') == ("1", "2")
# A comma change on its OWN line is still a real edit and is not swallowed.
assert one_change("x = [1, 2]", "x = [1; 2]") is not None

# Lines too dissimilar to correspond are still reported separately, and the
# leftovers on either side are named as added or removed.
got = describe("@@ -1,2 +1,3 @@\n-import os\n+const x = totallyUnrelated(1)\n+another = 2\n")
assert any("removed `import os`" in g for g in got), got
assert sum("added" in g for g in got) == 2, got

# Line numbers cite the NEW file, which is the one the reader has open. Using
# the old number for an edit and the new one for an addition made two different
# changes in the same hunk both report "line 6".
got = describe("@@ -5,2 +5,3 @@\n func f() {\n"
               "+\tv := h.Cache.Version()\n"
               "-\th.Cache.Set(k, b)\n"
               "+\th.Cache.Set(k, b, v)\n")
assert len({g.split(":")[0] for g in got}) == len(got), got   # distinct lines
assert any("line 6" in g for g in got) and any("line 7" in g for g in got), got

print("ok")
