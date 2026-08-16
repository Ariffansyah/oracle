"""Turn raw commits into conversational JSONL for supervised fine-tuning.

Input CSV needs `hash`, `diff`, `label` (label: 1/0, true/false, buggy/clean).
ApacheJIT-style CSVs are accepted too - `commit_id` and `buggy` are recognised.

    python -m dataset_builder.build_sft_data --mock            # 60 synthetic commits
    python -m dataset_builder.build_sft_data --csv data/commits.csv

Output is the HuggingFace conversational format TRL's SFTTrainer reads directly:

    {"messages": [
        {"role": "system",    "content": "..."},
        {"role": "user",      "content": "...diff..."},
        {"role": "assistant", "content": "{\\"summary\\": ..., \\"findings\\": [...]}"}]}

The assistant turn is always a serialised `Analysis`, so the model is trained on
exactly the JSON the inference client parses.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import MAX_DIFF_CHARS, RAW_COMMITS_CSV, SFT_DATASET
from dataset_builder.mock_data import DEFECT_TEMPLATES, SAFE_TEMPLATES, mock_commits
from dataset_builder.schema import (SYSTEM_PROMPT, Analysis, Finding,
                                    build_user_message)

_TRUE = {"1", "true", "yes", "buggy", "defective", "y"}


def _is_buggy(row: dict) -> bool:
    raw = row.get("label", row.get("buggy", ""))
    return str(raw).strip().lower() in _TRUE


def _commit_id(row: dict) -> str:
    return row.get("hash") or row.get("commit_id") or ""


def to_example(diff: str, buggy: bool, analysis: Analysis | None = None,
               subject: str = "", files: str = "", context: str = "") -> dict:
    """One (system, user, assistant) conversation.

    `context` is the surrounding-code block. Training with it means the model
    learns to *use* the wider file, and matches what the inference client sends.
    """
    if analysis is None:
        # No per-commit annotation available: fall back to the label alone.
        # ponytail: label-only targets teach the verdict, not the reasoning.
        # Distil real explanations from a teacher model for anything serious.
        analysis = Analysis(
            summary=("This change introduces a defect." if buggy else
                     "This change is behaviour-preserving; no defect found."),
            findings=[Finding(category="other",
                              explanation="A later fix touched lines this commit "
                                          "introduced.")] if buggy else [],
        )
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(
                diff, subject, files, max_diff_chars=MAX_DIFF_CHARS,
                context=context, include_schema=False)},
            {"role": "assistant", "content": analysis.to_json()},
        ]
    }


def from_csv(path: Path) -> list[dict]:
    rows = list(csv.DictReader(open(path)))
    if not rows:
        raise SystemExit(f"{path} is empty")
    if "diff" not in rows[0]:
        raise SystemExit(
            f"{path} has no `diff` column — ORACLE trains on code, not metrics. "
            f"Columns found: {', '.join(rows[0])}"
        )
    out = []
    for row in rows:
        diff = row["diff"]
        if not diff.strip():
            continue
        out.append(to_example(
            diff, _is_buggy(row),
            subject=row.get("subject", ""),
            files=row.get("files", ""),
            # An expanded diff (`git diff -U50`) or file body, when the corpus
            # carries one; the column is optional.
            context=row.get("context", "") or row.get("file_context", ""),
        ))
    return out


def from_jsonl(path: Path) -> list[dict]:
    """Records written by a fetcher: {diff, buggy, subject, files, analysis?}."""
    out = []
    with open(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            if not rec.get("diff"):
                continue
            analysis = (Analysis.model_validate(rec["analysis"])
                        if rec.get("analysis") else None)
            out.append(to_example(
                rec["diff"], bool(rec.get("buggy")), analysis,
                subject=rec.get("subject", ""),
                files=", ".join(rec.get("files", [])),
                context=rec.get("context", ""),
            ))
    return out


def build_mock(n: int = 60, seed: int = 0) -> list[dict]:
    """Synthetic commits with *real* annotations, so the pipeline is trainable
    and testable before any teacher labelling exists."""
    rng = random.Random(seed)
    out = []
    for diff, analysis in mock_commits(n, rng):
        out.append(to_example(diff, bool(analysis.findings), analysis,
                              subject="(mock commit)", files="mock.py"))
    return out


def distinct_targets(rows: list[dict]) -> tuple[int, str, int]:
    """How many distinct assistant turns, and the most repeated one.

    `sft-cve` was trained on a file where half the targets were byte-identical.
    Memorising that one string drove the loss near zero, training looked healthy,
    and the model emitted exactly one output for all 1000 eval records — ten GPU
    hours for a null result visible in the data. Never write an SFT file without
    looking at this number.
    """
    turns = Counter(m["content"] for r in rows for m in r["messages"]
                    if m["role"] == "assistant")
    top, n = turns.most_common(1)[0] if turns else ("", 0)
    return len(turns), top, n


def write_jsonl(rows: list[dict], path: Path) -> Path:
    distinct, top, n = distinct_targets(rows)
    share = n / max(len(rows), 1)
    print(f"  {distinct} distinct assistant turns in {len(rows)} rows; "
          f"most repeated {share:.0%} ({n}x)")
    if share >= 0.2:
        print(f"  !!! {share:.0%} of targets are one string — training on this "
              f"collapses the model. Vary the target before you spend the GPU:\n"
              f"      {top[:160]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, help="commits CSV (hash, diff, label)")
    ap.add_argument("--jsonl", type=Path, help="fetched commit records instead")
    ap.add_argument("--out", type=Path, default=Path(SFT_DATASET))
    ap.add_argument("--mock", action="store_true", help="generate synthetic commits")
    ap.add_argument("--n", type=int, default=60, help="how many, with --mock")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    if args.mock:
        rows = build_mock(args.n, args.seed)
    elif args.jsonl:
        rows = from_jsonl(args.jsonl)
    else:
        csv_path = args.csv or Path(RAW_COMMITS_CSV)
        if not csv_path.exists():
            raise SystemExit(
                f"{csv_path} not found. Use --mock to generate synthetic data, "
                f"--csv <file>, or --jsonl <fetched records>."
            )
        rows = from_csv(csv_path)

    out = write_jsonl(rows, args.out)
    defective = sum(
        1 for r in rows if json.loads(r["messages"][-1]["content"])["findings"]
    )
    print(f"{len(rows)} SFT examples -> {out}  "
          f"({defective} with findings, {len(rows) - defective} clean)")


def _selftest() -> None:
    rows = build_mock(12, seed=1)
    assert len(rows) == 12
    for r in rows:
        assert [m["role"] for m in r["messages"]] == ["system", "user", "assistant"]
        Analysis.model_validate_json(r["messages"][-1]["content"])  # must parse
    kinds = {json.loads(r["messages"][-1]["content"])["findings"] == [] for r in rows}
    assert kinds == {True, False}, "mock set must contain both clean and defective"
    assert len(SAFE_TEMPLATES) and len(DEFECT_TEMPLATES)


if __name__ == "__main__":
    _selftest()
    main()
