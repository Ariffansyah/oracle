"""Does the statistical prior change what the LLM reviewer does?

Three conditions on the same real ApacheJIT commits, scored against the SZZ
`buggy` label:

  hybrid   diff + risk score + SHAP drivers   (what ORACLE ships)
  llm      diff only, no prior                (ablation)
  ml       risk score thresholded, no LLM     (the classifier alone)

    python experiment_baseline.py --n 24
    python experiment_baseline.py --n 24 --resume        # continue a killed run

Read the caveats in `interpret()` before quoting any of these numbers. The label
is SZZ-derived: `buggy=True` means a later fix touched lines this commit
introduced, which is not the same as "this diff visibly contains a defect", and
a reviewer can be right while disagreeing with it.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

import config
from llm_explainer.client import LLMError, OllamaClient

console = Console()
COMMITS = config.ROOT / "data" / "apachejit_commits.jsonl"
RESULTS = config.ROOT / "data" / "baseline_results.jsonl"


def confusion(pairs: list[tuple[bool, bool]]) -> dict:
    """pairs of (predicted_defective, actually_buggy) -> the usual metrics."""
    tp = sum(1 for p, a in pairs if p and a)
    fp = sum(1 for p, a in pairs if p and not a)
    fn = sum(1 for p, a in pairs if not p and a)
    tn = sum(1 for p, a in pairs if not p and not a)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1,
        "accuracy": (tp + tn) / len(pairs) if pairs else 0.0,
        "flag_rate": (tp + fp) / len(pairs) if pairs else 0.0,
    }


def run_condition(client: OllamaClient, rec: dict, include_risk: bool) -> dict:
    started = time.time()
    try:
        review = client.review(
            diff=rec["diff"],
            risk_score=rec["risk_score"],
            risk_band=rec["risk_band"],
            contributions=rec["contributions"],
            subject=rec["subject"],
            files=rec["files"],
            include_risk=include_risk,
        )
    except LLMError as e:
        return {"error": str(e), "seconds": time.time() - started}
    return {
        "n_findings": len(review.findings),
        "categories": [f.category for f in review.findings],
        "max_confidence": max((f.confidence for f in review.findings), default=0.0),
        "grounded_all": all(f.grounded for f in review.findings),
        "summary": review.summary,
        "seconds": time.time() - started,
    }


def load_done(path: Path) -> dict:
    if not path.exists():
        return {}
    out = {}
    with open(path) as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                out[(r["commit_id"], r["condition"])] = r
    return out


def interpret(rows: list[dict], threshold: float) -> None:
    hybrid = [(r["hybrid"]["n_findings"] > 0, r["buggy"]) for r in rows]
    llm = [(r["llm"]["n_findings"] > 0, r["buggy"]) for r in rows]
    ml = [(r["risk_score"] >= threshold, r["buggy"]) for r in rows]

    table = Table(title=f"baseline comparison — n={len(rows)} real ApacheJIT commits",
                  title_justify="left")
    table.add_column("condition")
    for col in ("TP", "FP", "FN", "TN", "precision", "recall", "F1", "flag rate"):
        table.add_column(col, justify="right")

    for name, pairs in (("hybrid (diff+risk+SHAP)", hybrid),
                        ("llm (diff only)", llm),
                        (f"ml (risk >= {threshold})", ml)):
        m = confusion(pairs)
        table.add_row(
            name, str(m["tp"]), str(m["fp"]), str(m["fn"]), str(m["tn"]),
            f"{m['precision']:.2f}", f"{m['recall']:.2f}", f"{m['f1']:.2f}",
            f"{m['flag_rate']:.0%}",
        )
    console.print(table)

    base = sum(r["buggy"] for r in rows) / len(rows)
    agree = sum(1 for h, l in zip(hybrid, llm) if h[0] == l[0])
    console.print(f"base rate (buggy): {base:.0%}")
    console.print(f"hybrid vs llm agreement: {agree}/{len(rows)} "
                  f"({agree / len(rows):.0%}) — the prior only matters where these differ")

    flipped = [r for r in rows
               if (r["hybrid"]["n_findings"] > 0) != (r["llm"]["n_findings"] > 0)]
    for r in flipped[:8]:
        h, l = r["hybrid"]["n_findings"], r["llm"]["n_findings"]
        console.print(f"  [dim]{r['commit_id'][:8]} buggy={r['buggy']} "
                      f"risk={r['risk_score']:.2f}: hybrid {h} findings, llm {l}[/]")

    console.print(
        "\n[yellow]caveats[/]: SZZ labels are noisy — `buggy=True` means a later fix "
        "touched lines this commit introduced, not that the defect is visible in this "
        "diff. The reviewer can be right and still disagree with the label. "
        "The risk scores also leak: these commits were in the classifier's training "
        "set, so the `ml` row is optimistic."
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commits", type=Path, default=COMMITS)
    ap.add_argument("--results", type=Path, default=RESULTS)
    ap.add_argument("--n", type=int, default=24, help="commits to evaluate")
    ap.add_argument("--llm-model", default=config.OLLAMA_MODEL)
    ap.add_argument("--threshold", type=float, default=config.RISK_THRESHOLD)
    ap.add_argument("--max-diff-bytes", type=int, default=8000,
                    help="keep latency sane; long diffs dominate the runtime")
    ap.add_argument("--report-only", action="store_true",
                    help="re-print from cached results, run nothing")
    args = ap.parse_args(argv)

    if not args.commits.exists():
        raise SystemExit(
            f"{args.commits} not found — fetch some first:\n"
            f"  python dpo_pipeline/fetch_apachejit.py --limit 200"
        )

    records = [json.loads(l) for l in open(args.commits) if l.strip()]
    records = [r for r in records if len(r["diff"]) <= args.max_diff_bytes]
    # Balance the sample so precision and recall are both measurable.
    buggy = [r for r in records if r["buggy"]][: args.n // 2]
    clean = [r for r in records if not r["buggy"]][: args.n - len(buggy)]
    chosen = buggy + clean
    if len(chosen) < 4:
        raise SystemExit(f"only {len(chosen)} usable commits — fetch more")

    done = load_done(args.results)
    client = OllamaClient(model=args.llm_model)

    if not args.report_only:
        args.results.parent.mkdir(parents=True, exist_ok=True)
        # Retry cached errors: a timeout is not a result, and skipping it would
        # silently drop the commit from the comparison.
        todo = [(r, c) for r in chosen for c in ("hybrid", "llm")
                if "error" in done.get((r["commit_id"], c), {"error": 1})]
        console.print(f"{len(chosen)} commits × 2 conditions, {len(todo)} calls to make")
        started = time.time()
        with open(args.results, "a") as out:
            for i, (rec, cond) in enumerate(todo, 1):
                result = run_condition(client, rec, include_risk=(cond == "hybrid"))
                row = {"commit_id": rec["commit_id"], "condition": cond,
                       "buggy": rec["buggy"], "risk_score": rec["risk_score"], **result}
                out.write(json.dumps(row) + "\n")
                out.flush()
                done[(rec["commit_id"], cond)] = row
                mark = "!" if "error" in result else str(result.get("n_findings"))
                console.print(
                    f"[dim]{i}/{len(todo)} {rec['commit_id'][:8]} {cond:6s} "
                    f"findings={mark} ({result['seconds']:.0f}s, "
                    f"{(time.time() - started) / 60:.0f}m elapsed)[/]"
                )

    rows = []
    for rec in chosen:
        h = done.get((rec["commit_id"], "hybrid"))
        l = done.get((rec["commit_id"], "llm"))
        if not h or not l or "error" in h or "error" in l:
            continue
        rows.append({"commit_id": rec["commit_id"], "buggy": rec["buggy"],
                     "risk_score": rec["risk_score"], "hybrid": h, "llm": l})

    if not rows:
        console.print("[red]no complete pairs to report[/]")
        return 1
    interpret(rows, args.threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
