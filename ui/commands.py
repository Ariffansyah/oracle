"""Vim-style `:` commands for the TUI.

Kept out of the app so the parsing and the dispatch table are testable without
starting a terminal. Every command returns a status string; raising is reserved
for genuine errors the app should surface in red.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


class CommandError(Exception):
    """Bad command or bad argument - shown to the user, not a crash."""


@dataclass
class Command:
    names: tuple[str, ...]
    args: str
    help: str
    run: Callable

    @property
    def name(self) -> str:
        return self.names[0]

    @property
    def usage(self) -> str:
        alias = f" ({', '.join(self.names[1:])})" if len(self.names) > 1 else ""
        return f":{self.name}{alias} {self.args}".rstrip()


def build_registry(app) -> dict[str, Command]:
    """Command table bound to a running app."""

    def need(args: list[str], what: str) -> str:
        if not args:
            raise CommandError(f"expected {what}")
        return " ".join(args)

    def cmd_model(args):
        name = need(args, "a model name, e.g. :model qwen2.5-review")
        app.ollama_model = name
        return f"model → {name}"

    def cmd_backend(args):
        name = need(args, "transformers or ollama")
        if name not in ("transformers", "ollama"):
            raise CommandError(f"unknown backend {name!r}; use transformers|ollama")
        app.backend = name
        return f"backend → {name}"

    def cmd_repo(args):
        path = need(args, "a repository path")
        app.load_repo(path)
        return f"repo → {path} ({len(app.commits)} commits)"

    def cmd_limit(args):
        raw = need(args, "a number, e.g. :limit 100")
        try:
            n = int(raw)
        except ValueError:
            raise CommandError(f"{raw!r} is not a number") from None
        if n < 1:
            raise CommandError("limit must be at least 1")
        app.limit = n
        app.load_repo(app.repo) if app.repo else None
        return f"limit → {n}"

    def cmd_context(args):
        state = (args[0] if args else "").lower()
        if state not in ("on", "off"):
            raise CommandError("use :context on | :context off")
        app.with_context = state == "on"
        return (f"full-file context {'on' if app.with_context else 'off'} "
                f"— off reviews the bare diff")

    def cmd_perturb(args):
        """Send a cosmetically different rendering of the same diff.

        Measured on 40 held-out commits, verdicts survived these edits only
        87.7% of the time and per-rendering F1 ranged 0.08-0.31. This makes
        that visible on one commit: analyze, switch rendering, analyze again.
        """
        from variance import VARIANTS

        name = (args[0] if args else "").lower()
        allowed = ("off",) + tuple(k for k in VARIANTS if k != "base")
        if name not in allowed:
            raise CommandError(f"use :perturb {' | '.join(allowed)}")
        app.perturb = name
        if name == "off":
            return "rendering → the real diff"
        return (f"rendering → {name} (same change, different text; "
                f"a new verdict here is noise, not a finding)")

    def cmd_ctx_size(args):
        raw = need(args, "a token count, e.g. :numctx 16384")
        try:
            n = int(raw)
        except ValueError:
            raise CommandError(f"{raw!r} is not a number") from None
        app.num_ctx = n
        return f"num_ctx → {n} tokens"

    def cmd_analyze(args):
        app.action_analyze()
        return "analyzing…"

    def cmd_copy(args):
        what = (args[0] if args else "all").lower()
        if what in ("diff", "d"):
            app.action_copy_diff()
        elif what in ("analysis", "review", "a"):
            app.action_copy_analysis()
        elif what in ("all", "report"):
            app.action_copy_all()
        else:
            raise CommandError("use :copy diff | analysis | all")
        return ""  # the copy action writes its own status

    def cmd_write(args):
        return app.write_report(args[0] if args else None)

    def cmd_goto(args):
        raw = need(args, "a commit number or sha prefix")
        if raw.isdigit():
            app.select(int(raw) - 1)
            return f"commit {raw}"
        for i, c in enumerate(app.commits):
            if c.sha.startswith(raw):
                app.select(i)
                return f"{c.sha[:8]} {c.subject[:40]}"
        raise CommandError(f"no commit matching {raw!r}")

    def cmd_reload(args):
        app.action_reload()
        return ""

    def cmd_sidebar(args):
        app.action_toggle_sidebar()
        return ""

    def cmd_info(args):
        return (f"model={app.ollama_model} backend={app.backend} "
                f"rendering={app.perturb} "
                f"context={'on' if app.with_context else 'off'} "
                f"num_ctx={app.num_ctx} repo={app.repo or 'mock'} "
                f"commits={len(app.commits)}")

    def cmd_help(args):
        # Dedupe by primary name: aliases share a Command instance.
        seen, out = set(), []
        for c in REGISTRY.values():
            if c.name not in seen:
                seen.add(c.name)
                out.append(c.usage)
        return "  ".join(out)

    def cmd_quit(args):
        app.exit()
        return "bye"

    commands = [
        Command(("model", "m"), "<name>", "switch the reviewer model", cmd_model),
        Command(("backend",), "<transformers|ollama>", "switch inference backend",
                cmd_backend),
        Command(("repo", "open"), "<path>", "load another repository", cmd_repo),
        Command(("limit",), "<n>", "how many commits to list", cmd_limit),
        Command(("context", "ctx"), "<on|off>", "send full-file context",
                cmd_context),
        Command(("numctx",), "<tokens>", "model context window", cmd_ctx_size),
        Command(("perturb", "p"), "<off|no_index|rehash|bare_hunk>",
                "re-render the diff to test verdict stability", cmd_perturb),
        Command(("analyze", "a"), "", "analyze the selected commit", cmd_analyze),
        Command(("copy", "y"), "[diff|analysis|all]", "copy to clipboard", cmd_copy),
        Command(("write", "w"), "[path]", "write the report to a file", cmd_write),
        Command(("goto", "g"), "<n|sha>", "jump to a commit", cmd_goto),
        Command(("reload",), "", "re-read the commit list", cmd_reload),
        Command(("sidebar",), "", "hide or show the commit list", cmd_sidebar),
        Command(("info",), "", "show current settings", cmd_info),
        Command(("help", "h"), "", "list commands", cmd_help),
        Command(("quit", "q"), "", "exit", cmd_quit),
    ]

    REGISTRY = {name: c for c in commands for name in c.names}
    return REGISTRY


def run_command(registry: dict[str, Command], line: str) -> str:
    """Parse and dispatch one `:` line. Raises CommandError on bad input."""
    line = line.strip().lstrip(":").strip()
    if not line:
        return ""
    head, *args = line.split()
    command = registry.get(head.lower())
    if command is None:
        near = [n for n in registry if n.startswith(head.lower())]
        hint = f" — did you mean :{near[0]}?" if near else " — try :help"
        raise CommandError(f"unknown command :{head}{hint}")
    return command.run(args)


if __name__ == "__main__":
    # Run standalone, sys.path[0] is ui/, so the root-level modules the
    # commands reach for (variance) are not importable without this.
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    class FakeApp:
        def __init__(self):
            self.ollama_model = "qwen2.5-review"
            self.backend = "ollama"
            self.repo = "/tmp/x"
            self.with_context = True
            self.perturb = "off"
            self.num_ctx = 16384
            self.limit = 50
            self.commits = []
            self.analyzed = False

        def load_repo(self, path):
            self.repo = path

        def action_analyze(self):
            self.analyzed = True

        def exit(self):
            self.exited = True

    app = FakeApp()
    reg = build_registry(app)

    assert "qwen3-coder" in run_command(reg, ":model qwen3-coder")
    assert app.ollama_model == "qwen3-coder"
    assert run_command(reg, "m qwen2.5-review") and app.ollama_model == "qwen2.5-review"
    run_command(reg, ":context off")
    assert app.with_context is False
    run_command(reg, ":numctx 32768")
    assert app.num_ctx == 32768
    assert "bare_hunk" in run_command(reg, ":perturb bare_hunk")
    assert app.perturb == "bare_hunk"
    assert run_command(reg, ":p off") and app.perturb == "off"
    try:
        run_command(reg, ":perturb sideways")
        raise AssertionError("an unknown rendering must be refused")
    except CommandError:
        pass
    run_command(reg, ":analyze")
    assert app.analyzed

    for bad, why in ((":model", "missing arg"),
                     (":backend nope", "bad value"),
                     (":numctx abc", "not a number"),
                     (":nonsense", "unknown command"),
                     (":limit 0", "out of range")):
        try:
            run_command(reg, bad)
        except CommandError:
            pass
        else:
            raise AssertionError(f"{bad} should have failed ({why})")

    # A near-miss should suggest, not just reject.
    try:
        run_command(reg, ":mod x")
    except CommandError as e:
        assert "did you mean :model" in str(e), e

    assert run_command(reg, "") == ""
    assert ":help" in run_command(reg, ":help")
    print(f"{len({c.name for c in reg.values()})} commands, parsing + errors ok")
