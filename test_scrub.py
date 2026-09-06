"""Removing what differs between two runs of the SAME code.

    python test_scrub.py

Comparing raw output made all of these look like behaviour changes. The worktree
one is structural: every run gets a fresh mkdtemp, so any output naming a file
differs no matter what the code does.
"""

from oracle_reviewer.core import scrub

# The worktree path, which cannot ever match between two runs.
assert scrub("can't open '/tmp/oracle-wt-abc/t/main.py'", "/tmp/oracle-wt-abc") \
    == "can't open '<repo>/t/main.py'"
assert scrub("at /tmp/wt-1/x.js:3", "/tmp/wt-1") == scrub("at /tmp/wt-2/x.js:3", "/tmp/wt-2")

# Durations: "3 passed in 0.12s" is different every run.
assert scrub("3 passed in 0.12s") == scrub("3 passed in 1.07s")
assert scrub("took 450ms") == scrub("took 12ms")
assert scrub("done in 9 seconds") == scrub("done in 2 seconds")

# Timestamps and relative times, from the real lockfile check.
assert scrub("Lockfile passes (verified 9s ago)") == scrub("Lockfile passes (verified 41s ago)")
assert scrub("built 2026-09-03T19:11:02Z") == scrub("built 2026-09-04T01:02:03Z")
assert scrub("started 11:02:33") == scrub("started 23:59:01")

# Colour, which appears or not depending on TTY detection.
assert scrub("\x1b[32mok\x1b[0m") == "ok"

# A progress bar rewrites one line; only the frame it ended on survives.
assert scrub("10%\r50%\rdone") == "done"
assert scrub("10%\r50%\r\nnext") == "50%\nnext"
assert scrub("a\r\nb") == "a\nb"          # CRLF is a line ending, not a redraw

# What must NOT be touched: the program's own values are the whole measurement.
assert scrub("sum_to(5) = 15") == "sum_to(5) = 15"
assert scrub("10\n9\n2") == "10\n9\n2"
assert scrub("BankJatim") == "BankJatim"
assert scrub("total 100") == "total 100"
# A bare "m" is left alone -- too many real values end in it.
assert scrub("width 5m") == "width 5m"
assert scrub("") == ""

# The scrub must not make two genuinely different outputs look the same.
assert scrub("sum_to(5) = 10") != scrub("sum_to(5) = 15")
assert scrub("exit ok") != scrub("exit fail")

print("ok")
