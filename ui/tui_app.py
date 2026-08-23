"""ORACLE TUI - commits, diff, and the model's analysis side by side.

    python main.py tui --repo /path/to/repo
    python main.py tui --mock

Left: recent commits. Middle: the syntax-highlighted diff. Right: the analysis
returned by the fine-tuned model, one entry per finding. `s` hides the commit
list when the code needs the room, `a` analyzes, `c`/`e`/`y` copy.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from rich.syntax import Syntax
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import (Footer, Header, Input, Label, ListItem,
                             ListView, Static)

from config import (BACKEND, BASE_MODEL, MERGED_MODEL_DIR, OLLAMA_HOST,
                    OLLAMA_MODEL, OLLAMA_NUM_CTX)
from dataset_builder.schema import Analysis
from ui.commands import CommandError, build_registry, run_command
from variance import VARIANTS


def model_label(backend: str, model_path: Path, ollama_model: str,
                host: str = OLLAMA_HOST) -> str:
    """What is answering: the backend, the model, and where it runs.

    A served model can sit behind a tunnel on another machine, so the host is
    part of the model's identity - "oracle-merged" alone does not say which
    box's oracle-merged.
    """
    if backend == "transformers":
        return f"transformers:{model_path.name}"
    return f"ollama:{ollama_model} @ {host.split('//', 1)[-1]}"


def served_note(claimed: str, served: list[str]) -> str:
    """Header suffix confirming the server really has the model we name."""
    if not served:
        return "  (no model served)"
    # Ollama reports "name:tag"; the config names the model without the tag.
    if any(n == claimed or n.split(":")[0] == claimed for n in served):
        return "  ✓"
    return f"  (server has {served[0]})"


_CATEGORY_STYLE = {
    "security": "bold red", "concurrency": "bold red",
    "null-dereference": "red", "resource-leak": "red",
    "off-by-one": "yellow", "logic-error": "yellow",
    "input-validation": "yellow", "error-handling": "yellow",
    "api-misuse": "cyan", "other": "dim",
}


@dataclass
class Commit:
    sha: str
    subject: str
    author: str
    date: str
    diff: str = ""
    gate: object | None = field(default=None, compare=False)   # Stage 1
    analysis: Analysis | None = field(default=None, compare=False)  # Stage 2

    @property
    def label(self) -> Text:
        mark = Text(f"{self.sha[:7]} ", style="dim")
        if self.analysis is None:
            mark.append("·  ", style="dim")
        elif self.analysis.findings:
            mark.append(f"{len(self.analysis.findings)}✗ ", style="red")
        else:
            mark.append("✓  ", style="green")
        mark.append(self.subject[:40])
        return mark


def git_log(repo: str, limit: int = 50) -> list[Commit]:
    out = subprocess.run(
        ["git", "-C", repo, "log", f"-{limit}",
         "--format=%H%x00%s%x00%an%x00%ad", "--date=short"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git log failed: {out.stderr.strip()}")
    return [Commit(*p) for line in out.stdout.splitlines()
            if len(p := line.split("\x00")) == 4]


def git_diff(repo: str, sha: str) -> str:
    out = subprocess.run(
        ["git", "-C", repo, "show", "--format=", "--unified=3", sha],
        capture_output=True, text=True,
    )
    return out.stdout if out.returncode == 0 else f"(diff unavailable: {out.stderr})"


def mock_commits() -> list[Commit]:
    import random

    from dataset_builder.mock_data import mock_commits as gen

    rng = random.Random(0)
    out = []
    for i, (diff, analysis) in enumerate(gen(10, rng)):
        subject = (f"fix: {analysis.findings[0].category} in module {i}"
                   if analysis.findings else f"refactor: tidy module {i}")
        out.append(Commit(f"mock{i:04d}" + "0" * 32, subject,
                          "demo@oracle.local", "2026-08-12", diff))
    return out


class OracleTUI(App):
    CSS = """
    #panes { height: 1fr; }
    #sidebar { width: 42; border: round $primary; }
    #sidebar.hidden { display: none; }
    #diff-pane { width: 3fr; border: round $accent; }
    #analysis-pane { width: 2fr; border: round $success; }
    #gate { height: auto; padding: 0 1; }
    #analysis { height: auto; padding: 0 1; }
    #status { height: auto; padding: 0 1; }
    #cmdline { display: none; border: none; height: 3; }
    #cmdline.active { display: block; }
    """

    BINDINGS = [
        Binding("s", "toggle_sidebar", "hide/show commits"),
        Binding("a", "analyze", "analyze"),
        Binding("j,down", "next_commit", "next", show=False),
        Binding("k,up", "prev_commit", "prev", show=False),
        Binding("r", "reload", "reload"),
        Binding("c", "copy_diff", "copy diff"),
        Binding("e", "copy_analysis", "copy analysis"),
        Binding("y", "copy_all", "copy all"),
        Binding("w", "write_report", "write file", show=False),
        Binding("colon", "command_mode", ": command"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self, commits: list[Commit], repo: str | None,
                 model_path=None, backend: str = BACKEND, gate=None):
        super().__init__()
        self.commits = commits
        self.repo = repo
        self.model_path = Path(model_path or MERGED_MODEL_DIR)
        # Once the fine-tuned model exists locally it is the better answer:
        # smaller, faster, and trained for exactly this. Fall back to a served
        # model only while it does not.
        if backend == "auto":
            trained = ((self.model_path / "config.json").exists() or
                       (self.model_path / "adapter_config.json").exists())
            backend = "transformers" if trained else "ollama"
        self.backend = backend
        self.index = 0
        self._syncing = False  # guards sidebar repopulation
        # Stage 1 is loaded *before* the app starts, in run(). Loading it from
        # inside a Textual worker spawns a subprocess (huggingface_hub) while
        # stdio is redirected, and Python raises
        # "ValueError: bad value(s) in fds_to_keep".
        self._gate = gate
        # Runtime-settable via `:` commands, so a session can switch model or
        # repo without restarting.
        self.ollama_model = OLLAMA_MODEL
        self.num_ctx = OLLAMA_NUM_CTX
        self.with_context = True
        # Which rendering of the diff to send. "off" is the real one; the rest
        # re-render the same change to show whether the verdict survives it.
        self.perturb = "off"
        self.limit = 50
        self.registry = build_registry(self)
        self._history: list[str] = []

    @property
    def current(self) -> Commit | None:
        return self.commits[self.index] if self.commits else None

    # --- layout ------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="panes"):
            yield ListView(*[ListItem(Label(c.label)) for c in self.commits],
                           id="sidebar")
            with VerticalScroll(id="diff-pane"):
                yield Static(id="diff")
            with VerticalScroll(id="analysis-pane"):
                yield Static(id="gate")
                yield Static(id="analysis")
        yield Static(id="status")
        # Disabled until `:` opens it - a hidden-but-enabled Input still takes
        # focus and swallows every keystroke.
        yield Input(placeholder="type a command, e.g. model qwen3-coder",
                    id="cmdline", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "ORACLE"
        self._refresh_subtitle()
        self._probe_model()
        self._select(0)
        self.query_one("#sidebar", ListView).focus()
        self._status("[s] commits · [j/k] move · [a] analyze · [:] command "
                     "(:help lists them)")

    # --- rendering ---------------------------------------------------------
    def _refresh_subtitle(self, note: str = "") -> None:
        label = model_label(self.backend, self.model_path, self.ollama_model)
        # A perturbed answer must never be mistaken for the model's real one.
        rendering = "" if self.perturb == "off" else f" · rendering:{self.perturb}"
        self.sub_title = (f"{self.repo or 'mock commits'} · {label}"
                          f"{rendering}{note}")

    def _status(self, msg: str, style: str = "dim") -> None:
        self.query_one("#status", Static).update(Text(msg, style=style))

    def _select(self, index: int) -> None:
        if not (0 <= index < len(self.commits)):
            return
        self.index = index
        commit = self.commits[index]
        if not commit.diff and self.repo:
            commit.diff = git_diff(self.repo, commit.sha)

        self.query_one("#diff", Static).update(
            Syntax(commit.diff or "(empty diff)", "diff",
                   line_numbers=True, theme="ansi_dark", word_wrap=False)
        )
        self._render_gate(commit)
        self._render_analysis(commit)
        if commit.gate is None and not commit.sha.startswith("mock"):
            self._score_gate(commit)

    def _render_gate(self, commit: Commit) -> None:
        """Stage 1 probability, always shown - it is why Stage 2 did or did not run."""
        target = self.query_one("#gate", Static)
        d = commit.gate
        if d is None:
            target.update(Text("stage 1 · scoring…", style="dim"))
            return
        if isinstance(d, str):          # gate unavailable, carrying the reason
            body = Text("stage 1 · ", style="bold")
            body.append(d + "\n", style="yellow")
            body.append("stage 2 still runs — press [a]\n\n", style="dim")
            target.update(body)
            return

        style = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}[d.band]
        body = Text()
        body.append("stage 1 · gatekeeper\n", style="bold")
        body.append(f"{d.score:.1%} {d.band}", style=f"bold {style}")
        body.append(f"   gate {d.threshold:.1%}\n", style="dim")
        body.append(d.reason + "\n", style="italic dim")
        for name, value in d.top_metrics:
            body.append(f"  {name:<6}{value:>10g}\n", style="dim")
        body.append("\n")
        target.update(body)

    @work(thread=True, exclusive=False)
    def _score_gate(self, commit: Commit) -> None:
        if self._gate is None:
            commit.gate = "not loaded (train one: python -m ml_model.train_gate)"
            if self.current is commit:
                self.call_from_thread(self._render_gate, commit)
            return
        try:
            decision = self._gate.decide(commit.diff)
        except Exception as e:
            # The message, not just the type - "unavailable (ValueError)" says
            # nothing about which of a dozen causes it was.
            decision = f"unavailable — {type(e).__name__}: {e}"
        commit.gate = decision
        if self.current is commit:
            self.call_from_thread(self._render_gate, commit)

    def _render_analysis(self, commit: Commit) -> None:
        target = self.query_one("#analysis", Static)
        analysis = commit.analysis
        if analysis is None:
            target.update(Text("stage 2 · press [a] to run the validator",
                               style="dim"))
            return

        body = Text()
        body.append("stage 2 · semantic validator\n", style="bold")
        body.append(analysis.summary + "\n\n")
        if not analysis.findings:
            body.append("✓ no defects found in the diff\n", style="green")
            target.update(body)
            return
        body.append(f"{len(analysis.findings)} finding(s)\n\n", style="bold")
        for i, f in enumerate(analysis.findings, 1):
            body.append(f"{i}. {f.category}",
                        style=_CATEGORY_STYLE.get(f.category, "yellow"))
            if f.file:
                body.append(f"  {f.file}", style="cyan")
            body.append("\n")
            body.append(f"   {f.explanation}\n\n")
        target.update(body)

    def _refresh_sidebar(self) -> None:
        """Redraw the list (risk marks arrive asynchronously) without moving
        the selection - repopulating fires Highlighted, which would otherwise
        drag the user back to whatever the list last had selected."""
        lv = self.query_one("#sidebar", ListView)
        self._syncing = True
        try:
            lv.clear()
            for c in self.commits:
                lv.append(ListItem(Label(c.label)))
            lv.index = self.index
        finally:
            self._syncing = False

    # --- workers -----------------------------------------------------------
    @work(thread=True, group="probe")
    def _probe_model(self) -> None:
        """Ask the server what it actually serves before the header claims it.

        The name in the config is a request, not a fact: the server may hold a
        different model, or be down behind a tunnel that still accepts writes.
        """
        if self.backend != "ollama":
            return
        import json
        import urllib.request

        try:
            with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=3) as r:
                served = [m.get("name", "")
                          for m in json.load(r).get("models", [])]
        except Exception:
            self.call_from_thread(self._refresh_subtitle, "  (unreachable)")
            return
        self.call_from_thread(self._refresh_subtitle,
                              served_note(self.ollama_model, served))

    @work(thread=True, exclusive=True)
    def _run_analysis(self, commit: Commit) -> None:
        from llm_explainer.client import InferenceError, OracleClient

        client = OracleClient(model_path=self.model_path, backend=self.backend,
                              ollama_model=self.ollama_model)

        def progress(i: int, total: int, path: str) -> None:
            self.call_from_thread(
                self._status, f"reading {commit.sha[:7]} · file {i}/{total} · {path}",
                "yellow")

        try:
            if self.perturb != "off":
                # Re-render the same change and ask again. The perturbations
                # touch git metadata only, so a different answer here is the
                # model reading punctuation - the whole point of :perturb.
                # Goes through analyze() because analyze_commit() re-fetches
                # the diff from git and would undo the edit.
                analysis = client.analyze(VARIANTS[self.perturb](commit.diff),
                                          subject=commit.subject,
                                          progress=progress)
            elif self.repo and not commit.sha.startswith("mock"):
                # Fetches `git show -U50` plus post-commit file bodies, so a
                # guard is judged against the control it protects.
                analysis = client.analyze_commit(self.repo, commit.sha,
                                                 progress=progress,
                                                 with_context=self.with_context)
            else:
                analysis = client.analyze(commit.diff, subject=commit.subject,
                                          progress=progress)
        except (InferenceError, Exception) as e:
            self.call_from_thread(self._status, f"analysis failed: {e}", "red")
            return
        commit.analysis = analysis
        self.call_from_thread(self._after_analysis, commit)

    def _after_analysis(self, commit: Commit) -> None:
        if self.current is commit:
            self._render_analysis(commit)
        n = len(commit.analysis.findings)
        self._status(f"{commit.sha[:7]}: {n} finding(s)", "red" if n else "green")

    # --- copying -----------------------------------------------------------
    def _copy(self, text: str, what: str) -> None:
        """Clipboard via OSC 52, plus a native helper when one exists.

        OSC 52 works over SSH but several terminals ignore or truncate it, so a
        local wl-copy/xclip is tried as well - whichever lands, lands.
        """
        self.copy_to_clipboard(text)
        native = None
        for tool, cmd in (("wl-copy", ["wl-copy"]),
                          ("xclip", ["xclip", "-selection", "clipboard"]),
                          ("xsel", ["xsel", "--clipboard", "--input"])):
            if shutil.which(tool):
                try:
                    subprocess.run(cmd, input=text, text=True, timeout=5, check=True)
                    native = tool
                except (subprocess.SubprocessError, OSError):
                    native = None
                break
        lines = text.count("\n") + 1
        via = f"via {native}" if native else "via OSC 52"
        self._status(f"copied {what} ({lines} lines, {len(text)} chars) {via} · "
                     f"[w] writes it to a file instead", "green")

    def _analysis_text(self, commit: Commit) -> str:
        a = commit.analysis
        if a is None:
            return "semantic review: not run"
        out = [f"semantic review\n{a.summary}"]
        if not a.findings:
            out.append("\nno defects found in the diff")
        for i, f in enumerate(a.findings, 1):
            where = f"  [{f.file}]" if f.file else ""
            out.append(f"\n{i}. {f.category}{where}\n   {f.explanation}")
        return "\n".join(out)

    def _report_text(self, commit: Commit) -> str:
        return (f"commit {commit.sha}\n"
                f"subject: {commit.subject}\n"
                f"author: {commit.author}  date: {commit.date}\n"
                f"{'=' * 72}\n\n"
                f"{self._analysis_text(commit)}\n\n"
                f"{'-' * 72}\n\ndiff\n\n{commit.diff}")

    def action_copy_diff(self) -> None:
        if self.current:
            self._copy(self.current.diff, "diff")

    def action_copy_analysis(self) -> None:
        if self.current:
            self._copy(self._analysis_text(self.current), "analysis")

    def action_copy_all(self) -> None:
        if self.current:
            self._copy(self._report_text(self.current), "full report")

    def action_write_report(self) -> None:
        """Escape hatch for terminals where no clipboard path works."""
        try:
            self._status(self.write_report(), "green")
        except CommandError as e:
            self._status(str(e), "red")

    # --- command mode ------------------------------------------------------
    def action_command_mode(self) -> None:
        line = self.query_one("#cmdline", Input)
        line.disabled = False
        line.add_class("active")
        line.value = ""
        line.focus()
        self._status("`:` — enter runs, escape cancels, :help lists commands")

    def _close_command(self) -> None:
        line = self.query_one("#cmdline", Input)
        line.remove_class("active")
        line.value = ""
        line.disabled = True
        self.query_one("#sidebar", ListView).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "cmdline":
            return
        text = event.value
        self._close_command()
        if not text.strip():
            return
        self._history.append(text)
        try:
            message = run_command(self.registry, text)
        except CommandError as e:
            self._status(str(e), "red")
            return
        except Exception as e:  # a command must never take the app down
            self._status(f"{type(e).__name__}: {e}", "red")
            return
        # :model, :backend and :repo all move what the header names, so one
        # refresh here covers every command instead of three call sites.
        self._refresh_subtitle()
        self._probe_model()
        if message:
            self._status(message, "green")

    def on_key(self, event) -> None:
        if event.key == "escape" and self.query_one("#cmdline", Input).has_class("active"):
            self._close_command()
            self._status("cancelled")
            event.stop()

    # --- command targets ---------------------------------------------------
    def select(self, index: int) -> None:
        """Public alias used by `:goto`."""
        self._select(index)
        self._refresh_sidebar()

    def load_repo(self, path: str) -> None:
        """Point the session at another repository."""
        target = Path(path).expanduser()
        if not (target / ".git").exists():
            raise CommandError(f"{target} is not a git repository")
        commits = git_log(str(target), self.limit)
        if not commits:
            raise CommandError(f"no commits in {target}")
        self.repo = str(target)
        self.commits = commits
        self.index = 0
        self.sub_title = f"{self.repo} · {self.backend}"
        self._refresh_sidebar()
        self._select(0)

    def write_report(self, path: str | None = None) -> str:
        if not self.current:
            raise CommandError("no commit selected")
        target = Path(path).expanduser() if path else Path(
            f"oracle-{self.current.sha[:8]}.txt")
        target.write_text(self._report_text(self.current))
        return f"wrote {target.resolve()}"

    # --- actions -----------------------------------------------------------
    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar", ListView)
        sidebar.toggle_class("hidden")
        if not sidebar.has_class("hidden"):
            sidebar.index = self.index
            sidebar.focus()

    def action_next_commit(self) -> None:
        self._select(min(self.index + 1, len(self.commits) - 1))

    def action_prev_commit(self) -> None:
        self._select(max(self.index - 1, 0))

    def action_reload(self) -> None:
        if not self.repo:
            self._status("mock mode — nothing to reload")
            return
        self.commits = git_log(self.repo)
        self._refresh_sidebar()
        self._select(0)
        self._status(f"reloaded {len(self.commits)} commits")

    def action_analyze(self) -> None:
        commit = self.current
        if commit is None:
            return
        self._status(f"reading {commit.sha[:7]} …", "yellow")
        self._run_analysis(commit)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not self._syncing and event.list_view.index is not None:
            self._select(event.list_view.index)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if not self._syncing and event.list_view.index is not None:
            self._select(event.list_view.index)


def load_gate():
    """Stage 1, loaded before the TUI takes over stdio.

    The encoder pulls from huggingface_hub, which may spawn a subprocess; doing
    that inside a Textual worker fails with "bad value(s) in fds_to_keep".
    Loading here also means the first commit is scored immediately instead of
    waiting several seconds for a cold model.
    """
    try:
        from ml_model.gate import Gatekeeper

        print("loading stage 1 gatekeeper …", flush=True)
        gate = Gatekeeper.load()
        if gate.use_embeddings:
            # `.encoder` only constructs the wrapper; the transformers model
            # loads lazily on the first encode. Scoring one diff here forces
            # that load into this process, where a subprocess spawn is legal.
            gate.decide("diff --git a/warm.py b/warm.py\n@@ -1 +1 @@\n-a\n+b\n")
        return gate
    except FileNotFoundError:
        print("no gatekeeper trained — stage 1 will be skipped", flush=True)
    except Exception as e:
        print(f"stage 1 unavailable ({type(e).__name__}: {e})", flush=True)
    return None


def run(repo: str | None = None, model_path=None, backend: str = BACKEND,
        limit: int = 50, with_gate: bool = True) -> None:
    commits = git_log(repo, limit) if repo else mock_commits()
    if not commits:
        raise SystemExit(f"no commits found in {repo}")
    gate = load_gate() if with_gate else None
    OracleTUI(commits, repo, model_path, backend, gate).run()


if __name__ == "__main__":
    run()
