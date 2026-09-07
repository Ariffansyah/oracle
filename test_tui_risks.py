"""Every risk kind core can emit must be renderable by the TUI.

`co-dependent` and `provably-safe` were added to core with badges and prose,
and NOT to the TUI's colour and dot tables. Reviewing any commit containing one
raised KeyError and took the whole app down -- on the exact Go commit the
feature was written for. The verdict logic was tested; the fact that something
has to draw it was not.

This reads the kinds out of core's source rather than listing them, so the next
one added fails here instead of at the user's terminal.
"""
import pathlib, re
from oracle_reviewer.core import FileReview
from oracle_reviewer.tui import RISK, DOT

src = pathlib.Path("oracle_reviewer/core.py").read_text()

# `r.risk = "x"`, `r.risk, r.why_unclear = "x", ...`, `r.risk, r.static = "x", ...`
kinds = set(re.findall(r'r\.risk(?:,\s*[\w.]+)?\s*=\s*"([a-z-]+)"', src))
# and the mapping in `badge` that names the rest
kinds |= set(re.findall(r'^\s*"(high|change|fixes|none|unverified)":', src, re.M))
assert len(kinds) >= 8, sorted(kinds)

missing_colour = sorted(k for k in kinds if k not in RISK)
missing_dot = sorted(k for k in kinds if k not in DOT)
assert not missing_colour, f"no colour for {missing_colour}"
assert not missing_dot, f"no dot for {missing_dot}"

# Each must also produce a badge rather than raising out of the dict lookup.
for k in sorted(kinds):
    b = FileReview(path="x", risk=k).badge
    assert isinstance(b, str) and b, (k, b)

# The two that are NOT risk verdicts must not be coloured as danger. #f38ba8 is
# the red used for `high`; a file whose commit is fine must never wear it.
for k in ("co-dependent", "provably-safe", "unreachable", "none"):
    assert RISK[k] != RISK["high"], k

print("ok")


# --------------------------------------------------- the panel names its commit
# "FILES IN THIS COMMIT" listed the last REVIEWED commit's files, because it was
# only ever filled when a review finished and moving the highlight left it
# untouched. On a real repo a six-file commit showed the two files of a docs
# commit selected several moves earlier, with nothing marking them stale.
import asyncio, subprocess, tempfile
from oracle_reviewer.tui import Reviewer


def _repo():
    d = pathlib.Path(tempfile.mkdtemp())
    g = lambda *a: subprocess.run(["git", "-C", str(d), *a],
                                  capture_output=True, text=True, check=True)
    g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (d / "a.txt").write_text("1\n"); g("add", "-A"); g("commit", "-qm", "first")
    (d / "a.txt").write_text("2\n")
    (d / "b.txt").write_text("x\n")
    (d / "c.txt").write_text("y\n")
    g("add", "-A"); g("commit", "-qm", "three files")
    (d / "a.txt").write_text("3\n"); g("add", "-A"); g("commit", "-qm", "one file")
    return str(d)


async def _panel():
    app = Reviewer(repo=_repo(), run="true", host="http://localhost:1",
                   model="none", gate=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        files = app.query_one("#files")
        assert app.pending == ["a.txt"], app.pending
        assert len(files.children) == 1, len(files.children)

        await pilot.press("down")                    # the three-file commit
        await pilot.pause()
        assert app.pending == ["a.txt", "b.txt", "c.txt"], app.pending
        assert len(files.children) == 3, len(files.children)

        await pilot.press("up")                      # and back
        await pilot.pause()
        assert app.pending == ["a.txt"], app.pending
        assert len(files.children) == 1, len(files.children)


asyncio.run(_panel())
print("ok")
