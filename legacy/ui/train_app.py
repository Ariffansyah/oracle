"""Live TUI for the DPO run - loss, reward margins, accuracy, progress.

Used by `python dpo_pipeline/train_dpo.py --tui`. Try it without torch:

    python -m ui.train_app          # synthetic run, same widgets
"""

from __future__ import annotations

import time
from typing import Callable

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Label, ProgressBar, Sparkline, Static

_TRACKED = (
    ("loss", "loss"),
    ("rewards/chosen", "r_chosen"),
    ("rewards/rejected", "r_rejected"),
    ("rewards/margins", "margin"),
    ("rewards/accuracies", "acc"),
    ("learning_rate", "lr"),
)


class TrainMonitor(App):
    """Runs `train_fn(on_log)` on a worker thread and plots what it reports."""

    CSS = """
    #top { height: auto; }
    #cfg { width: 1fr; border: round $primary; padding: 0 1; height: auto; }
    #plots { width: 1fr; height: auto; }
    .plot { height: 5; border: round $accent; padding: 0 1; }
    #logs { height: 1fr; border: round $accent; }
    #status { height: auto; padding: 0 1; }
    """

    BINDINGS = [Binding("q", "quit", "quit (stops after the current step)")]

    def __init__(self, train_fn: Callable, total_steps: int = 0, cfg: str = ""):
        super().__init__()
        self.train_fn = train_fn
        self.total_steps = total_steps
        self.cfg = cfg
        self.losses: list[float] = []
        self.margins: list[float] = []
        self.started = time.time()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="top"):
            yield Static(self.cfg or "(no config)", id="cfg")
            with VerticalScroll(id="plots"):
                yield Label("loss")
                yield Sparkline([0.0], id="loss-plot", classes="plot")
                yield Label("reward margin (chosen - rejected)")
                yield Sparkline([0.0], id="margin-plot", classes="plot")
        yield ProgressBar(total=self.total_steps or 100, show_eta=True, id="progress")
        yield Static("waiting for the first logging step …", id="status")
        yield DataTable(id="logs", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "ORACLE · DPO training"
        self.query_one("#logs", DataTable).add_columns(
            "step", *[short for _, short in _TRACKED], "elapsed"
        )
        self._train()

    # --- called from the training thread -----------------------------------
    def on_log(self, logs: dict) -> None:
        self.call_from_thread(self._append, dict(logs))

    def finish(self, message: str) -> None:
        self.call_from_thread(
            self.query_one("#status", Static).update, Text(message, style="bold green")
        )

    def _append(self, logs: dict) -> None:
        step = int(logs.get("step", len(self.losses) + 1))
        row = [str(step)]
        for key, _short in _TRACKED:
            v = logs.get(key)
            row.append("-" if v is None else f"{v:.4g}")
        row.append(f"{time.time() - self.started:.0f}s")
        table = self.query_one("#logs", DataTable)
        table.add_row(*row)
        table.move_cursor(row=table.row_count - 1)

        if (loss := logs.get("loss")) is not None:
            self.losses.append(float(loss))
            self.query_one("#loss-plot", Sparkline).data = self.losses[-120:]
        if (margin := logs.get("rewards/margins")) is not None:
            self.margins.append(float(margin))
            self.query_one("#margin-plot", Sparkline).data = self.margins[-120:]

        if self.total_steps:
            self.query_one("#progress", ProgressBar).update(progress=step)

        acc = logs.get("rewards/accuracies")
        parts = [f"step {step}"]
        if self.losses:
            parts.append(f"loss {self.losses[-1]:.4f}")
        if self.margins:
            parts.append(f"margin {self.margins[-1]:+.4f}")
        if acc is not None:
            parts.append(f"accuracy {acc:.1%}")
        style = "green" if self.margins and self.margins[-1] > 0 else "yellow"
        self.query_one("#status", Static).update(
            Text("  ·  ".join(parts), style=style)
            + Text("   (margin > 0 means chosen is preferred)", style="dim")
        )

    @work(thread=True, exclusive=True)
    def _train(self) -> None:
        try:
            self.train_fn(self.on_log)
        except Exception as e:  # surface the traceback instead of a blank screen
            self.finish(f"training failed: {type(e).__name__}: {e}")
            raise
        self.finish("training finished — adapter saved. press q to exit.")


def demo(on_log) -> None:
    """Synthetic run so the TUI is testable without torch."""
    import math
    import random

    rng = random.Random(0)
    for step in range(1, 61):
        time.sleep(0.05)
        on_log({
            "step": step,
            "loss": 0.69 * math.exp(-step / 25) + rng.uniform(0, 0.05),
            "rewards/chosen": step * 0.02 + rng.uniform(-0.05, 0.05),
            "rewards/rejected": -step * 0.015 + rng.uniform(-0.05, 0.05),
            "rewards/margins": step * 0.035 + rng.uniform(-0.05, 0.05),
            "rewards/accuracies": min(0.5 + step / 100, 1.0),
            "learning_rate": 5e-6 * (1 - step / 60),
        })


if __name__ == "__main__":
    TrainMonitor(demo, total_steps=60, cfg="demo run\nno torch, synthetic metrics").run()
