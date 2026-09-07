"""Definitions fetched by grep, and the prompt they do or do not change.

The model saw `h.EventCache.Version()` being called and had never seen what it
IS -- so it could only report that `Set` gained a parameter, never what the
parameter is for, which `Version`'s doc comment states outright.
"""
import os, pathlib, subprocess, tempfile
from oracle_reviewer import core
from oracle_reviewer.related import called_symbols, find_definition, related_context

D = lambda body: f"--- a/h.go\n+++ b/h.go\n@@ -1,6 +1,6 @@\n{body}"

# ------------------------------------------------------------------- symbols
got = called_symbols(D("+\tv := h.Cache.Version()\n+\th.Cache.Set(k, b, v)\n"))
assert "Version" in got and "Set" in got, got
# `Set` is the point: an earlier version skipped it as a "generic" name, which
# dropped the single most relevant symbol in the commit this was written for.

# Only ADDED lines are read -- a removed call is not what the new code does.
assert called_symbols(D("-\tv := h.Cache.Version()\n")) == []

# Something the diff itself defines needs no fetching.
assert "Helper" not in called_symbols(
    D("+func Helper() {}\n+\tHelper()\n"))

# Keywords and shouty constants are not symbols to look up.
none = called_symbols(D("+\tif len(xs) > 0 { return MAX_SIZE }\n"))
assert "if" not in none and "len" not in none and "MAX_SIZE" not in none, none

# ---------------------------------------------------------------- retrieval
d = pathlib.Path(tempfile.mkdtemp())
g = lambda *a: subprocess.run(["git", "-C", str(d), *a], capture_output=True,
                              text=True, check=True)
g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
(d / "cache.go").write_text(
    "package cache\n\n"
    "// Version returns the invalidation generation. Read it before loading.\n"
    "func (c *Cache) Version() uint64 {\n\treturn c.version\n}\n")
(d / "h.go").write_text("package h\n")
g("add", "-A"); g("commit", "-qm", "base")

hit = find_definition(str(d), "Version", exclude="h.go")
assert hit, "no definition found"
where, snip = hit
assert where == "cache.go", where
# The doc comment above the signature is the sentence that says WHY, which is
# precisely what a caller's diff cannot show. It must come along.
assert "invalidation generation" in snip, snip
assert "func (c *Cache) Version()" in snip, snip

# The file under review is excluded -- it is already in the prompt.
assert find_definition(str(d), "Version", exclude="cache.go") is None

# A name this repo does not declare yields nothing, which is how stdlib names
# fall out without a hand-written skip list.
assert find_definition(str(d), "Printf", exclude="") is None

ctx = related_context(str(d), "h.go", D("+\tv := c.Version()\n"))
assert len(ctx) == 1 and "invalidation generation" in ctx[0][1], ctx

# The budget is the adapter's, not the base model's: a tiny budget yields none
# rather than blowing the context.
assert related_context(str(d), "h.go", D("+\tv := c.Version()\n"), budget=5) == []

# ------------------------------------------------------------------- prompt
# OFF by default. Adding a section to a prompt v3 never trained on is the move
# that cost v4 34 rows, so the default must reproduce today's prompt exactly.
assert core.RELATED is False, "ORACLE_RELATED must default to off"
r = core.FileReview(path="h.go", risk="change", diff="x", before="b", after="a")
assert r.related == []

print("ok")
