"""Build the DPO preference set from historical commits + false-positive labels.

Input: a JSONL of review records, one per commit:

    {"diff": "...", "risk_score": 0.83, "risk_band": "HIGH",
     "contributions": ["la = 400 (+0.42)"], "subject": "...",
     "files": ["a.py"],
     "label": "false_positive" | "true_positive",
     "model_review": {...ReviewResult the LLM produced...},
     "human_review": {...ReviewResult a reviewer signed off on...}}

Output: `{"prompt", "chosen", "rejected"}` triples.

* `false_positive` -> chosen is the *empty-findings* review (with the summary
  saying the statistical flag was not borne out); rejected is what the model
  hallucinated.
* `true_positive`  -> chosen is the human review; rejected is a degraded copy
  (dropped findings / risk-score parroting), teaching the model not to miss real
  defects and not to justify the score instead of the code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run as a script

from config import DPO_DATASET_PATH
from llm_explainer.prompts import SYSTEM_PROMPT, ReviewResult, build_prompt

_NO_FINDING_SUMMARY = (
    "The statistical model scored this commit {band} ({score:.2f}) on process metrics "
    "such as {driver}, but semantic review of the diff shows standard, safe code. "
    "No defects found."
)
_PARROT_SUMMARY = (
    "The risk score of {score:.2f} is {band}, so this commit is dangerous and likely "
    "introduces a defect."
)


def _prompt(rec: dict) -> str:
    return SYSTEM_PROMPT + "\n\n" + build_prompt(
        diff=rec["diff"],
        risk_score=rec["risk_score"],
        risk_band=rec.get("risk_band", "HIGH"),
        contributions=rec.get("contributions", []),
        subject=rec.get("subject", ""),
        files=rec.get("files"),
    )


def _json(review: ReviewResult | dict) -> str:
    if isinstance(review, dict):
        review = ReviewResult.model_validate(review)
    return review.model_dump_json(indent=2)


def build_pair(rec: dict) -> dict | None:
    """Turn one labelled record into a preference triple (or None if unusable)."""
    if rec.get("label") not in ("false_positive", "true_positive"):
        return None  # still awaiting a human label
    driver = (rec.get("contributions") or ["churn"])[0]
    score, band = rec["risk_score"], rec.get("risk_band", "HIGH")

    if rec["label"] == "false_positive":
        rejected = rec.get("model_review")
        if not rejected or not rejected.get("findings"):
            return None  # nothing to prefer against
        chosen = ReviewResult(
            summary=_NO_FINDING_SUMMARY.format(band=band, score=score, driver=driver)
        )
    else:
        human = rec.get("human_review")
        if not human or not human.get("findings"):
            return None
        chosen = ReviewResult.model_validate(human)
        # Rejected: parrots the risk score and reports nothing concrete.
        rejected = ReviewResult(
            summary=_PARROT_SUMMARY.format(score=score, band=band)
        ).model_dump()

    return {
        "prompt": _prompt(rec),
        "chosen": _json(chosen),
        "rejected": _json(rejected),
    }


def build(records: list[dict]) -> list[dict]:
    return [p for p in (build_pair(r) for r in records) if p]


def load_records(path: Path) -> list[dict]:
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_jsonl(pairs: list[dict], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        for pair in pairs:
            fh.write(json.dumps(pair) + "\n")
    return path


def mock_records() -> list[dict]:
    """Two labelled records - one false positive, one real defect."""
    from ml_model.kamei_metrics import MOCK_DIFF

    return [
        {
            "diff": MOCK_DIFF,
            "risk_score": 0.87,
            "risk_band": "HIGH",
            "contributions": ["la = 412 (+0.51)", "entropy = 0.88 (+0.33)"],
            "subject": "refactor: name locals consistently and document helpers",
            "files": ["payments/checkout.py", "payments/receipt.py"],
            "label": "false_positive",
            "model_review": {
                "summary": "High risk score; the payment path looks dangerous.",
                "findings": [{
                    "category": "logic-error",
                    "confidence": 0.6,
                    "grounded": True,
                    "faithful": True,
                    "explanation": "The discount calculation may be wrong because "
                                   "the commit is large and touches payments.",
                    "file_line": "payments/checkout.py:48",
                }],
            },
        },
        {
            "diff": (
                "diff --git a/auth/session.py b/auth/session.py\n"
                "@@ -8,3 +8,3 @@\n"
                "-    if token.expires_at > now():\n"
                "+    if token.expires_at >= now():\n"
                "         return token.user\n"
            ),
            "risk_score": 0.34,
            "risk_band": "LOW",
            "contributions": ["la = 1 (+0.02)"],
            "subject": "fix: session expiry boundary",
            "files": ["auth/session.py"],
            "label": "true_positive",
            "human_review": {
                "summary": "Low statistical risk, but the one-line change accepts "
                           "tokens at the exact expiry instant.",
                "findings": [{
                    "category": "off-by-one",
                    "confidence": 0.9,
                    "grounded": True,
                    "faithful": True,
                    "explanation": "Changing `>` to `>=` makes a token valid at "
                                   "exactly expires_at, extending every session by "
                                   "one tick past expiry.",
                    "file_line": "auth/session.py:10",
                }],
            },
        },
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the ORACLE DPO preference set.")
    ap.add_argument("--input", type=Path, help="labelled review records (JSONL)")
    ap.add_argument("--output", type=Path, default=Path(DPO_DATASET_PATH))
    args = ap.parse_args()

    if args.input:
        records = load_records(args.input)
    else:
        print("no --input given, using built-in demo records")
        records = mock_records()

    pairs = build(records)
    out = write_jsonl(pairs, args.output)
    print(f"wrote {len(pairs)} preference pairs -> {out}")


def _selftest() -> None:
    demo = build(mock_records())
    assert len(demo) == 2, demo
    for pair in demo:
        assert pair["chosen"] != pair["rejected"]
        assert set(pair) == {"prompt", "chosen", "rejected"}
    assert json.loads(demo[0]["chosen"])["findings"] == [], "false positive must prefer 0 findings"
    assert json.loads(demo[1]["chosen"])["findings"], "true positive must keep the real finding"


if __name__ == "__main__":
    _selftest()
    main()
