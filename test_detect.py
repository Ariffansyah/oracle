"""Proposing a command that can actually establish a baseline.

    python test_detect.py

`suggest_run` answers what a project calls its own test command. That is not the
same as a command that can RUN, and the difference was measured on a real
Next.js repository: the detected `pnpm run lint` died in pnpm's
`runDepsStatusCheck` before eslint was ever reached, identically on both sides
of the change, so the reviewer measured the package manager's complaint and
correctly refused to say anything about the code.

Every assertion here is one of the three failures found on that repository:
the package manager getting in the way, a project-wide command that is red for
reasons unrelated to the commit, and a build that cannot survive a worktree.
"""

import json
import tempfile
from pathlib import Path

from oracle_reviewer.detect import describe, find_repos, with_files

ROOT = Path(tempfile.mkdtemp())


def repo(name, files, bins=()):
    d = ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    for path, body in files.items():
        (d / path).parent.mkdir(parents=True, exist_ok=True)
        (d / path).write_text(body)
    for b in bins:
        p = d / "node_modules" / ".bin" / b
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!/bin/sh\n")
        p.chmod(0o755)
    return str(d)


def pkg(scripts, deps=None):
    return json.dumps({"scripts": scripts, "dependencies": deps or {}})


# --- the pnpm failure: a script is rewritten to the binary it invokes --------
# This is the whole fix. `pnpm run lint` cannot start in a worktree; the eslint
# it would have run starts fine.
a = describe(repo("a", {"package.json": pkg({"lint": "eslint ."}),
                        "pnpm-lock.yaml": ""}, bins=["eslint"]))
assert a.candidates[0].cmd == "./node_modules/.bin/eslint .", a.candidates[0].cmd
assert "bypassing pnpm" in a.candidates[0].why, a.candidates[0].why
assert a.manager == "pnpm", a.manager

# Arguments survive the rewrite -- `next build` keeps its subcommand.
b = describe(repo("b", {"package.json": pkg({"build": "next build"}),
                        "pnpm-lock.yaml": ""}, bins=["next"]))
assert b.candidates[0].cmd == "./node_modules/.bin/next build", b.candidates[0].cmd

# With no local binary there is nothing to rewrite to, and the script is left
# exactly as the project wrote it rather than guessed at.
c = describe(repo("c", {"package.json": pkg({"test": "vitest"})}))
assert c.candidates[0].cmd == "vitest", c.candidates[0].cmd

# --- a build is proposed LAST, whatever order package.json lists it in -------
# It is the slowest command a project owns and the one most likely to be
# impossible inside a worktree: Turbopack rejects a node_modules symlink that
# points out of the project root, and nothing here can fix that.
d = describe(repo("d", {"package.json": pkg({"build": "next build",
                                             "test": "vitest run"}),
                        "package-lock.json": ""}, bins=["next", "vitest"]))
assert "vitest" in d.candidates[0].cmd, [x.cmd for x in d.candidates]
assert "next build" in d.candidates[-1].cmd, [x.cmd for x in d.candidates]
assert d.candidates[-1].heavy and not d.candidates[0].heavy

# --- scoping: what rescues a baseline in a repo carrying lint debt -----------
# Project-wide eslint exits 1 on pre-existing errors that have nothing to do
# with the commit; the same tool over the touched file exits 0.
assert with_files("./node_modules/.bin/eslint", ["a.tsx"]) \
    == "./node_modules/.bin/eslint a.tsx"
assert with_files("./.venv/bin/pytest -q", ["t_x.py"]) == "./.venv/bin/pytest -q t_x.py"
# A tool whose argument handling is not understood is never given paths:
# appending one turns a working baseline into a usage error.
assert with_files("next build", ["a.tsx"]) == "next build"
assert with_files("go test ./...", ["m.go"]) == "go test ./..."
assert with_files("", ["a"]) == "" and with_files("x", []) == "x"

# --- identification, for the picker to show ---------------------------------
e = describe(repo("e", {"package.json": pkg({"dev": "next dev"}, {"next": "15"}),
                        "tsconfig.json": "{}", "pnpm-lock.yaml": ""}))
assert e.language == "TypeScript" and e.framework == "Next.js", e.stack
assert e.stack == "TypeScript · Next.js · pnpm", e.stack

f = describe(repo("f", {"package.json": pkg({}, {"react": "18"})}))
assert f.language == "JavaScript" and f.framework == "React", f.stack

g = describe(repo("g", {"manage.py": "", "requirements.txt": "django\n"}))
assert g.language == "Python" and g.framework == "Django", g.stack
assert "manage.py test" in g.best, g.best

h = describe(repo("h", {"go.mod": "module x"}))
assert h.language == "Go" and h.best == "go test ./...", h.best

# A directory that is not a project says so rather than proposing something
# that could only fail.
i = describe(repo("i", {"README.md": "hi"}))
assert i.candidates == [] and i.best == "" and i.language == "unknown"
assert describe("/nonexistent-path-here").candidates == []

# Malformed package.json is a missing answer, never a crash.
j = describe(repo("j", {"package.json": "{not json"}))
assert j.best == "" or j.candidates == [], j.best

# --- find_repos ------------------------------------------------------------
# Only directories that are actually git repositories, and never a crash on a
# root that does not exist.
(ROOT / "scan" / "r1" / ".git").mkdir(parents=True)
(ROOT / "scan" / "plain").mkdir(parents=True)
found = find_repos([str(ROOT / "scan")])
names = [p.name for p in found]
assert "r1" in names and "plain" not in names, names
assert find_repos(["/nonexistent-root-here"]) == []

print("ok — detect: binaries resolved, builds last, scoping bounded, "
      f"{len(names)} repo(s) found")
