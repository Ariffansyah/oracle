"""What a command can ESTABLISH, and the verdict that follows from it.

The bug: eslint reads a .tsx file, so `unreachable` stays quiet, and the review
then reported "the changed code never ran, or it ran and made no difference to
what this command prints". Both halves are false for a linter -- it never
executes anything -- and the badge, "Command Output Unchanged", implied a check
had happened and come back level. Two readers took that as a clean bill.
"""
from oracle_reviewer.core import FileReview, command_class, review_body

# ------------------------------------------------------------ classification
assert command_class("pnpm run lint") == "style"
assert command_class("eslint .") == "style"
assert command_class("ruff check") == "style"
assert command_class("npx tsc --noEmit") == "types"
assert command_class("mypy src") == "types"
assert command_class("pytest -q") == "tests"
assert command_class("npm test") == "tests"
assert command_class("go test ./...") == "tests"
assert command_class("cargo test") == "tests"
assert command_class("mvn -q test") == "tests"
assert command_class("next build") == "build"
# Executes, but what it covers is unknowable -- do not promise it is a test.
assert command_class("python main.py") == "unknown"

# A test command must win over the word "lint" appearing elsewhere in it.
assert command_class("npm run test:lint-clean") == "tests"

# ------------------------------------------------------------------- badges
def badge(cmd):
    return FileReview(path="a.tsx", risk="unclear", why_unclear="not-exercised",
                      checks=command_class(cmd)).badge

assert badge("pnpm run lint") == "Style Checked — Behaviour Unchecked"
assert badge("npx tsc --noEmit") == "Types Checked — Behaviour Unchecked"
assert badge("next build") == "Builds — Behaviour Unchecked"
# A real test run keeps the older wording: there, identical output genuinely is
# the ambiguous "never reached, or reached and identical" case.
assert badge("pytest -q") == "Command Output Unchanged — Worth Checking"

# Unset `checks` must not change the existing badge -- older reviews and any
# caller that does not set it keep exactly what they had.
assert FileReview(path="a", risk="unclear",
                  why_unclear="not-exercised").badge \
    == "Command Output Unchanged — Worth Checking"
assert FileReview(path="a", risk="unclear",
                  why_unclear="baseline").badge == "Baseline Already Failing"

# --------------------------------------------------------------------- prose
D = "--- a/a.tsx\n+++ b/a.tsx\n@@ -1,3 +1,3 @@\n-  const n = 1\n+  const n = 2\n"
def body(cmd):
    return review_body(FileReview(path="a.tsx", risk="unclear", diff=D,
                                  why_unclear="not-exercised",
                                  checks=command_class(cmd)), cmd)

lint = body("pnpm run lint")
assert "never executes the code" in lint
assert "nothing at all about behaviour" in lint
# The linter verdict must NOT claim the code ran, in either direction.
assert "never ran" not in lint
assert "ran and made no difference" not in lint

tests = body("pytest -q")
assert "does execute the code" in tests
assert "never reached by these tests" in tests

# No verdict in this state may read as safe.
for c in ("pnpm run lint", "pytest -q", "npx tsc --noEmit", "next build"):
    assert "NOT a clean bill of health" in body(c), c

# ------------------------------------- a test command that ran no tests at all
# `go test ./...` answering `[no test files]` has already settled the ambiguity
# the wording above hedges about: the change was NOT reached, because nothing
# was there to reach it. Offering the reader two possibilities and calling the
# choice unknown is less true than what was measured, and it points at the
# wrong next step -- re-reading the diff instead of writing the missing test.
def unrun(out, cmd="go test ./..."):
    r = FileReview(path="internal/routes/routes.go", risk="unclear", diff=D,
                   why_unclear="not-exercised", checks=command_class(cmd))
    r.before = r.after = out
    return r, review_body(r, cmd)

r, go = unrun("?  example.com/api/internal/routes  [no test files]")
assert r.badge == "No Tests Ran — Nothing Measured", r.badge
assert "ran NO TESTS over this code" in go
assert "The gap is the test, not the diff" in go
# The hedge belongs to the ambiguous case and must not survive into this one.
assert "which of the two is NOT known" not in go
assert "NOT a clean bill of health" in go

# Every runner's own way of saying it, not just Go's.
for out in ("collected 0 items", "no tests ran", "Ran 0 tests", "0 passing"):
    r2, b2 = unrun(out, "pytest -q")
    assert r2.badge == "No Tests Ran — Nothing Measured", (out, r2.badge)
    assert "ran NO TESTS" in b2, out

# When tests DID run, the ambiguity is real and the hedge stays. This is the
# assertion that keeps the fix from swallowing the honest uncertain case.
r3, ran = unrun("ok  example.com/api  0.02s")
assert r3.badge == "Command Output Unchanged — Worth Checking", r3.badge
assert "which of the two is NOT known" in ran
assert "ran NO TESTS" not in ran

print("ok")
