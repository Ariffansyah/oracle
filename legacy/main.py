#!/usr/bin/env python3
"""ORACLE - hybrid JIT defect prediction + LLM explainability.

    python main.py analyze --commit HEAD --repo /path/to/repo
    python main.py analyze --mock            # no repo, no Ollama needed
    python main.py train                     # (re)fit the XGBoost risk model
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import config
from ml_model import kamei_metrics
from ml_model.classifier import RiskModel, train
from ui import terminal_display as ui


def _load_commit(args) -> kamei_metrics.CommitFeatures:
    if args.mock:
        return kamei_metrics.mock_commit(seed=args.seed, risky=not args.safe)
    if args.diff_file:
        text = Path(args.diff_file).read_text()
        commit = kamei_metrics.mock_commit(seed=args.seed)
        commit.diff = text
        commit.subject = f"(diff from {args.diff_file})"
        # ponytail: metrics stay mocked for a bare diff file - process metrics
        # need history. Point --repo/--commit at a git repo for real ones.
        return commit
    return kamei_metrics.from_git(args.commit, args.repo)


def _log_review(path: Path, commit, risk, review) -> None:
    """Append the run in the exact shape `dpo_pipeline/dataset_builder.py` reads.

    `label` starts as "unlabelled"; set it to "false_positive" (and keep
    model_review) or "true_positive" (and add a human_review) to make the record
    usable as a preference pair.
    """
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps({
            "rev": commit.rev,
            "diff": commit.diff,
            "risk_score": risk.score,
            "risk_band": risk.band,
            "contributions": [str(c) for c in risk.drivers],
            "subject": commit.subject,
            "files": commit.files,
            "label": "unlabelled",
            "model_review": review.model_dump(),
        }) + "\n")
    ui.console.print(f"[dim]logged review -> {path}[/]")


def cmd_analyze(args) -> int:
    commit = _load_commit(args)
    model = RiskModel.load(args.model)
    risk = model.score(commit)

    review, skipped = None, None
    if risk.score < args.threshold:
        skipped = (f"Risk {risk.score:.1%} is below the {args.threshold:.0%} threshold "
                   f"— LLM review skipped. Force it with --always-explain.")
    if risk.score >= args.threshold or args.always_explain:
        from llm_explainer.client import LLMError, OllamaClient

        client = OllamaClient(model=args.llm_model)
        try:
            review = client.review(
                diff=commit.diff,
                risk_score=risk.score,
                risk_band=risk.band,
                contributions=[str(c) for c in risk.drivers],
                subject=commit.subject,
                files=commit.files,
            )
            skipped = None
        except LLMError as e:
            skipped = f"LLM review unavailable: {e}"

    if args.log and review is not None:
        _log_review(args.log, commit, risk, review)

    ui.render(commit, risk, review, skipped, show_features=args.features)
    if args.json:
        import json

        print(json.dumps({
            "rev": commit.rev,
            "risk_score": risk.score,
            "risk_band": risk.band,
            "features": commit.as_dict(),
            "shap": [{"feature": c.feature, "value": c.value,
                      "contribution": c.contribution} for c in risk.top_contributions],
            "review": review.model_dump() if review else None,
        }, indent=2))
    return 0


def cmd_tui(args) -> int:
    from ui.app import run

    run(_load_commit(args), model_path=args.model, llm_model=args.llm_model,
        auto_explain=args.explain)
    return 0


def cmd_train(args) -> int:
    if args.synthetic:
        train(path=args.model, seed=args.seed)
        print(f"model trained on the synthetic stand-in -> {args.model}")
        return 0

    from ml_model.apachejit import DEFAULT_CSV, main as apachejit_main

    csv_path = args.apachejit or DEFAULT_CSV
    argv = ["--csv", str(csv_path), "--out", str(args.model)]
    if not Path(csv_path).exists():
        argv.append("--download")
    apachejit_main(argv)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="oracle", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="score a commit and explain it")
    a.add_argument("--commit", default="HEAD", help="git revision (default HEAD)")
    a.add_argument("--repo", default=".", help="repository path (default cwd)")
    a.add_argument("--diff-file", help="analyze a unified diff from a file instead")
    a.add_argument("--mock", action="store_true", help="use the built-in demo commit")
    a.add_argument("--safe", action="store_true", help="with --mock, generate a low-risk commit")
    a.add_argument("--threshold", type=float, default=config.RISK_THRESHOLD)
    a.add_argument("--always-explain", action="store_true",
                   help="run the LLM even below the risk threshold")
    a.add_argument("--llm-model", default=config.OLLAMA_MODEL)
    a.add_argument("--features", action="store_true", help="print the full Kamei vector")
    a.add_argument("--json", action="store_true", help="also dump machine-readable JSON")
    a.add_argument("--log", type=Path, nargs="?", const=Path("data/reviews.jsonl"),
                   help="append this review to a corpus for DPO labelling "
                        "(default data/reviews.jsonl)")
    a.set_defaults(func=cmd_analyze)

    u = sub.add_parser("tui", help="interactive review dashboard")
    u.add_argument("--commit", default="HEAD")
    u.add_argument("--repo", default=".")
    u.add_argument("--diff-file")
    u.add_argument("--mock", action="store_true")
    u.add_argument("--safe", action="store_true")
    u.add_argument("--llm-model", default=config.OLLAMA_MODEL)
    u.add_argument("--explain", action="store_true", help="query the LLM on startup")
    u.set_defaults(func=cmd_tui)

    t = sub.add_parser("train", help="fit the XGBoost risk model on ApacheJIT")
    t.add_argument("--apachejit", type=Path, help="path to apachejit_total.csv "
                                                  "(downloaded if missing)")
    t.add_argument("--synthetic", action="store_true",
                   help="use the synthetic stand-in instead of real data")
    t.set_defaults(func=cmd_train)

    for p in (a, u, t):
        p.add_argument("--model", type=Path, default=config.MODEL_PATH)
        p.add_argument("--seed", type=int, default=0)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, FileNotFoundError) as e:
        ui.error(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
