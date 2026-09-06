"""cosmetic_only and risky_edits: what they must NOT claim, mostly.

Both run where the command output was byte-identical, which is the state a
false claim does the most damage in -- there is no measurement to contradict
it. So the negatives matter more than the positives here.
"""
from oracle_reviewer.static_claims import cosmetic_only, risky_edits

D = lambda path, body: f"--- a/{path}\n+++ b/{path}\n@@ -1,4 +1,4 @@\n{body}"

# ------------------------------------------------------------ cosmetic_only
# The bug this function shipped with: `>BankJatim<` and `>Bank Jatim<` compare
# equal if whitespace is REMOVED rather than collapsed, so it announced
# "behaviour is unchanged" about a commit that changed a label a user reads.
label = D("a.tsx", '-  <option value="B">BankJatim</option>\n'
                   '+  <option value="B">Bank Jatim</option>\n')
assert cosmetic_only(label) is None, cosmetic_only(label)

# A genuine reindent still passes.
reindent = D("a.ts", "-    foo(x)\n+        foo(x)\n")
assert cosmetic_only(reindent) is not None

# Comments only, in a language whose comment marker we know.
comments = D("a.ts", "-// old note\n+// new note\n")
assert cosmetic_only(comments) is not None
py_comments = D("a.py", "-# old note\n+# new note\n")
assert cosmetic_only(py_comments) is not None

# `#` is NOT a comment in CSS -- claiming so would call an id selector cosmetic.
css = D("a.css", "-#main { color: red }\n+#main { color: blue }\n")
assert cosmetic_only(css) is None, cosmetic_only(css)

# Unknown language: claim nothing rather than guess the comment syntax.
unknown = D("a.zzz", "-// old\n+// new\n")
assert cosmetic_only(unknown) is None

# A real edit alongside a comment edit is not cosmetic.
mixed = D("a.ts", "-// note\n-const n = 1\n+// note two\n+const n = 2\n")
assert cosmetic_only(mixed) is None

assert cosmetic_only("") is None

# -------------------------------------------------------------- risky_edits
def only(diff):
    got = risky_edits(diff)
    assert len(got) == 1, got
    return got[0]

assert "await" in only(D("a.ts", "-  await save(x)\n+  save(x)\n"))
assert "try" in only(D("a.py", "-    try:\n+    pass\n"))
assert "optional chaining" in only(D("a.ts", "-  return u?.name\n+  return u.name\n"))
assert "guard" in only(D("a.py", "-    if x is None:\n+    pass\n"))

# Boundary flips need BOTH sides -- the pairing is the hazard.
assert "endpoint" in only(D("a.py", "-    for i in range(n):\n"
                                    "+    for i in range(n + 1):\n")
                          .replace("range(n):", "i < n:")
                          .replace("range(n + 1):", "i <= n:"))
assert "coercion" in only(D("a.ts", "-  if (a === b) {\n+  if (a == b) {\n"))

# A guard that was MOVED is not a guard that was deleted.
moved = D("a.py", "-    if x is None:\n-        return\n"
                  "+    log(x)\n+    if x is None:\n+        return\n")
assert risky_edits(moved) == [], risky_edits(moved)

# `===` inside a wholesale branch removal is not an equality loosening: there
# is no `==` counterpart. This is the shape every hit in a real repo had.
removed_branch = D("a.tsx", '-  if (provider === "GOPAY") {\n'
                            '-    return payout()\n'
                            '-  }\n')
assert not any("coercion" in h for h in risky_edits(removed_branch))

# Adding a guard is not removing one.
added = D("a.py", "+    if x is None:\n+        return\n")
assert risky_edits(added) == []

assert risky_edits("") == []
assert risky_edits(D("a.py", "-x = 1\n+x = 2\n")) == []

print("ok")
