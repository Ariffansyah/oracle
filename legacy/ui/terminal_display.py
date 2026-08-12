"""Rich terminal dashboard: risk score, SHAP features, LLM summary, findings."""

from __future__ import annotations

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ml_model.classifier import RiskResult
from ml_model.kamei_metrics import CommitFeatures
from llm_explainer.prompts import ReviewResult

console = Console()

_BAND_COLOR = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}
_CONF_COLOR = ((0.75, "red"), (0.4, "yellow"), (0.0, "green"))


def _conf_color(c: float) -> str:
    return next(color for cutoff, color in _CONF_COLOR if c >= cutoff)


def risk_panel(commit: CommitFeatures, risk: RiskResult) -> Panel:
    color = _BAND_COLOR.get(risk.band, "white")
    bar_width = 40
    filled = round(risk.score * bar_width)
    bar = Text("█" * filled, style=color) + Text("░" * (bar_width - filled), style="dim")

    header = Table.grid(padding=(0, 2))
    header.add_column(style="bold")
    header.add_column()
    header.add_row("commit", f"{commit.rev}  {commit.subject}")
    header.add_row("author", commit.author or "(unknown)")
    header.add_row("files", ", ".join(commit.files) or "(unknown)")
    header.add_row("risk", Text.assemble(bar, "  ", (f"{risk.score:.1%} {risk.band}", f"bold {color}")))

    return Panel(header, title="[bold]JIT Defect Risk", border_style=color)


def shap_table(risk: RiskResult) -> Table:
    t = Table(title="Top SHAP contributions (Kamei process metrics)",
              title_justify="left", header_style="bold", expand=False)
    t.add_column("feature")
    t.add_column("value", justify="right")
    t.add_column("contribution", justify="right")
    t.add_column("effect")
    for c in risk.top_contributions:
        up = c.contribution > 0
        t.add_row(
            c.feature,
            f"{c.value:g}",
            Text(f"{c.contribution:+.3f}", style="red" if up else "green"),
            "raises risk" if up else "lowers risk",
        )
    return t


def features_table(commit: CommitFeatures) -> Table:
    t = Table(title="Kamei feature vector", title_justify="left",
              header_style="bold", box=None)
    values = commit.as_dict()
    for name in values:
        t.add_column(name, justify="right")
    t.add_row(*[f"{v:g}" for v in values.values()])
    return t


def review_panel(review: ReviewResult) -> Panel:
    body: list = [Text(review.summary)]

    if not review.findings:
        body.append(Text("\n✓ 0 semantic findings — the statistical flag was not "
                         "borne out by the code.", style="green"))
    else:
        t = Table(header_style="bold", expand=True, show_lines=True)
        t.add_column("#", width=3)
        t.add_column("category")
        t.add_column("location")
        t.add_column("conf", justify="right", width=6)
        t.add_column("g/f", justify="center", width=5)
        t.add_column("explanation", ratio=1)
        for i, f in enumerate(review.findings, 1):
            flags = ("[green]G[/]" if f.grounded else "[red]g[/]") + \
                    ("[green]F[/]" if f.faithful else "[red]f[/]")
            t.add_row(
                str(i), f.category, f.file_line,
                f"[{_conf_color(f.confidence)}]{f.confidence:.2f}[/]",
                flags, f.explanation,
            )
        body.append(t)
        body.append(Text("G/F = grounded / faithful; lowercase means the model "
                         "flagged its own claim as uncertain.", style="dim"))

    return Panel(Group(*body), title="[bold]LLM Semantic Review", border_style="cyan")


def render(
    commit: CommitFeatures,
    risk: RiskResult,
    review: ReviewResult | None,
    skipped_reason: str | None = None,
    show_features: bool = False,
) -> None:
    console.print()
    console.print(risk_panel(commit, risk))
    console.print(shap_table(risk))
    if show_features:
        console.print(features_table(commit))
    console.print()
    if review is not None:
        console.print(review_panel(review))
    else:
        console.print(Panel(skipped_reason or "LLM review skipped.",
                            title="[bold]LLM Semantic Review", border_style="dim"))
    console.print()


def error(msg: str) -> None:
    console.print(f"[bold red]error[/] {msg}")


if __name__ == "__main__":
    from ml_model.classifier import Contribution
    from ml_model.kamei_metrics import mock_commit
    from llm_explainer.prompts import Finding

    c = mock_commit(seed=3)
    r = RiskResult(
        score=0.87, band="HIGH", base_value=-0.4,
        top_contributions=[
            Contribution("la", 412, +0.51),
            Contribution("entropy", 0.88, +0.33),
            Contribution("exp", 1200, -0.19),
        ],
    )
    render(c, r, ReviewResult(
        summary="Statistically HIGH risk from churn, but the diff only adds null "
                "and non-positive-amount guards.",
        findings=[],
    ), show_features=True)
    render(c, r, ReviewResult(
        summary="Real defect found.",
        findings=[Finding(category="off-by-one", confidence=0.9, grounded=True,
                          faithful=False, explanation="`>=` admits expired tokens.",
                          file_line="auth/session.py:10")],
    ))
