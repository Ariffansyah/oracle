"""The unified-diff -> two-column aligner.

    python test_splitdiff.py

The alignment rule is the whole point: the Nth removed line must land opposite
the Nth added line, so a changed line sits across from the line it replaced.
"""

from oracle_reviewer.splitdiff import split

D = """diff --git a/calc.py b/calc.py
index 111..222 100644
--- a/calc.py
+++ b/calc.py
@@ -1,5 +1,5 @@
 def sum_to(n):
     total = 0
-    for i in range(1, n):
+    for i in range(1, n + 1):
         total += i
     return total
"""

rows = split(D)
# hunk header, then five paired rows
assert len(rows) == 6, len(rows)
assert rows[0][0][2] == "hunk"

# the changed line is ONE row, both sides present and opposite each other
changed = [r for r in rows if r[0] and r[0][2] == "del"]
assert len(changed) == 1
left, right = changed[0]
assert left[1].strip() == "for i in range(1, n):"
assert right[1].strip() == "for i in range(1, n + 1):"
assert right[2] == "add"
assert (left[0], right[0]) == (3, 3)          # line numbers, both sides

# `--- a/calc.py` and `+++ b/calc.py` must not become a deleted and an added
# line of source. They start with - and + , so order of the tests matters.
assert not any(r[0] and "a/calc.py" in r[0][1] for r in rows)
assert not any(r[1] and "b/calc.py" in r[1][1] for r in rows)

# Uneven runs pad the shorter side rather than misaligning the rest.
U = """@@ -1,3 +1,4 @@
 keep
-one
-two
+ONE
+TWO
+THREE
 tail
"""
rows = split(U)
pairs = [(l, r) for l, r in rows if (l and l[2] == "del") or (r and r[2] == "add")]
assert len(pairs) == 3
assert pairs[2][0] is None and pairs[2][1][1] == "THREE"   # padded left
assert rows[-1][0][1] == "tail" and rows[-1][1][1] == "tail"

# A pure addition (new file) has no left side at all.
A = """@@ -0,0 +1,2 @@
+alpha
+beta
"""
rows = split(A)
assert all(l is None for l, _ in rows[1:])
assert [r[1] for _, r in rows[1:]] == ["alpha", "beta"]

# Anything before the first @@ is preamble, whatever it looks like -- a commit
# message from `git show` must not render as source.
SHOW = """commit abc123
Author: someone <a@b>

    -1 was the old bound
    +1 is the new one

diff --git a/x.py b/x.py
@@ -1,1 +1,1 @@
-a
+b
"""
rows = split(SHOW)
assert len(rows) == 2 and rows[0][0][2] == "hunk"
assert rows[1][0][1] == "a" and rows[1][1][1] == "b"

assert split("") == []

print("ok")
