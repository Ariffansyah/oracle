"""A file that fails alone, in a commit that passes, is not a risk.

Per-file isolation is what makes "which file broke it" an observation rather
than an opinion. In a COMPILED language it also manufactures failures: a commit
that changes a signature in one file and its callers in another cannot build
from either file alone.

Measured on a real Go commit (EventManagementAPI 11983b8), three of its four
code files came back HIGH RISK -- `Version undefined`, `not enough arguments in
call to Set`, `CheckInTicketByQR undefined` -- while `go build ./...` on the
commit itself exited 0. Every one was an artefact of the isolation, and each
pointed a reader at a file that was fine.

Reproduced here without a compiler: two files that agree only together.
"""
import pathlib, subprocess, tempfile
from oracle_reviewer import core

d = pathlib.Path(tempfile.mkdtemp())
run = lambda *a: subprocess.run(["git", "-C", str(d), *a], capture_output=True,
                                text=True, check=True)
run("init", "-q")
run("config", "user.email", "t@t")
run("config", "user.name", "t")

# The command passes only when both files hold the same value.
(d / "a.txt").write_text("1\n")
(d / "b.txt").write_text("1\n")
run("add", "-A"); run("commit", "-qm", "base")

(d / "a.txt").write_text("2\n")
(d / "b.txt").write_text("2\n")
run("add", "-A"); run("commit", "-qm", "bump both")

cmd = "test $(cat a.txt) = $(cat b.txt)"
rs = {r.path: r for r in core.review_commit(
    str(d), "HEAD", cmd, "http://localhost:1", "none",
    progress=lambda *_: None, timeout=30)}

# Alone, each file disagrees with the other and the command fails. Together
# they pass -- so neither failure is attributable to either file.
assert set(rs) == {"a.txt", "b.txt"}, set(rs)
assert rs["a.txt"].moves_with == ["b.txt"], rs["a.txt"].moves_with
assert rs["b.txt"].moves_with == ["a.txt"], rs["b.txt"].moves_with
for path, r in rs.items():
    assert r.risk == "co-dependent", (path, r.risk, r.after)
    assert r.badge == "Needs The Rest Of The Commit", r.badge
    body = core.review_body(r, cmd)
    assert "cannot be applied on its own" in body
    assert "a fact about the isolation, not about the change" in body
    # It must not read as a risk verdict in any direction.
    assert "High Risk" not in body
    # It must name the files it moves with, and be measured WITH them: telling
    # the reader only "this cannot run alone" throws away the whole-commit run
    # that was already paid for.
    assert r.moves_with, r.path
    assert "It moves with:" in body
    for sib in r.moves_with:
        assert sib in body, (r.path, sib)
    assert "measured WITH them" in body
    # Both measurements are shown, and labelled so they cannot be swapped:
    # the group's, which is real, and the isolated one, which is the artefact.
    assert "together," in body
    assert "when this file is applied ALONE:" in body
    assert r.isolated, r.path

# A file that breaks a commit which is ITSELF broken stays attributable: the
# artefact rule requires the whole commit to pass.
(d / "a.txt").write_text("9\n")
run("add", "-A"); run("commit", "-qm", "break it for real")
broke = {r.path: r for r in core.review_commit(
    str(d), "HEAD", cmd, "http://localhost:1", "none",
    progress=lambda *_: None, timeout=30)}
assert broke["a.txt"].risk == "high", broke["a.txt"].risk

print("ok")
