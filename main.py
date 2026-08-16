#!/usr/bin/env python3
"""ORACLE — end-to-end instruction-tuned JIT defect reviewer.

    python main.py build-sft --mock          # SFT dataset
    python main.py build-dpo --mock          # preference pairs
    python main.py train-sft                 # stage 1: QLoRA SFT
    python main.py train-dpo --merge         # stage 2: DPO, then merge
    python main.py analyze --diff-file x.patch
    python main.py tui --repo /path/to/repo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import config


def cmd_build_sft(args) -> int:
    from dataset_builder.build_sft_data import main as build

    argv = ["--out", str(args.out)]
    if args.mock:
        argv += ["--mock", "--n", str(args.n)]
    elif args.jsonl:
        argv += ["--jsonl", str(args.jsonl)]
    elif args.csv:
        argv += ["--csv", str(args.csv)]
    build(argv)
    return 0


def cmd_build_dpo(args) -> int:
    from dpo_pipeline.build_dpo_data import main as build

    argv = ["--out", str(args.out)]
    if args.reviews:
        argv += ["--reviews", str(args.reviews)]
    else:
        argv += ["--mock", "--n", str(args.n)]
    build(argv)
    return 0


def cmd_train_sft(args) -> int:
    from fine_tuning.train_sft import main as train

    train(args.extra)
    return 0


def cmd_train_dpo(args) -> int:
    from fine_tuning.train_dpo import main as train

    train((["--merge"] if args.merge else []) + args.extra)
    return 0


def _run_gate(console, diff: str, commit_id: str | None, force: bool):
    """Stage 1. Returns (decision, ok) - ok is False when no gate is trained."""
    from ml_model.gate import Gatekeeper

    try:
        gate = Gatekeeper.load()
    except FileNotFoundError as e:
        console.print(f"[dim]stage 1 skipped: {e.args[0].splitlines()[0]}[/]")
        return None, False

    metrics = None
    if commit_id:
        import numpy as np

        from corpus.apachejit import load_rows, row_values
        from corpus.kamei_metrics import KAMEI_FEATURES
        from config import ROOT

        csv = ROOT / "data" / "apachejit_total.csv"
        if csv.exists():
            src = {r["commit_id"]: r for r in load_rows(csv)}.get(commit_id)
            if src:
                v = row_values(src)
                metrics = np.array([v[k] for k in KAMEI_FEATURES], dtype="float32")
    return gate.decide(diff, metrics, force=force), True


def cmd_analyze(args) -> int:
    from llm_explainer.client import InferenceError, OracleClient
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()

    # --- gather the diff ---------------------------------------------------
    if args.commit:
        from ui.tui_app import git_diff

        diff, subject = git_diff(args.repo, args.commit), args.commit
    elif args.diff_file:
        diff, subject = Path(args.diff_file).read_text(), str(args.diff_file)
    else:
        from dataset_builder.mock_data import DEFECT_TEMPLATES

        diff, subject = DEFECT_TEMPLATES[0][0].format(n=8), "(mock commit)"

    # --- stage 1: gatekeeper ------------------------------------------------
    decision = None
    if not args.no_gate:
        decision, ok = _run_gate(console, diff, args.commit, args.always_review)
        if ok and decision is not None:
            colour = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}[decision.band]
            console.print(Panel(
                f"[bold {colour}]{decision.score:.1%} {decision.band}[/]  "
                f"(gate at {decision.threshold:.1%})\n{decision.reason}",
                title="ORACLE · stage 1 · deep-learning gatekeeper",
                border_style=colour))
            if not decision.should_review:
                console.print("[green]✓ clean — no LLM call made.[/] "
                              "[dim]--always-review overrides.[/]")
                if args.json:
                    print(json.dumps({"risk_score": decision.score,
                                      "risk_band": decision.band,
                                      "reviewed": False, "analysis": None},
                                     indent=2))
                return 0

    # --- stage 2: fine-tuned semantic validator -----------------------------
    client = OracleClient(model_path=args.model, backend=args.backend)
    try:
        if args.commit:
            analysis = client.analyze_commit(
                args.repo, args.commit, with_context=not args.no_context,
                progress=lambda i, n, p: console.print(
                    f"[dim]  file {i}/{n}  {p}[/]"))
        else:
            analysis = client.analyze(diff, subject=subject)
    except InferenceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return _render(console, analysis, args.json, decision)


def _render(console, analysis, as_json: bool, decision=None) -> int:
    from rich.panel import Panel
    from rich.table import Table

    if as_json:
        print(json.dumps({
            "risk_score": decision.score if decision else None,
            "risk_band": decision.band if decision else None,
            "reviewed": True,
            "analysis": analysis.model_dump(),
        }, indent=2))
        return 0

    console.print(Panel(analysis.summary,
                        title="ORACLE · stage 2 · semantic validator",
                        border_style="cyan"))
    if not analysis.findings:
        console.print("[green]✓ no defects found[/]")
        return 0
    table = Table(show_lines=True)
    table.add_column("#", width=3)
    table.add_column("category")
    table.add_column("file")
    table.add_column("explanation", ratio=1)
    for i, f in enumerate(analysis.findings, 1):
        table.add_row(str(i), f.category, f.file or "-", f.explanation)
    console.print(table)
    return 0


def cmd_tui(args) -> int:
    from ui.tui_app import run

    run(repo=None if args.mock else args.repo, model_path=args.model,
        backend=args.backend, limit=args.limit, with_gate=not args.no_gate)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="oracle", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    b1 = sub.add_parser("build-sft", help="build the SFT dataset")
    b1.add_argument("--csv", type=Path, help="commits CSV (hash, diff, label)")
    b1.add_argument("--jsonl", type=Path, help="fetched commit records")
    b1.add_argument("--mock", action="store_true")
    b1.add_argument("--n", type=int, default=60)
    b1.add_argument("--out", type=Path, default=Path(config.SFT_DATASET))
    b1.set_defaults(func=cmd_build_sft)

    b2 = sub.add_parser("build-dpo", help="build preference pairs")
    b2.add_argument("--reviews", type=Path, help="logged reviews with corrections")
    b2.add_argument("--mock", action="store_true")
    b2.add_argument("--n", type=int, default=40)
    b2.add_argument("--out", type=Path, default=Path(config.DPO_DATASET))
    b2.set_defaults(func=cmd_build_dpo)

    t1 = sub.add_parser("train-sft", help="stage 1: QLoRA supervised fine-tune")
    t1.add_argument("extra", nargs="*", help="passed through to the trainer")
    t1.set_defaults(func=cmd_train_sft)

    t2 = sub.add_parser("train-dpo", help="stage 2: preference alignment")
    t2.add_argument("--merge", action="store_true", help="merge adapter when done")
    t2.add_argument("extra", nargs="*", help="passed through to the trainer")
    t2.set_defaults(func=cmd_train_dpo)

    a = sub.add_parser("analyze", help="review one diff")
    a.add_argument("--diff-file", type=Path)
    a.add_argument("--commit", help="git revision to review")
    a.add_argument("--repo", default=".")
    a.add_argument("--json", action="store_true")
    a.add_argument("--no-context", action="store_true",
                   help="review the bare diff, without surrounding file context")
    a.add_argument("--no-gate", action="store_true",
                   help="skip stage 1 and always run the validator")
    a.add_argument("--always-review", action="store_true",
                   help="run stage 2 even when the gate says clean")
    a.set_defaults(func=cmd_analyze)

    u = sub.add_parser("tui", help="three-pane review UI")
    u.add_argument("--repo", default=".")
    u.add_argument("--mock", action="store_true", help="demo commits, no repo")
    u.add_argument("--limit", type=int, default=50)
    u.add_argument("--no-gate", action="store_true",
                   help="skip stage 1 entirely")
    u.set_defaults(func=cmd_tui)

    for p in (a, u):
        p.add_argument("--model", type=Path, default=None,
                       help=f"model dir (default {config.MERGED_MODEL_DIR})")
        p.add_argument("--backend", choices=("auto", "transformers", "ollama"),
                       default=config.BACKEND,
                       help="auto prefers the trained model when it exists")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
