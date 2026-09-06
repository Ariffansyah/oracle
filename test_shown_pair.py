"""What the two measured values show.

    python test_shown_pair.py

`shown` takes the last line, which suits a test runner and truncates a program
that prints several values. main.py printing 10/9/2 then 15/9/2 was displayed
as "2" on both sides: the badge said Behavior Change while the two values said
nothing had changed.
"""

from oracle_reviewer.core import shown, shown_pair

run = lambda out, rc=0: {"out": out, "err": "", "rc": rc, "timeout": False}

# The reported case: the difference is on the FIRST line of three.
a, b = shown_pair(run("10\n9\n2\n"), run("15\n9\n2\n"))
assert a == "line 1: 10" and b == "line 1: 15", (a, b)

# A difference on a later line is found too.
a, b = shown_pair(run("10\n9\n2"), run("10\n9\n3"))
assert a == "line 3: 2" and b == "line 3: 3", (a, b)

# Single-line output needs no line label.
a, b = shown_pair(run("10"), run("15"))
assert (a, b) == ("10", "15")

# Identical runs keep the last line, which is the useful summary for a runner.
# Identical runs keep the last line, which is the useful summary for a runner --
# but say it IS the last line. Showing "2" for a program that prints 10, 9, 2
# invited "the output remains 2": true of the display, false of the program.
a, b = shown_pair(run("collected 3\n3 passed in 0.1s"), run("collected 3\n3 passed in 0.1s"))
assert a == b == "3 passed in 0.1s   (last of 2 lines)", a
assert shown_pair(run("only"), run("only"))[0] == "only"        # single line, bare

# One side ending early is said plainly rather than shown as blank.
a, b = shown_pair(run("1\n2\n3"), run("1\n2"))
assert a == "line 3: 3" and b == "line 3: (output ends here)", (a, b)

# A failing run keeps its exit code alongside the differing line.
a, b = shown_pair(run("ok\nfine"), run("ok\nboom", rc=1))
assert a == "line 2: fine" and b == "exit 1: line 2: boom", (a, b)

# Empty output on one side.
a, b = shown_pair(run(""), run("hello"))
assert b == "hello", (a, b)

# shown() itself is unchanged for the single-value callers.
assert shown(run("only")) == "only"
assert shown(run("x", rc=5)) == "exit 5: x"
assert shown({"timeout": True}) == "(timed out)"
assert shown(run("")) == "(no output)"

# ------------------------------------------------- the reason, not the summary
# `go test` puts the package summary on stdout and the COMPILER DIAGNOSTICS on
# stderr. `_body` was `out or err`, so stderr was discarded whenever stdout had
# anything, and a build failure was shown as "FAIL [build failed]" while the two
# lines naming the actual errors were dropped. The reason was measured and then
# withheld by accident, leaving the model to invent one.
from oracle_reviewer.core import _body, error_detail

GO_FAIL = {"out": "FAIL\texample.com/api [build failed]\nFAIL",
           "err": "# example.com/api\n"
                  "./handlers.go:6:31: h.EventCache.Version undefined "
                  "(type *EventCache has no field or method Version)\n"
                  "./handlers.go:7:30: too many arguments in call to h.EventCache.Set",
           "rc": 1, "timeout": False}
GO_OK = run("?   \texample.com/api\t[no test files]")

assert "Version undefined" in _body(GO_FAIL)          # stderr is not dropped
assert "build failed" in _body(GO_FAIL)               # nor is stdout
assert error_detail(GO_FAIL).startswith("./handlers.go:6:31:")
assert error_detail(GO_OK) is None                    # nothing failed

a, b = shown_pair(GO_OK, GO_FAIL)
assert "no test files" in a
assert "Version undefined" in b and b.startswith("exit 1: ")
assert "build failed" not in b                        # the summary is not the reason

# A test failure's assertion beats the runner's FAIL header.
PY_FAIL = {"out": "--- FAIL: TestSumTo (0.00s)\n    stats_test.go:7: SumTo(5) = 10, want 15\nFAIL",
           "err": "", "rc": 1, "timeout": False}
assert error_detail(PY_FAIL) == "stats_test.go:7: SumTo(5) = 10, want 15"

# A run with no diagnostic falls back to the ordinary first-difference rule.
a, b = shown_pair(run("10\n9\n2"), run("15\n9\n2"))
assert a == "line 1: 10" and b == "line 1: 15"

print("ok")
