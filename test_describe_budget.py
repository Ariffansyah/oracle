"""describe() has six slots. They must go to lines that can change behaviour.

On a real Go commit, five of the first twelve facts were comment lines and the
next six were the body of one added function -- so `Set` gaining a parameter
and the new early-return, which is what the commit was FOR, sat below the cut.
"""
from oracle_reviewer.static_claims import describe

def D(path, body):
    return f"--- a/{path}\n+++ b/{path}\n@@ -1,20 +1,20 @@\n{body}"

# ------------------------------------------------------- comments do not compete
c = describe(D("a.go", "+\tversion uint64\n"
                       "+\t// Version returns the invalidation generation.\n"
                       "+\t// Read it before loading the data.\n"))
assert any("version uint64" in f for f in c), c
assert not any("//" in f for f in c), c
# Dropped, not hidden: the reader is told, in one line rather than three.
assert any("comment line" in f and "cannot affect behaviour" in f for f in c), c

# A pragma is a comment to the parser and an instruction to the toolchain.
for prag in ("//go:build linux", "// +build linux", "# type: ignore",
             "# noqa: E501", "// eslint-disable-next-line", "// @ts-ignore",
             "// nolint:gosec"):
    ext = "a.py" if prag.startswith("#") else "a.go"
    got = describe(D(ext, f"+{prag}\n+\tx := 1\n"))
    assert any(prag.split(":")[0].strip("/# +") in f for f in got), (prag, got)

# A diff of nothing but comments says nothing here -- that is cosmetic_only's
# to describe, and it says more than a count would.
only = describe(D("a.go", "-// old\n+// new\n"))
assert not any("comment line" in f for f in only), only

# ------------------------------------------------- a function is one fact
fn = describe(D("a.go",
    "+func (c *Cache) Version() uint64 {\n"
    "+\tc.mu.RLock()\n"
    "+\tdefer c.mu.RUnlock()\n"
    "+\treturn c.version\n"
    "+}\n"
    "-func (c *Cache) Set(k string, d []byte) {\n"
    "+func (c *Cache) Set(k string, d []byte, version uint64) {\n"))
folded = [f for f in fn if "and its body" in f]
assert len(folded) == 1, fn
assert "func (c *Cache) Version() uint64" in folded[0], folded
assert "(5 lines)" in folded[0], folded
# The signature change must survive -- it is the point of the commit.
assert any("version uint64" in f and "became" in f for f in fn), fn
# The body lines must not also be listed individually.
assert not any("RLock" in f for f in fn), fn

# Two declarations in a row stay two facts.
two = describe(D("a.py", "+def one():\n+    return 1\n+    x = 2\n"
                         "+def two():\n+    return 2\n+    y = 3\n"))
assert len([f for f in two if "and its body" in f]) == 2, two

# A run too short to be worth folding is left alone.
short = describe(D("a.go", "+func f() {\n+}\n"))
assert not any("and its body" in f for f in short), short

# Not a declaration, so not folded however long.
plain = describe(D("a.go", "".join(f"+\tx{i} := {i}\n" for i in range(6))))
assert not any("and its body" in f for f in plain), plain

print("ok")
