"""Choosing a repository and its run command before anything is executed.

    python test_picker.py

The run command decides what the reviewer can observe, and it used to be chosen
invisibly: a project whose detected command could not start looked like a broken
model rather than a wrong setting. The picker exists to make that choice visible
at the one moment it is still cheap to change.

Driven through Textual's own pilot, because the failure this pins is a UI one:
a focused ListView consumes Enter to select a row, so an app-level `enter`
binding never fires and the picker returned None however the user pressed it.
"""

import asyncio
import json
import pathlib
import subprocess
import tempfile

from oracle_reviewer.picker import Picker

R = pathlib.Path(tempfile.mkdtemp())


def project(name, scripts, deps, bins, lock="pnpm-lock.yaml"):
    d = R / name
    (d / "node_modules" / ".bin").mkdir(parents=True)
    (d / "package.json").write_text(json.dumps({"scripts": scripts,
                                                "dependencies": deps}))
    (d / lock).write_text("")
    (d / "tsconfig.json").write_text("{}")
    for b in bins:
        p = d / "node_modules" / ".bin" / b
        p.write_text("#!/bin/sh\n")
        p.chmod(0o755)
    subprocess.run(["git", "init", "-q", str(d)], capture_output=True)
    return d


project("demo", {"lint": "eslint .", "build": "next build"},
        {"next": "15"}, ["eslint", "next"])


async def main() -> None:
    app = Picker(roots=[str(R)])
    async with app.run_test() as pilot:
        await pilot.pause()

        # The repository was found, described, and a command pre-selected --
        # the pnpm script resolved to its binary, which is the one that runs.
        assert [d.name for d in app.repos] == ["demo"], app.repos
        assert app.project.stack == "TypeScript · Next.js · pnpm", app.project.stack
        assert app.chosen_cmd == "./node_modules/.bin/eslint .", app.chosen_cmd
        assert app.query_one("#cmd").value == app.chosen_cmd

        # The build is offered, but never as the default: it is the slowest
        # command and the one least likely to survive a worktree.
        assert app.project.candidates[-1].heavy
        assert not app.project.candidates[0].heavy

        # `e` opens the command line, escape closes it. It stays disabled
        # otherwise, because an enabled Input takes every keystroke and makes
        # the letter keys unreachable.
        assert app.query_one("#cmd").disabled
        await pilot.press("e")
        assert not app.query_one("#cmd").disabled, "e did not open the input"
        await pilot.press("escape")
        assert app.query_one("#cmd").disabled, "escape did not close the input"

        # Enter starts. This is the assertion that matters: the key arrives as
        # a ListView selection, never as the app-level binding.
        await pilot.press("enter")
        await pilot.pause()

    got = app.return_value
    assert got is not None, "enter did not start the review"
    repo, cmd = got
    assert pathlib.Path(repo).name == "demo", repo
    assert cmd == "./node_modules/.bin/eslint .", cmd
    print(f"ok — picker: {app.project.stack} -> {cmd}")


async def quits() -> None:
    """q leaves without choosing, and says so with None rather than a default."""
    app = Picker(roots=[str(R)])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("q")
    assert app.return_value is None, app.return_value


async def empty() -> None:
    """A root with no repositories is a message, not a crash."""
    app = Picker(roots=[str(R / "nothing-here")])
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.repos == [], app.repos
        await pilot.press("enter")     # must not start anything
    assert app.return_value is None, app.return_value


asyncio.run(main())
asyncio.run(quits())
asyncio.run(empty())
print("ok — picker: quit returns None, an empty scan cannot start a review")
