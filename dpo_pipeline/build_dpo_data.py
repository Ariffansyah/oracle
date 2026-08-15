"""Preference pairs that teach the model to stay quiet on safe code.

After SFT the model answers in the right shape but over-reports: given churn, a
rename or an added guard it manufactures a plausible-sounding defect. DPO fixes
behaviour, and the behaviour to fix is exactly that.

    python -m dpo_pipeline.build_dpo_data --mock
    python -m dpo_pipeline.build_dpo_data --reviews data/reviews.jsonl

Two pair sources:

  safe commits    chosen   = empty findings, summary saying so
                  rejected = a pedantic, hallucinated finding

  logged reviews  chosen   = the human-corrected analysis
                  rejected = what the model actually said

`prompt` is the same system+user text the model sees at inference, so the
preference is learnt on the real input distribution.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DPO_DATASET, MAX_DIFF_CHARS
from dataset_builder.mock_data import SAFE_SUMMARIES, SAFE_TEMPLATES, mock_commits
from dataset_builder.schema import (SYSTEM_PROMPT, Analysis, Finding,
                                    build_user_message)

# What an over-eager reviewer invents on perfectly safe code. Each is plausible,
# which is the point: the model must learn to reject its own best guess.
HALLUCINATIONS = [
    ("logic-error",
     "The renamed local may shadow an outer variable, which could change which "
     "value is returned."),
    ("input-validation",
     "The function does not validate its input, so malformed data could reach "
     "the formatting logic and corrupt the output."),
    ("error-handling",
     "No exception handling was added around the new code, so an unexpected "
     "failure here would propagate to the caller."),
    ("api-misuse",
     "The added type hint suggests a contract that callers may not honour, "
     "which could cause a runtime type error."),
    ("resource-leak",
     "The loop accumulates into a list without an explicit bound, which could "
     "grow without limit for large inputs."),
    ("concurrency",
     "This code is not synchronised, so concurrent callers could interleave and "
     "observe an inconsistent intermediate state."),
]


def _prompt(diff: str, subject: str = "", files: str = "",
            context: str = "") -> str:
    return (SYSTEM_PROMPT + "\n\n"
            + build_user_message(diff, subject, files,
                                 max_diff_chars=MAX_DIFF_CHARS, context=context,
                                 include_schema=False))


def pair(diff: str, chosen: Analysis, rejected: Analysis,
         subject: str = "", files: str = "", context: str = "") -> dict:
    return {
        "prompt": _prompt(diff, subject, files, context),
        "chosen": chosen.to_json(),
        "rejected": rejected.to_json(),
    }


def build_frontend_pairs(repeat: int = 4) -> list[dict]:
    """Security boilerplate the base model calls a bug.

    These carry the most signal per pair in the whole set: the chosen and
    rejected answers describe the same few lines, so they sit in exactly the
    small-edit-distance regime DPO-Positive exists to handle.
    """
    from dpo_pipeline.frontend_cases import turnstile_pairs

    out = []
    for _ in range(repeat):
        for subject, files, diff, chosen, rejected, context in turnstile_pairs():
            out.append(pair(diff, chosen=chosen, rejected=rejected,
                            subject=subject, files=files, context=context))
    return out


def build_mock(n: int = 40, seed: int = 0) -> list[dict]:
    """Safe diffs paired against invented findings."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        idx = rng.randrange(len(SAFE_TEMPLATES))
        diff = SAFE_TEMPLATES[idx].format(n=rng.randint(5, 200))
        category, explanation = rng.choice(HALLUCINATIONS)
        out.append(pair(
            diff,
            chosen=Analysis(summary=SAFE_SUMMARIES[idx], findings=[]),
            rejected=Analysis(
                summary="This change is risky and likely introduces a defect.",
                findings=[Finding(category=category, explanation=explanation)],
            ),
            subject="(mock commit)", files="mock.py",
        ))
    return out


def build_hard_negatives(n: int = 20, seed: int = 1) -> list[dict]:
    """The other direction: real defects the model must NOT wave through.

    A corpus made only of "stay quiet" pairs teaches silence. These pairs make
    the preference two-sided - correct finding over false reassurance.
    """
    rng = random.Random(seed)
    out = []
    for diff, analysis in mock_commits(n * 2, rng):
        if not analysis.findings:
            continue
        out.append(pair(
            diff,
            chosen=analysis,
            rejected=Analysis(
                summary="This change looks like a small, safe adjustment; "
                        "no defects found.",
                findings=[],
            ),
            subject="(mock commit)", files="mock.py",
        ))
        if len(out) >= n:
            break
    return out


def from_reviews(path: Path) -> list[dict]:
    """Logged reviews carrying a human correction.

    Expected per record: `diff`, `model_analysis` (what the model said) and
    either `human_analysis` (the correction) or `label: "false_positive"`.
    """
    out = []
    with open(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            model = rec.get("model_analysis")
            if not model or not rec.get("diff"):
                continue
            model_analysis = Analysis.model_validate(model)

            if rec.get("human_analysis"):
                chosen = Analysis.model_validate(rec["human_analysis"])
            elif rec.get("label") == "false_positive":
                chosen = Analysis(
                    summary="Semantic review of this diff shows standard, safe "
                            "code. No defects found.",
                    findings=[],
                )
            else:
                continue  # unlabelled: nothing to prefer

            if chosen.to_json() == model_analysis.to_json():
                continue  # model was right; no signal
            out.append(pair(
                rec["diff"], chosen, model_analysis,
                subject=rec.get("subject", ""),
                files=", ".join(rec.get("files", [])),
            ))
    return out


def from_eval(path: Path, misses: bool = True) -> list[dict]:
    """On-policy pairs: the tuned model's own mistakes on held-out commits.

    `evaluate.py` writes every held-out record back with what the model actually
    said. Where it was wrong, the teacher's analysis is the correction and the
    model's own answer is the rejection - which is the whole point of going
    on-policy: the rejected side is a sentence this model really produces, not
    a hallucination written by hand.

    A mistake counts only when SZZ and the teacher agree about the commit. They
    agree on roughly seven commits in eight; on the eighth, "wrong" is not
    established, and training against a disputed label teaches the disagreement.

      false positive  model reported a defect, label clean and teacher silent
      missed defect   model stayed silent, label buggy and teacher found it

    `misses=False` keeps only the false positives. It is the wrong default: a
    set that only ever prefers the empty answer teaches silence, which is the
    failure this pipeline already had to fix once.
    """
    out = []
    for line in open(path):
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("error") or not rec.get("diff"):
            continue
        said = Analysis.model_validate(rec["predicted"])
        # Mined commits carry an SZZ label and no teacher. That still supports
        # the false-positive direction, because the correction for "reported a
        # defect on a commit no later fix touched" is the empty answer, which
        # needs no explanation and therefore no teacher. The missed-defect
        # direction does need one - a chosen answer has to say what is wrong.
        teacher = (Analysis.model_validate(rec["analysis"])
                   if rec.get("analysis") else None)

        if said.findings and not rec["buggy"] and not (teacher and teacher.findings):
            chosen = teacher or Analysis(
                summary="Semantic review of this diff shows standard, safe "
                        "code. No defects found.",
                findings=[])
        elif (misses and teacher and not said.findings
              and rec["buggy"] and teacher.findings):
            chosen = teacher
        else:
            continue  # right, disputed, or unteachable without a teacher
        out.append(pair(rec["diff"], chosen, said,
                        subject=rec.get("subject", ""),
                        files=", ".join(rec.get("files", []))))
    return out


def from_labelled(path: Path, limit: int = 0) -> list[dict]:
    """Real missed-defect pairs: prefer the teacher's finding over silence.

    The counterweight to `from_eval`, which can only teach silence when it has
    no teacher. A set made purely of "say nothing" pairs produces a model that
    says nothing, so the preference has to pull both ways.

    These labels were written by a teacher that had been told a defect existed,
    which is what capped the first training round - told there is a bug, it
    finds one whether or not the diff shows it. Findings that cite nothing in
    the diff are the signature of one invented to order, so `grounded` drops
    them: what survives is a finding pointing at code that is actually there.
    """
    from evaluate import grounded

    out = []
    for line in open(path):
        if not line.strip():
            continue
        rec = json.loads(line)
        if not rec.get("diff") or not rec.get("analysis"):
            continue
        analysis = Analysis.model_validate(rec["analysis"])
        if not analysis.findings:
            continue
        if not all(grounded(f.model_dump(), rec["diff"]) for f in analysis.findings):
            continue
        out.append(pair(
            rec["diff"], analysis,
            Analysis(summary="This change looks like a small, safe adjustment; "
                             "no defects found.", findings=[]),
            subject=rec.get("subject", ""),
            files=", ".join(rec.get("files", []))))
        if limit and len(out) >= limit:
            break
    return out


def write_jsonl(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reviews", type=Path, help="logged reviews with corrections")
    ap.add_argument("--from-eval", type=Path,
                    help="evaluate.py results: build pairs from this model's "
                         "own errors")
    ap.add_argument("--no-misses", action="store_true",
                    help="with --from-eval, keep false positives only")
    ap.add_argument("--out", type=Path, default=Path(DPO_DATASET))
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--n", type=int, default=40, help="false-positive pairs, with --mock")
    ap.add_argument("--hard-negatives", type=int, default=20,
                    help="missed-defect pairs to add, with --mock")
    ap.add_argument("--frontend-repeat", type=int, default=4,
                    help="times to repeat each Turnstile/auth-guard case")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    if args.from_eval:
        rows = from_eval(args.from_eval, misses=not args.no_misses)
        if not rows:
            raise SystemExit(f"no undisputed errors in {args.from_eval} — "
                             f"nothing to correct")
    elif args.reviews:
        rows = from_reviews(args.reviews)
        if not rows:
            raise SystemExit(f"no labelled pairs in {args.reviews}")
    elif args.mock:
        rows = (build_mock(args.n, args.seed)
                + build_hard_negatives(args.hard_negatives)
                + build_frontend_pairs(args.frontend_repeat))
    else:
        raise SystemExit("pass --mock, --reviews <file> or --from-eval <file>")

    out = write_jsonl(rows, args.out)
    quiet = sum(1 for r in rows if not json.loads(r["chosen"])["findings"])
    captcha = sum(1 for r in rows
                  if "turnstile" in r["prompt"].lower() or "captcha" in r["prompt"].lower())
    print(f"{len(rows)} preference pairs -> {out}  "
          f"({quiet} teach silence, {len(rows) - quiet} teach speaking up, "
          f"{captcha} frontend security-boilerplate cases)")


def _selftest() -> None:
    fe = build_frontend_pairs(repeat=1)
    assert len(fe) == 5, len(fe)
    ctxed = [p for p in fe if "Surrounding code" in p["prompt"]]
    assert len(ctxed) >= 3, "frontend pairs must carry file context"
    assert any("disabled={!token || pending}" in p["prompt"] for p in fe), \
        "the control the guard protects must be in the prompt"
    for p in fe:
        assert json.loads(p["chosen"])["findings"] == [], \
            "captcha guard must be preferred as safe"
        assert json.loads(p["rejected"])["findings"], \
            "rejected must contain the hallucinated defect"
        # Small edit distance is the point - and the reason DPOP is used.
        assert len(p["chosen"]) < len(p["rejected"]) + 400
    fp = build_mock(6, seed=2)
    hn = build_hard_negatives(4)
    assert len(fp) == 6 and len(hn) == 4
    for p in fp + hn:
        assert set(p) == {"prompt", "chosen", "rejected"}
        assert p["chosen"] != p["rejected"]
        Analysis.model_validate_json(p["chosen"])
        Analysis.model_validate_json(p["rejected"])
        assert "```diff" in p["prompt"]
    assert all(not json.loads(p["chosen"])["findings"] for p in fp)
    assert all(json.loads(p["chosen"])["findings"] for p in hn), \
        "hard negatives must prefer the real finding"
    assert all(not json.loads(p["rejected"])["findings"] for p in hn)

    # On-policy pairs: a false positive, a missed defect, one correct answer and
    # one where SZZ and the teacher disagree. Only the first two are pairs.
    import tempfile

    invented = {"category": "concurrency", "explanation": "workers interleave"}
    real = {"category": "off-by-one", "explanation": "admits the boundary"}
    rows = [
        {"diff": "@@ -1 +1 @@\n-a\n+b\n", "buggy": False, "error": None,
         "analysis": {"summary": "safe", "findings": []},
         "predicted": {"summary": "risky", "findings": [invented]}},
        {"diff": "@@ -2 +2 @@\n-c\n+d\n", "buggy": True, "error": None,
         "analysis": {"summary": "off-by-one", "findings": [real]},
         "predicted": {"summary": "safe", "findings": []}},
        {"diff": "@@ -3 +3 @@\n-e\n+f\n", "buggy": False, "error": None,
         "analysis": {"summary": "safe", "findings": []},
         "predicted": {"summary": "safe", "findings": []}},
        # SZZ says buggy, the teacher found nothing: "wrong" is not established.
        {"diff": "@@ -4 +4 @@\n-g\n+h\n", "buggy": True, "error": None,
         "analysis": {"summary": "safe", "findings": []},
         "predicted": {"summary": "safe", "findings": []}},
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
        evalfile = Path(fh.name)
    both = from_eval(evalfile)
    assert len(both) == 2, both
    assert json.loads(both[0]["chosen"])["findings"] == []
    assert json.loads(both[0]["rejected"])["findings"] == [invented | {"file": ""}]
    assert json.loads(both[1]["chosen"])["findings"], "missed defect must be taught"
    fps = from_eval(evalfile, misses=False)
    assert len(fps) == 1 and json.loads(fps[0]["chosen"])["findings"] == []
    evalfile.unlink()


if __name__ == "__main__":
    _selftest()
    main()
