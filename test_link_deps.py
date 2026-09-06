"""Installed dependencies in a fresh worktree.

    python test_link_deps.py

A worktree is a clean checkout, and installed dependencies are gitignored, so it
has none of them. For an interpreted language that is fatal before the code is
reached: pnpm exits on `runDepsStatusCheck` because node_modules does not match
the lockfile, and the review measures the package manager rather than the project.
"""

import subprocess
import tempfile
from pathlib import Path

from oracle_reviewer.core import link_deps, observe, worktree

R = Path(tempfile.mkdtemp()) / "repo"
(R / "node_modules" / "dep").mkdir(parents=True)
(R / "node_modules" / "dep" / "index.js").write_text("module.exports = 1;\n")
(R / ".venv" / "bin").mkdir(parents=True)
(R / ".gitignore").write_text("node_modules/\n.venv/\n")
(R / "run.js").write_text("console.log(require('./node_modules/dep'));\n")
g = lambda *a: subprocess.run(["git", "-C", str(R), *a], capture_output=True)
subprocess.run(["git", "init", "-q", str(R)], capture_output=True)
g("config", "user.email", "t@t"); g("config", "user.name", "t")
g("add", "-A"); g("commit", "-qm", "init")

# A bare worktree has no dependencies at all -- this is the failure being fixed.
plain = Path(tempfile.mkdtemp()) / "w"
g("worktree", "add", "--detach", "-f", str(plain), "HEAD")
assert not (plain / "node_modules").exists()

# Linking makes them reachable, and reports what it linked.
linked = link_deps(str(R), plain)
assert "node_modules" in linked and ".venv" in linked, linked
assert (plain / "node_modules" / "dep" / "index.js").exists()
assert (plain / "node_modules").is_symlink()

# Already-present directories are never clobbered.
again = link_deps(str(R), plain)
assert again == [], again

# Absent ones are simply skipped -- no error, no empty directory left behind.
assert "vendor" not in linked
assert not (plain / "vendor").exists()
g("worktree", "remove", "--force", str(plain))

# End to end: the command actually resolves the dependency inside a worktree.
with worktree(str(R), "HEAD") as w:
    assert (w / "node_modules").exists()
    got = observe(w, "node run.js")
    assert got["rc"] == 0, got
    assert got["out"].strip() == "1", got

# The real dependency tree must survive the worktree being torn down: the
# symlink is deleted, not what it points at.
assert (R / "node_modules" / "dep" / "index.js").exists()

print("ok")
