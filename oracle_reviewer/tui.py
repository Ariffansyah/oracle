"""Oracle Reviewer 3B — terminal UI.

    python -m oracle_reviewer.tui --repo ~/code/thing --run "python main.py"

Nothing leaves this machine: the model is served locally and there is no GitHub
integration, no telemetry and no network call other than to the local model host.

Left: the repository's commits. Right: the files that commit touched, the review,
and the diff in TWO columns — before on the left, after on the right — so a
changed line sits opposite the line it replaced.

Everything is a key. There are no buttons and no always-live text boxes: an
enabled Input swallows every letter you type, which is why editing a command in
place kept silently doing nothing. `:` opens a command line that is DISABLED
until you open it, and closes again on enter or escape.

  j/k ↓/↑ move    tab switch pane    r review    a apply (twice)
  c copy diff     e copy review      y copy all  w write report to a file
  : command       q quit

  :run python main.py     the command whose output defines what the project does
  :repo ~/code/thing      review a different repository
  :model oracle-reviewer-3b
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from rich.table import Table
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (Footer, Header, Input, Label, ListItem, ListView,
                             Static)

from . import core
from .splitdiff import split

RISK = {"high": "#f38ba8", "change": "#f9e2af", "fixes": "#a6e3a1", "ui-text": "#89b4fa", "unreachable": "#6c7086",
        "unclear": "#cba6f7", "none": "#6c7086", "unverified": "#9399b2"}
DOT = {"high": "●", "change": "●", "fixes": "●", "ui-text": "◇", "unreachable": "○",
       "unclear": "◆", "none": "○", "unverified": "○"}
HELP = ("commands:  :run <command>   :repo <path>   :model <name>   :timeout <secs>"
        "   ·   keys: r review, a apply, c/e/y copy, w write, q quit")


class Reviewer(App):
    TITLE = "Oracle Reviewer 3B"

    CSS = """
    #body { height: 1fr; }
    #left { width: 40; border-right: solid $panel-darken-2; }
    #commits { height: 1fr; }
    #files { height: 14; border-top: solid $panel-darken-2; }
    .head { background: $panel; color: $text-muted; padding: 0 1; }
    /* Stage 1 sits ABOVE the badge and looks different on purpose: it is a
       prediction over a population, not an observation about this run. */
    #stage1 { height: auto; padding: 1 2 0 2; color: $text-muted; }
    #badge { height: auto; padding: 1 2 0 2; text-style: bold; }
    #review { height: auto; max-height: 14; padding: 1 2; }
    #diffwrap { height: 1fr; border-top: solid $panel-darken-2; }
    #status { height: auto; padding: 0 2; background: $panel; }
    /* Disabled AND hidden until `:` opens it. A live Input takes every
       keystroke, so a persistent one makes the letter keys unreachable. */
    #cmdline { display: none; }
    #cmdline.active { display: block; }
    /* Same rule as the command line: hidden until asked for, so it never
       competes for the keys that drive the review. */
    #settings { display: none; }
    #settings.active {
        display: block; height: auto; padding: 1 2;
        background: $panel; border-top: solid $panel-darken-2;
    }
    """

    BINDINGS = [
        Binding("r", "review", "review"),
        Binding("a", "apply", "apply"),
        Binding("c", "copy_diff", "copy diff"),
        Binding("e", "copy_review", "copy review"),
        Binding("y", "copy_all", "copy all"),
        Binding("w", "write_report", "write file", show=False),
        Binding("s", "settings", "settings"),
        Binding("colon", "command_mode", ": command"),
        # Only act while the panel is open. A bare "1" silently changing how
        # the next review runs is the kind of surprise a settings bar exists
        # to prevent.
        Binding("1", "toggle_gate", "gate", show=False),
        Binding("2", "toggle_auto", "auto-review", show=False),
        Binding("3", "cycle_timeout", "timeout", show=False),
        Binding("tab", "switch_pane", "switch pane", show=False),
        Binding("j,down", "move_next", "next", show=False),
        Binding("k,up", "move_prev", "prev", show=False),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self, repo: str = ".", run: str = "",
                 host: str = "http://localhost:8111",
                 model: str = "oracle-reviewer-3b",
                 timeout: int = core.TIMEOUT, gate: bool = True) -> None:
        super().__init__()
        # `gate_ready` is not the same as `gate_on`. Stage 1 can only be loaded
        # before the TUI takes the terminal (see core.preload_gate: torch's
        # resource_tracker spawn dies once a full-screen app owns the fds), so
        # a session started with --no-gate can never turn it on again. The
        # panel says so rather than offering a switch that cannot work.
        self.gate_ready = gate
        self.gate_on = gate
        self.auto_review = False
        self._settings_open = False
        # An empty `run` means "work it out from the repository". Defaulting to
        # a Python command made the tool look broken on every project that is
        # not Python: the baseline could only ever fail.
        self.repo, self.run_cmd = repo, run
        self._run_explicit = bool(run)
        self.host, self.model, self.timeout = host, model, timeout
        self.commits: list[tuple[str, str]] = []      # (sha, subject)
        self.reviews: list[core.FileReview] = []
        self._armed: core.FileReview | None = None

    # ------------------------------------------------------------ composition
    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield Label("COMMITS", classes="head")
                yield ListView(id="commits")
                yield Label("FILES IN THIS COMMIT", classes="head")
                yield ListView(id="files")
            with Vertical():
                yield Static("", id="stage1")
                yield Static("", id="badge")
                yield Static("Press r to review the highlighted commit.",
                             id="review")
                with VerticalScroll(id="diffwrap"):
                    yield Static("", id="diff")
        yield Static("", id="settings")
        yield Static("", id="status")
        yield Input(placeholder="run python main.py", id="cmdline",
                    disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        self._detect()
        self._subtitle()
        self.load_commits(self.repo)
        self.query_one("#commits", ListView).focus()

    def _detect(self) -> None:
        """Pick a run command from the repository, unless one was given."""
        if self._run_explicit:
            self._say(HELP)
            return
        cmd, why = core.suggest_run(self.repo)
        if cmd:
            self.run_cmd = cmd
            self._say(f"run command set to `{cmd}` from {why} · "
                      f"change it with `:run <command>`", "#a6e3a1")
        else:
            self.run_cmd = ""
            self._say("could not tell how to run this project — set it with "
                      "`:run <command>` (anything whose output shows what the "
                      "project does)", "#f9e2af")

    def _subtitle(self) -> None:
        # The run command is the thing that decides whether anything can be
        # measured, so it is on screen at all times rather than inside a box.
        self.sub_title = (f"{core.repo_path(self.repo)}  ·  run: "
                          f"{self.run_cmd or '(none — use :run)'}"
                          f"  ·  {self.model}")

    def _say(self, text: str, colour: str = "#9399b2") -> None:
        self.query_one("#status", Static).update(Text(text, style=colour))

    # ---------------------------------------------------------------- commits
    @work(thread=True, exclusive=True, group="log")
    def load_commits(self, raw: str) -> None:
        repo = core.repo_path(raw)
        if not Path(repo).is_dir():
            self.call_from_thread(self._listed, [], f"no such directory: {repo}")
            return
        try:
            got = subprocess.run(
                ["git", "-C", repo, "log", "-n", "200",
                 "--pretty=%h\x1f%s\x1f%cr"],
                capture_output=True, text=True, timeout=15)
        except Exception as e:
            self.call_from_thread(self._listed, [], f"{type(e).__name__}: {e}")
            return
        if got.returncode:
            # git puts the reason on the FIRST stderr line; what follows is
            # advice about the search path, not what went wrong.
            lines = [l for l in got.stderr.splitlines() if l.strip()]
            why = next((l for l in lines if l.startswith("fatal:")),
                       lines[0] if lines else "not a git repository")
            self.call_from_thread(self._listed, [], why.removeprefix("fatal: "))
            return
        rows = []
        for line in got.stdout.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 3:
                rows.append((parts[0], parts[1], parts[2]))
        self.call_from_thread(self._listed, rows, None)

    def _listed(self, rows: list[tuple[str, str, str]], err: str | None) -> None:
        lv = self.query_one("#commits", ListView)
        lv.clear()
        self.commits = [(sha, subject) for sha, subject, _ in rows]
        for sha, subject, when in rows:
            lv.append(ListItem(Label(Text.assemble(
                (f"{sha}  ", "#89b4fa"), (subject[:26], "#cdd6f4"),
                (f"  {when}", "#6c7086")))))
        if err:
            self._say(err, "#f38ba8")
        else:
            self._say(f"{len(rows)} commits · press r to review the "
                      f"highlighted one · : for commands")
            if rows:
                lv.index = 0

    # ----------------------------------------------------------------- review
    def action_review(self) -> None:
        lv = self.query_one("#commits", ListView)
        if not self.commits or lv.index is None \
                or not 0 <= lv.index < len(self.commits):
            self._say("no commit selected", "#f38ba8")
            return
        if not self.run_cmd:
            self._say("no run command yet — set one with `:run <command>`",
                      "#f38ba8")
            return
        sha = self.commits[lv.index][0]
        self._armed = None
        self.reviews = []
        self.query_one("#files", ListView).clear()
        self._show(None)
        self._say(f"reviewing {sha} with `{self.run_cmd}` …", "#f9e2af")
        if self.gate_on:
            self.query_one("#stage1", Static).update("Stage 1 (JIT): scoring …")
            self.run_gate(self.repo, sha)
        else:
            self.query_one("#stage1", Static).update(
                "Stage 1 (JIT): off — every commit goes to the model")
        self.run_review(self.repo, sha, self.run_cmd, self.model)

    @work(thread=True, exclusive=True, group="gate")
    def run_gate(self, repo: str, sha: str) -> None:
        """Stage 1 loads an encoder, so it never blocks the review."""
        line = core.gate_line(core.gate_risk(repo, sha))
        self.call_from_thread(self.query_one("#stage1", Static).update, line)

    @work(thread=True, exclusive=True, group="review")
    def run_review(self, repo: str, sha: str, cmd: str, model: str) -> None:
        try:
            rs = core.review_commit(
                repo, sha, cmd, self.host, model,
                progress=lambda m: self.call_from_thread(self._say, m, "#f9e2af"),
                timeout=self.timeout)
            self.call_from_thread(self._filled, rs)
        except Exception as e:
            self.call_from_thread(self._say, f"{type(e).__name__}: {e}", "#f38ba8")

    def _filled(self, rs: list[core.FileReview]) -> None:
        self.reviews = rs
        lv = self.query_one("#files", ListView)
        for r in rs:
            lv.append(ListItem(Label(
                Text(f" {DOT[r.risk]}  {r.path}", style=RISK[r.risk]))))
        c = lambda k: sum(1 for r in rs if r.risk == k)
        if rs and all(r.why_unclear == "baseline" for r in rs):
            # One fact about the command, not N findings about the files.
            self._say(f"`{self.run_cmd}` already fails at the parent commit — "
                      f"nothing was measured. Set a working one with "
                      f"`:run <command>`", "#f38ba8")
        else:
            self._say(f"{len(rs)} file(s) · {c('high')} high risk · "
                      f"{c('change')} behaviour change · {c('unclear')} not "
                      f"established · {c('none')} cosmetic")
        if rs:
            lv.index = 0
            self._show(rs[0])

    @on(ListView.Highlighted, "#commits")
    def _pick_commit(self, ev: ListView.Highlighted) -> None:
        """Off by default: a review is two runs of the command per file, so
        moving down a list with it on is expensive by accident."""
        i = ev.list_view.index
        if self.auto_review and self.run_cmd and i is not None \
                and 0 <= i < len(self.commits):
            self.action_review()

    @on(ListView.Highlighted, "#files")
    def _pick_file(self, ev: ListView.Highlighted) -> None:
        self._armed = None
        # `ListView.clear()` is deferred, so a Highlighted carrying the PREVIOUS
        # review's index can arrive after `self.reviews` has been replaced by a
        # shorter one -- review a five-file commit, then a two-file commit, and
        # the stale index 4 indexes a list of 2. Bounds-checked rather than
        # guarded on emptiness alone, which is what crashed.
        i = ev.list_view.index
        if i is not None and 0 <= i < len(self.reviews):
            self._show(self.reviews[i])

    # ----------------------------------------------------------------- render
    def _show(self, r: core.FileReview | None) -> None:
        badge = self.query_one("#badge", Static)
        review = self.query_one("#review", Static)
        diff = self.query_one("#diff", Static)
        if r is None:
            badge.update("")           # stage1 is per-commit, left as it is
            review.update("Press r to review the highlighted commit.")
            diff.update("")
            return
        badge.update(Text(f"Oracle AI   [{r.badge}]", style=RISK[r.risk]))
        review.update(core.review_body(r, self.run_cmd))
        diff.update(self._table(r.diff))

    def _table(self, diff: str) -> Table:
        """Before and after as two columns, aligned line for line."""
        t = Table(box=None, expand=True, show_header=True, pad_edge=False)
        t.add_column("", width=4, style="#6c7086", no_wrap=True)
        t.add_column("before", ratio=1, overflow="fold")
        t.add_column("", width=4, style="#6c7086", no_wrap=True)
        t.add_column("after", ratio=1, overflow="fold")
        style = {"del": "#f38ba8", "add": "#a6e3a1", "ctx": "#cdd6f4",
                 "hunk": "#9399b2"}
        for left, right in split(diff):
            if left and left[2] == "hunk":
                t.add_row("", Text(left[1], style=style["hunk"]), "", "")
                continue
            cell = lambda c: (("", Text("")) if c is None else
                              (str(c[0] or ""), Text(c[1], style=style[c[2]])))
            ln, lt = cell(left)
            rn, rt = cell(right)
            t.add_row(ln, lt, rn, rt)
        return t

    # ------------------------------------------------------------- navigation
    def _focused_list(self) -> ListView:
        f = self.focused
        return f if isinstance(f, ListView) else self.query_one("#commits", ListView)

    def action_move_next(self) -> None:
        self._focused_list().action_cursor_down()

    def action_move_prev(self) -> None:
        self._focused_list().action_cursor_up()

    def action_switch_pane(self) -> None:
        here = self._focused_list()
        other = "#files" if here.id == "commits" else "#commits"
        self.query_one(other, ListView).focus()

    # ---------------------------------------------------------------- copying
    def _current(self) -> core.FileReview | None:
        i = self.query_one("#files", ListView).index
        return self.reviews[i] if self.reviews and i is not None else None

    def _report(self, r: core.FileReview) -> str:
        stage1 = str(self.query_one("#stage1", Static).render()).strip()
        return (f"{r.path}  [{r.badge}]\n\n"
                + (f"{stage1}\n\n" if stage1 else "") +
                f"{core.review_body(r, self.run_cmd)}\n\n"
                f"measured by running `{self.run_cmd}`\n"
                f"  before: {r.before}\n  after:  {r.after}\n\n{r.diff}")

    def _copy(self, text: str, what: str) -> None:
        """Clipboard via OSC 52, plus a native helper when one exists.

        OSC 52 works over SSH but several terminals ignore or truncate it, so a
        local wl-copy/xclip is tried as well — whichever lands, lands.
        """
        self.copy_to_clipboard(text)
        native = None
        for tool, cmd in (("wl-copy", ["wl-copy"]),
                          ("xclip", ["xclip", "-selection", "clipboard"]),
                          ("xsel", ["xsel", "--clipboard", "--input"])):
            if shutil.which(tool):
                try:
                    subprocess.run(cmd, input=text, text=True, timeout=5,
                                   check=True)
                    native = tool
                except (subprocess.SubprocessError, OSError):
                    native = None
                break
        via = f"via {native}" if native else "via OSC 52"
        self._say(f"copied {what} ({text.count(chr(10)) + 1} lines, "
                  f"{len(text)} chars) {via} · w writes it to a file instead",
                  "#a6e3a1")

    def action_copy_diff(self) -> None:
        r = self._current()
        self._copy(r.diff, "diff") if r else self._say("nothing to copy")

    def action_copy_review(self) -> None:
        r = self._current()
        if r:
            self._copy(core.review_body(r, self.run_cmd), "review")
        else:
            self._say("nothing to copy")

    def action_copy_all(self) -> None:
        r = self._current()
        self._copy(self._report(r), "full report") if r else self._say("nothing to copy")

    def action_write_report(self) -> None:
        """Escape hatch for terminals where no clipboard path works."""
        r = self._current()
        if not r:
            self._say("nothing to write")
            return
        out = Path.cwd() / f"oracle-review-{r.path.replace('/', '_')}.txt"
        out.write_text(self._report(r))
        self._say(f"wrote {out}", "#a6e3a1")

    # ------------------------------------------------------------------ apply
    def action_apply(self) -> None:
        r = self._current()
        # Gated on the RISK, not on `suggestion` being non-empty. Apply runs
        # `git checkout` over the whole file, which works for any change --
        # while `suggestion` is only the lines the diff removed, and a pure
        # addition removes none. Gating on it silently refused to offer a fix
        # for exactly the case that introduces a hang.
        if not r or r.risk != "high":
            self._armed = None
            self._say("nothing to apply here")
            return
        lv = self.query_one("#commits", ListView)
        base = f"{self.commits[lv.index][0]}^" if lv.index is not None else "HEAD^"
        if self._armed is not r:
            # Apply overwrites the working copy. Arming on the first press is
            # the confirmation, without a modal.
            self._armed = r
            self._say(f"press a again to restore {r.path} from {base} — this "
                      f"OVERWRITES your working copy. Any other key cancels.",
                      "#f9e2af")
            return
        self._armed = None
        got = subprocess.run(["git", "-C", core.repo_path(self.repo), "checkout",
                              base, "--", r.path], capture_output=True, text=True)
        if got.returncode:
            self._say(got.stderr.strip(), "#f38ba8")
        else:
            self._say(f"restored {r.path} from {base} — your working tree was "
                      f"edited", "#a6e3a1")

    # -------------------------------------------------------------- settings
    # Every switch here is one the tool actually has. Nothing is offered that
    # cannot be honoured: Stage 1 is shown as unavailable rather than as an
    # option, when the session was started without it.
    def _settings_rows(self) -> list[tuple[str, str, str, str]]:
        return [
            ("1", "Stage 1 (JIT) gate",
             "on" if self.gate_on else "off",
             "" if self.gate_ready
             else "unavailable — restart without --no-gate"),
            ("2", "auto-review on select",
             "on" if self.auto_review else "off",
             "reviews as you move; costs a run per commit"),
            ("3", "run timeout", f"{self.timeout}s",
             "each command gets this long, twice per file"),
        ]

    def _settings_text(self) -> str:
        rows = [f"SETTINGS   s or escape closes"]
        for key, name, value, note in self._settings_rows():
            rows.append(f"  {key}  {name:<24} {value:<8} {note}")
        return "\n".join(rows)

    def _refresh_settings(self) -> None:
        self.query_one("#settings", Static).update(self._settings_text())

    def action_settings(self) -> None:
        panel = self.query_one("#settings", Static)
        self._settings_open = not self._settings_open
        panel.set_class(self._settings_open, "active")
        if self._settings_open:
            self._refresh_settings()
            self._say("settings — press the number to change, s or escape to close")
        else:
            self._say("")

    def action_toggle_gate(self) -> None:
        if not self._settings_open:
            return
        if not self.gate_ready:
            self._say("Stage 1 cannot be loaded from inside the UI — restart "
                      "without --no-gate", "#f38ba8")
            return
        self.gate_on = not self.gate_on
        self._refresh_settings()
        self._say(f"Stage 1 gate {'on' if self.gate_on else 'off'}", "#a6e3a1")

    def action_toggle_auto(self) -> None:
        if not self._settings_open:
            return
        self.auto_review = not self.auto_review
        self._refresh_settings()
        self._say(f"auto-review {'on' if self.auto_review else 'off'}", "#a6e3a1")

    def action_cycle_timeout(self) -> None:
        if not self._settings_open:
            return
        steps = [60, 120, 300, 600]
        nxt = next((v for v in steps if v > self.timeout), steps[0])
        self.timeout = nxt
        self._refresh_settings()
        self._subtitle()
        self._say(f"each run may take up to {nxt}s", "#a6e3a1")

    # ----------------------------------------------------------- command line
    def action_command_mode(self) -> None:
        line = self.query_one("#cmdline", Input)
        line.disabled = False
        line.add_class("active")
        line.value = ""
        line.focus()
        self._say("`:` — enter runs, escape cancels · " + HELP)

    def _close_command(self) -> None:
        line = self.query_one("#cmdline", Input)
        line.remove_class("active")
        line.value = ""
        line.disabled = True
        self.query_one("#commits", ListView).focus()

    @on(Input.Submitted, "#cmdline")
    def _command(self, ev: Input.Submitted) -> None:
        text = ev.value.strip()
        self._close_command()
        if not text:
            return
        verb, _, rest = text.partition(" ")
        rest = rest.strip()
        if verb in ("run", "cmd") and rest:
            self._run_explicit = True
            self.run_cmd = rest
            self._say(f"run command is now `{rest}` · press r to review", "#a6e3a1")
        elif verb == "repo" and rest:
            self.repo = rest
            self._detect()
            self.load_commits(rest)
        elif verb == "model" and rest:
            self.model = rest
            self._say(f"model is now {rest}", "#a6e3a1")
        elif verb == "timeout" and rest.isdigit():
            self.timeout = int(rest)
            self._say(f"each run may take up to {rest}s", "#a6e3a1")
        elif verb == "host" and rest:
            self.host = rest
            self._say(f"host is now {rest}", "#a6e3a1")
        elif verb in ("help", "h", "?"):
            self._say(HELP)
        else:
            self._say(f"unknown command {text!r} · {HELP}", "#f38ba8")
        self._subtitle()

    def on_key(self, event) -> None:
        line = self.query_one("#cmdline", Input)
        if event.key == "escape" and line.has_class("active"):
            self._close_command()
            self._say("cancelled")
            event.stop()
            return
        if event.key == "escape" and self._settings_open:
            self.action_settings()
            event.stop()
            return
        if self._armed is not None and event.key != "a":
            self._armed = None
            self._say("apply cancelled")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--run", default="",
                    help="the command whose output defines what the project "
                         "does; detected from the repository when omitted")
    ap.add_argument("--model", default="oracle-reviewer-3b")
    ap.add_argument("--host", default="http://localhost:8111")
    ap.add_argument("--no-gate", action="store_true",
                    help="skip Stage 1, the JIT risk probability (it loads a "
                         "code encoder, which costs a few seconds at startup)")
    ap.add_argument("--timeout", type=int, default=core.TIMEOUT,
                    help="seconds one run of the command may take "
                         f"(default {core.TIMEOUT}); a lint or build over a "
                         "large codebase needs more")
    a = ap.parse_args()
    gate = not a.no_gate
    if gate:
        # Before the TUI starts, never inside it -- see core.preload_gate.
        print("loading Stage 1 (JIT gate) …", flush=True)
        why = core.preload_gate()
        if why:
            print(f"  Stage 1 unavailable: {why}", flush=True)
            # A failed preload is indistinguishable from --no-gate as far as
            # the settings panel is concerned: either way it cannot be turned
            # on later, so it must not be offered as a switch.
            gate = False
    Reviewer(repo=a.repo, run=a.run, host=a.host, model=a.model,
             timeout=a.timeout, gate=gate).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
