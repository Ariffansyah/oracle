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

print("ok")
