"""The risk gate: score a commit, decide whether the LLM is worth calling.

Used by both `main.py analyze` and the TUI, so the two cannot disagree about
what "risky enough to review" means.

Process metrics need repository history, so a bare diff (a patch file, a mock
commit) cannot be scored at all. That is not the same as scoring low, and the
gate says so instead of quietly returning 0.0 and skipping the review.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import RISK_MODEL_PATH, RISK_THRESHOLD, RISK_TOP_K
from ml_model.classifier import RiskModel, RiskResult


# SHAP names a feature; a developer needs a phrase. Without this the risk half
# reports `la = 412 (+0.51)` and calls it an explanation.
FEATURE_PHRASES = {
    "ns": ("touches {v:g} subsystems", "stays inside one subsystem"),
    "nd": ("spreads across {v:g} directories", "is confined to few directories"),
    "nf": ("changes {v:g} files", "changes few files"),
    "entropy": ("scatters its changes widely", "keeps changes concentrated"),
    "la": ("adds {v:g} lines", "adds little code"),
    "ld": ("deletes {v:g} lines", "deletes little code"),
    "lt": ("edits large files", "edits small files"),
    "fix": ("is a bug fix, which historically re-introduce defects",
            "is not a bug fix"),
    "ndev": ("touches files {v:g} other developers have edited",
             "touches files with few previous authors"),
    "age": ("edits code untouched for a long time", "edits recently changed code"),
    "nuc": ("edits files with a long change history",
            "edits files that rarely change"),
    "exp": ("comes from an author with {v:g} prior commits",
            "comes from an experienced author"),
    "rexp": ("comes from an author with little recent activity",
             "comes from a recently active author"),
    "sexp": ("comes from an author new to this subsystem",
             "comes from an author familiar with this subsystem"),
}


def explain_risk(risk) -> str:
    """One sentence for why the score is what it is."""
    up = [c for c in risk.top_contributions if c.contribution > 0][:3]
    down = [c for c in risk.top_contributions if c.contribution < 0][:2]

    def phrase(c, raised: bool) -> str:
        pair = FEATURE_PHRASES.get(c.feature)
        if pair is None:
            return f"{c.feature} = {c.value:g}"
        return pair[0 if raised else 1].format(v=c.value)

    parts = []
    if up:
        parts.append("scored " + risk.band.lower() + " because it "
                     + ", and ".join(phrase(c, True) for c in up))
    if down:
        parts.append("offset by the fact that it "
                     + ", and ".join(phrase(c, False) for c in down))
    if not parts:
        return f"scored {risk.score:.0%} with no dominant driver"
    return "This commit " + "; ".join(parts) + "."


@dataclass
class GateDecision:
    risk: RiskResult | None      # None when metrics could not be mined
    should_review: bool
    reason: str

    @property
    def scored(self) -> bool:
        return self.risk is not None

    def summary(self) -> str:
        if self.risk is None:
            return self.reason
        return f"risk {self.risk.score:.1%} ({self.risk.band}) · {self.explanation}"

    @property
    def explanation(self) -> str:
        """Plain-language reason for the score, not just the feature names."""
        return explain_risk(self.risk) if self.risk else self.reason


class RiskGate:
    """Loads the model once, scores many commits."""

    def __init__(self, model_path: Path | None = None,
                 threshold: float = RISK_THRESHOLD):
        self.model_path = Path(model_path or RISK_MODEL_PATH)
        self.threshold = threshold
        self._model: RiskModel | None = None
        self._load_error: str | None = None

    @property
    def model(self) -> RiskModel | None:
        if self._model is None and self._load_error is None:
            try:
                self._model = RiskModel.load(self.model_path)
            except (FileNotFoundError, Exception) as e:
                self._load_error = str(e)
        return self._model

    def decide(self, rev: str | None, repo: str = ".", force: bool = False) -> GateDecision:
        """Score `rev` in `repo` and decide. `rev=None` means an unminable diff."""
        if rev is None:
            return GateDecision(None, True,
                                "no repository history for this diff — "
                                "risk not computed, reviewing anyway")
        if (model := self.model) is None:
            return GateDecision(None, True,
                                f"risk model unavailable ({self._load_error}) — "
                                f"reviewing anyway")
        try:
            from ml_model.kamei_metrics import from_git

            commit = from_git(rev, repo)
        except Exception as e:
            return GateDecision(None, True, f"metric mining failed ({e}) — "
                                            f"reviewing anyway")

        risk = model.score(commit, top_k=RISK_TOP_K)
        if force:
            return GateDecision(risk, True, "forced")
        if risk.score >= self.threshold:
            return GateDecision(risk, True, "above threshold")
        return GateDecision(
            risk, False,
            f"risk {risk.score:.1%} below the {self.threshold:.0%} threshold — "
            f"review skipped",
        )


if __name__ == "__main__":
    from ml_model.classifier import Contribution, RiskResult

    gate = RiskGate()
    # An unminable diff must still be reviewed, never silently dropped.
    d = gate.decide(None)
    assert d.should_review and not d.scored, d
    # Forcing must review regardless of score.
    assert gate.decide(None, force=True).should_review

    risk = RiskResult(0.91, "HIGH", [
        Contribution("la", 412, +1.2),
        Contribution("exp", 4, +0.8),
        Contribution("nf", 18, +0.4),
        Contribution("age", 300, -0.5),
    ])
    text = explain_risk(risk)
    assert "412" in text and "prior commits" in text and "offset" in text, text
    assert not any(f" {name} =" in text for name in ("la", "exp", "nf")), \
        "explanation must not leak raw feature names"
    print("gate:", d.reason)
    print("explain:", text)
    print("model:", gate.model_path,
          "loaded" if gate.model is not None else "unavailable")
