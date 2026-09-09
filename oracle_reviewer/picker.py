"""Pick a repository and the command that defines it, before the review starts.

The reviewer runs a command before and after a change and compares what it
observed. That makes the command the single most consequential setting in the
tool, and until now it was chosen silently by a detector that could not be seen
or corrected -- so a project whose detected command could not even start looked
like a broken model rather than a wrong setting.

This screen makes that choice visible and editable at the one moment it can be
made cheaply: before anything has been run.

  j/k or arrows   move            tab    repos <-> commands
  e               edit the command        enter  start the review
  r               rescan                  q      quit

Nothing here runs the command. It is shown, and the review that follows is what
tries it -- which is why the ladder from `detect` is offered in full rather than
collapsed to one answer.
"""
from __future__ import annotations

import pathlib

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from . import detect

__all__ = ["Picker", "choose"]


class Picker(App):
    TITLE = "Oracle Reviewer — choose a repository"

    CSS = """
    #body { height: 1fr; }
    #left { width: 44; border-right: solid $panel-darken-2; }
    #repos { height: 1fr; }
    .head { background: $panel; color: $text-muted; padding: 0 1; }
    #stack { height: auto; padding: 1 2 0 2; text-style: bold; }
    #path { height: auto; padding: 0 2 1 2; color: $text-muted; }
    #cands { height: 1fr; border-top: solid $panel-darken-2; }
    #why { height: auto; padding: 0 2; color: $text-muted; }
    #cmdrow { height: auto; padding: 1 2; }
    /* Same rule as the reviewer's command line: an enabled Input takes every
       keystroke, so it stays disabled until `e` asks for it. */
    #cmd { display: none; }
    #cmd.active { display: block; }
    #status { height: auto; padding: 0 2; background: $panel; }
    """

    BINDINGS = [
        Binding("enter", "start", "start"),
        Binding("e", "edit", "edit command"),
        Binding("r", "rescan", "rescan"),
        Binding("tab", "switch", "switch pane", show=False),
        Binding("j,down", "move_next", "next", show=False),
        Binding("k,up", "move_prev", "prev", show=False),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self, roots: list[str] | None = None) -> None:
        super().__init__()
        self.roots = roots
        self.repos: list[pathlib.Path] = []
        self.project: detect.Project | None = None
        self.chosen_cmd = ""

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield Label("repositories", classes="head")
                yield ListView(id="repos")
            with Vertical():
                yield Static("", id="stack")
                yield Static("", id="path")
                yield Label("baseline command — best first", classes="head")
                yield ListView(id="cands")
                yield Static("", id="why")
                with Vertical(id="cmdrow"):
                    yield Input(placeholder="command to run", id="cmd", disabled=True)
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.action_rescan()
        self.query_one("#repos", ListView).focus()

    # ------------------------------------------------------------------ data
    def action_rescan(self) -> None:
        self._say("scanning for repositories …")
        self.repos = detect.find_repos(self.roots)
        lv = self.query_one("#repos", ListView)
        lv.clear()
        for d in self.repos:
            lv.append(ListItem(Label(d.name)))
        if self.repos:
            lv.index = 0
            self._load(0)
            self._say(f"{len(self.repos)} repositories — newest first")
        else:
            self._say("no git repositories found; pass --repo explicitly")

    def _load(self, i: int) -> None:
        """Describe repo `i` and fill the right-hand pane."""
        if not (0 <= i < len(self.repos)):
            return
        p = detect.describe(self.repos[i])
        self.project = p
        self.query_one("#stack", Static).update(p.stack or "unrecognised project")
        self.query_one("#path", Static).update(str(p.root))
        cl = self.query_one("#cands", ListView)
        cl.clear()
        for c in p.candidates:
            mark = " ⟨scopable⟩" if c.accepts_files else (" ⟨slow⟩" if c.heavy else "")
            cl.append(ListItem(Label(f"{c.cmd}{mark}")))
        if p.candidates:
            cl.index = 0
            self._pick(0)
        else:
            self.chosen_cmd = ""
            self.query_one("#why", Static).update(
                "nothing detected — press e to type a command")
            self.query_one("#cmd", Input).value = ""

    def _pick(self, i: int) -> None:
        p = self.project
        if not p or not (0 <= i < len(p.candidates)):
            return
        c = p.candidates[i]
        self.chosen_cmd = c.cmd
        self.query_one("#cmd", Input).value = c.cmd
        note = c.why
        if c.accepts_files:
            note += " · can be scoped to the files a commit touches"
        if c.heavy:
            note += " · slow, and may not survive a worktree"
        self.query_one("#why", Static).update(note)

    # --------------------------------------------------------------- events
    def on_list_view_highlighted(self, ev: ListView.Highlighted) -> None:
        if ev.list_view.id == "repos" and ev.list_view.index is not None:
            self._load(ev.list_view.index)
        elif ev.list_view.id == "cands" and ev.list_view.index is not None:
            self._pick(ev.list_view.index)

    def on_list_view_selected(self, ev: ListView.Selected) -> None:
        """Enter on a list starts the review.

        A focused ListView consumes Enter to select a row, so the app-level
        `enter` binding never fires while a list has focus -- which is always.
        The selection event is the only place the key actually arrives.
        """
        self.action_start()

    def on_input_submitted(self, ev: Input.Submitted) -> None:
        self.chosen_cmd = ev.value.strip()
        self._close_input()
        self.action_start()

    # --------------------------------------------------------------- actions
    def action_edit(self) -> None:
        box = self.query_one("#cmd", Input)
        box.add_class("active")
        box.disabled = False
        box.focus()
        self._say("editing — enter accepts and starts, escape cancels")

    def _close_input(self) -> None:
        box = self.query_one("#cmd", Input)
        box.remove_class("active")
        box.disabled = True
        self.query_one("#repos", ListView).focus()

    def action_switch(self) -> None:
        repos, cands = self.query_one("#repos", ListView), self.query_one("#cands", ListView)
        (cands if repos.has_focus else repos).focus()

    def action_move_next(self) -> None:
        self._focused_list().action_cursor_down()

    def action_move_prev(self) -> None:
        self._focused_list().action_cursor_up()

    def _focused_list(self) -> ListView:
        cands = self.query_one("#cands", ListView)
        return cands if cands.has_focus else self.query_one("#repos", ListView)

    def action_start(self) -> None:
        if not self.project:
            self._say("nothing selected")
            return
        cmd = (self.query_one("#cmd", Input).value or self.chosen_cmd).strip()
        if not cmd:
            self._say("no command — press e to type one")
            return
        self.exit((str(self.project.root), cmd))

    def key_escape(self) -> None:
        if not self.query_one("#cmd", Input).disabled:
            self._close_input()
            self._say("cancelled")

    def _say(self, msg: str) -> None:
        self.query_one("#status", Static).update(msg)


def choose(roots: list[str] | None = None) -> tuple[str, str] | None:
    """Run the picker. Returns (repo, command), or None if the user quit."""
    return Picker(roots).run()
