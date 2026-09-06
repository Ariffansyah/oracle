"""Working out how to run a project, so the tool is not Python-only.

    python test_suggest_run.py

Nothing about the review is language-specific — it runs a command and compares
output. What IS language-specific is knowing which command that is, and
defaulting to `python main.py` made the tool look broken on every project that
is not Python: the baseline could only ever fail.
"""

import json
import tempfile
from pathlib import Path

from oracle_reviewer.core import suggest_run

ROOT = Path(tempfile.mkdtemp())


def repo(name, files):
    d = ROOT / name
    for path, body in files.items():
        (d / path).parent.mkdir(parents=True, exist_ok=True)
        (d / path).write_text(body)
    d.mkdir(exist_ok=True)
    return str(d)


pkg = lambda scripts: json.dumps({"scripts": scripts})

# A JS/TS project names its own commands, so they are read, not guessed.
assert suggest_run(repo("a", {"package.json": pkg({"dev": "next dev",
                                                   "build": "next build",
                                                   "test": "jest"})}))[0] == "npm test"
# `dev` and `start` are servers: they never exit, so they can measure nothing.
assert suggest_run(repo("b", {"package.json": pkg({"dev": "next dev",
                                                   "start": "next start"})}))[0] == ""
assert suggest_run(repo("c", {"package.json": pkg({"dev": "x",
                                                   "build": "next build"})}))[0] == "npm run build"

# The lockfile names the runner. All three take `<runner> test`; anything else
# needs an explicit `run`.
assert suggest_run(repo("d", {"package.json": pkg({"test": "vitest"}),
                              "pnpm-lock.yaml": ""}))[0] == "pnpm test"
assert suggest_run(repo("e", {"package.json": pkg({"test": "jest"}),
                              "yarn.lock": ""}))[0] == "yarn test"
assert suggest_run(repo("f", {"package.json": pkg({"lint": "eslint ."}),
                              "yarn.lock": ""}))[0] == "yarn run lint"

# TypeScript with no test script still has something that fails on bad code.
assert suggest_run(repo("g", {"package.json": pkg({"dev": "next dev"}),
                              "tsconfig.json": "{}"}))[0] == "npx tsc --noEmit"

# Other ecosystems.
assert suggest_run(repo("h", {"go.mod": "module x"}))[0] == "go test ./..."
assert suggest_run(repo("i", {"Cargo.toml": "[package]"}))[0] == "cargo test"
assert suggest_run(repo("j", {"pom.xml": "<project/>"}))[0] == "mvn -q test"
assert suggest_run(repo("k", {"Gemfile": "source 'x'"}))[0] == "bundle exec rspec"
assert suggest_run(repo("l", {"Makefile": "build:\n\techo\ntest:\n\techo\n"}))[0] == "make test"
# A Makefile with no test-ish target says nothing useful.
assert suggest_run(repo("m", {"Makefile": "all:\n\techo\n"}))[0] == ""

# Python, tests before entry points.
assert suggest_run(repo("n", {"pyproject.toml": "", "tests/test_x.py": ""}))[0] == "pytest -q"
assert suggest_run(repo("o", {"pyproject.toml": "", "main.py": ""}))[0] == "python main.py"
assert suggest_run(repo("p", {"main.py": ""}))[0] == "python main.py"
assert suggest_run(repo("q", {"index.js": ""}))[0] == "node index.js"

# Nothing recognisable must return empty rather than something that cannot work.
# That is the whole point: a wrong guess produces a dead baseline and a review
# that establishes nothing.
assert suggest_run(repo("r", {"README.md": "hi"})) == ("", "")
assert suggest_run("/nonexistent-path-here") == ("", "")

# Malformed package.json must not take the app down.
assert suggest_run(repo("s", {"package.json": "{not json"}))[0] == ""

print("ok")
