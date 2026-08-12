"""ORACLE review TUI - editor-style diff on the left, evidence on the right.

    python main.py tui --mock
    python main.py tui --commit HEAD --repo /path/to/repo

The left pane is a read-only syntax-highlighted diff with line numbers. The
right pane holds the risk score, the SHAP drivers and the LLM findings.
Selecting a finding jumps the diff to the cited line and highlights it.
"""

from __future__ import annotations

from rich.syntax import Syntax
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Static

import config
from llm_explainer.prompts import ReviewResult
from ml_model.classifier import RiskModel, RiskResult
from ml_model.kamei_metrics import CommitFeatures, diff_line_index
from ui.terminal_display import risk_panel, shap_table

_CONF_COLOR = ((0.75, "red"), (0.4, "yellow"), (0.0, "green"))


class OracleApp(App):
    """Two-pane review dashboard."""

    CSS = """
    #panes { height: 1fr; }
    #code-pane { width: 3fr; border: round $primary; }
    #side { width: 2fr; }
    #findings { height: 1fr; border: round $accent; }
    #detail { height: auto; min-height: 8; border: round $accent; padding: 0 1; }
    #evidence { height: auto; }
    .title { text-style: bold; }
    """

    BINDINGS = [
        Binding("q", "quit", "quit"),
        Binding("e", "explain", "run LLM"),
        Binding("j,down", "next_finding", "next", show=False),
        Binding("k,up", "prev_finding", "prev", show=False),
        Binding("f", "focus_code", "focus diff"),
    ]

    def __init__(self, commit: CommitFeatures, risk: RiskResult, llm_model: str):
        super().__init__()
        self.commit = commit
        self.risk = risk
        self.llm_model = llm_model
        self.review: ReviewResult | None = None
        self._index = diff_line_index(commit.diff)
        self._status = "press [e] to run the LLM reviewer"

    # --- layout ------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="panes"):
            with VerticalScroll(id="code-pane"):
                yield Static(self._code(), id="code")
            with VerticalScroll(id="side"):
                yield Static(id="evidence")
                yield DataTable(id="findings", cursor_type="row", zebra_stripes=True)
                yield Static(id="detail")
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"ORACLE  {self.commit.rev}"
        self.sub_title = self.commit.subject
        table = self.query_one("#findings", DataTable)
        table.add_columns("#", "category", "location", "conf", "g/f")
        self._refresh_side()

    # --- rendering ---------------------------------------------------------
    def _code(self, highlight: int | None = None) -> Syntax:
        return Syntax(
            self.commit.diff or "(no diff)",
            "diff",
            line_numbers=True,
            word_wrap=False,
            theme="ansi_dark",
            highlight_lines={highlight} if highlight else None,
        )

    def _refresh_side(self) -> None:
        from rich.console import Group

        self.query_one("#evidence", Static).update(
            Group(risk_panel(self.commit, self.risk), shap_table(self.risk))
        )

        table = self.query_one("#findings", DataTable)
        table.clear()
        if self.review is None:
            self.query_one("#detail", Static).update(Text(self._status, style="dim"))
            return

        for i, f in enumerate(self.review.findings, 1):
            color = next(c for cutoff, c in _CONF_COLOR if f.confidence >= cutoff)
            table.add_row(
                str(i), f.category, f.file_line,
                Text(f"{f.confidence:.2f}", style=color),
                ("G" if f.grounded else "g") + ("F" if f.faithful else "f"),
            )
        if self.review.findings:
            table.focus()
            self._show_detail(0)
        else:
            self.query_one("#detail", Static).update(
                Text.assemble(
                    (self.review.summary + "\n\n", ""),
                    ("✓ 0 semantic findings — the statistical flag was not borne out "
                     "by the code.", "green"),
                )
            )

    def _show_detail(self, row: int) -> None:
        if self.review is None or not (0 <= row < len(self.review.findings)):
            return
        f = self.review.findings[row]
        flags = []
        if not f.grounded:
            flags.append("not grounded — cites lines outside the diff")
        if not f.faithful:
            flags.append("not faithful — explanation goes beyond the cited code")
        self.query_one("#detail", Static).update(
            Text.assemble(
                (f"{f.category}  ", "bold"),
                (f"{f.file_line}  ", "cyan"),
                (f"confidence {f.confidence:.2f}\n\n", "dim"),
                (f.explanation + "\n", ""),
                *[("\n! " + m, "yellow") for m in flags],
                ("\n\nsummary: ", "dim"), (self.review.summary, "dim"),
            )
        )
        self._jump_to(f.file_line)

    def _jump_to(self, file_line: str) -> None:
        """Highlight and scroll to the diff line a finding cites."""
        path, _, num = file_line.rpartition(":")
        if not path or not num.isdigit():
            return
        offset = self._index.get((path, int(num)))
        if offset is None:  # cited line is not in the diff — that means ungrounded
            return
        self.query_one("#code", Static).update(self._code(highlight=offset))
        pane = self.query_one("#code-pane", VerticalScroll)
        pane.scroll_to(y=max(offset - pane.size.height // 2, 0), animate=False)

    # --- actions -----------------------------------------------------------
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._show_detail(event.cursor_row)

    def action_focus_code(self) -> None:
        self.query_one("#code-pane").focus()

    def action_next_finding(self) -> None:
        self.query_one("#findings", DataTable).action_cursor_down()

    def action_prev_finding(self) -> None:
        self.query_one("#findings", DataTable).action_cursor_up()

    def action_explain(self) -> None:
        self._status = f"querying {self.llm_model} …"
        self.query_one("#detail", Static).update(Text(self._status, style="yellow"))
        self._run_llm()

    @work(thread=True, exclusive=True)
    def _run_llm(self) -> None:
        from llm_explainer.client import LLMError, OllamaClient

        try:
            review = OllamaClient(model=self.llm_model).review(
                diff=self.commit.diff,
                risk_score=self.risk.score,
                risk_band=self.risk.band,
                contributions=[str(c) for c in self.risk.drivers],
                subject=self.commit.subject,
                files=self.commit.files,
            )
        except LLMError as e:
            self._status = f"LLM unavailable: {e}"
            self.call_from_thread(self._refresh_side)
            return
        self.review = review
        self.call_from_thread(self._refresh_side)


def run(commit: CommitFeatures, model_path=None, llm_model: str = config.OLLAMA_MODEL,
        auto_explain: bool = False) -> None:
    risk = RiskModel.load(model_path or config.MODEL_PATH).score(commit)
    app = OracleApp(commit, risk, llm_model)
    if auto_explain:
        app.call_later(app.action_explain)
    app.run()


if __name__ == "__main__":
    from ml_model.kamei_metrics import mock_commit

    run(mock_commit(seed=2))
