"""The settings bar, driven by keys rather than by eye.

    python test_tui_settings.py

Every switch the panel offers has to be one the tool can honour. The case that
matters most is Stage 1: `core.preload_gate` can only run before the UI takes
the terminal, so a session started without it must show the gate as
unavailable rather than as a switch that silently does nothing.
"""
import asyncio

from textual.widgets import Label, ListItem, ListView, Static

from oracle_reviewer import core
from oracle_reviewer.tui import Reviewer

REPO = "."


async def main() -> None:
    # --- a session WITH the gate loaded -------------------------------------
    app = Reviewer(repo=REPO, run="true", gate=True)
    async with app.run_test() as pilot:
        panel = app.query_one("#settings", Static)
        assert not panel.has_class("active"), "settings must start closed"

        # a number key does nothing while the panel is shut
        before = app.gate_on
        await pilot.press("1")
        assert app.gate_on == before, "1 acted with the panel closed"

        await pilot.press("s")
        assert panel.has_class("active"), "s did not open the panel"
        text = app._settings_text()
        assert "Stage 1 (JIT) gate" in text and "on" in text, text

        await pilot.press("1")
        assert app.gate_on is False, "1 did not turn the gate off"
        assert "off" in app._settings_text()
        await pilot.press("1")
        assert app.gate_on is True, "1 did not turn the gate back on"

        await pilot.press("2")
        assert app.auto_review is True
        await pilot.press("2")
        assert app.auto_review is False, "auto-review did not toggle back"

        # timeout cycles, and wraps
        seen = [app.timeout]
        for _ in range(4):
            await pilot.press("3")
            seen.append(app.timeout)
        assert seen[1:] == [600, 60, 120, 300], seen
        assert len(set(seen[1:])) == 4, seen

        await pilot.press("escape")
        assert not panel.has_class("active"), "escape did not close the panel"
        await pilot.press("s")
        await pilot.press("s")
        assert not panel.has_class("active"), "s did not toggle shut"

    # --- a session started WITHOUT the gate ---------------------------------
    # It cannot be turned on later, so the panel must say so and the key must
    # refuse rather than flip a flag the review path would then act on.
    app = Reviewer(repo=REPO, run="true", gate=False)
    async with app.run_test() as pilot:
        await pilot.press("s")
        assert "unavailable" in app._settings_text(), app._settings_text()
        await pilot.press("1")
        assert app.gate_on is False, "the gate was switched on without a preload"

    # --- a stale highlight must not index a shorter review list -------------
    # `ListView.clear()` is deferred, so a Highlighted carrying the PREVIOUS
    # review's index arrives after `self.reviews` has been replaced. Reviewing a
    # three-file commit and then a one-file commit used to raise IndexError out
    # of _pick_file and take the whole app down.
    app = Reviewer(repo=REPO, run="true", gate=False)
    async with app.run_test() as pilot:
        files = app.query_one("#files", ListView)
        for name in ("a.py", "b.py", "c.py"):
            files.append(ListItem(Label(name)))
        await pilot.pause()
        app.reviews = [core.FileReview(path="a.py", risk="none")]   # the shrink
        files.focus()
        await pilot.pause()
        for _ in range(3):
            await pilot.press("down")
            await pilot.pause()
        assert app.is_running, "a stale highlight crashed the app"

    print("ok")


asyncio.run(main())
