"""Turn the repair-supervised dataset into ChatML SFT records.

    python -m dataset_builder.build_repair_sft --audit
    python -m dataset_builder.build_repair_sft --out data/sft_repair_msgs.jsonl

Diff rendering, stated explicitly
---------------------------------
PLAIN UNIFIED, not word-diff. Three reasons, and this has to be pinned down here
because a train/inference rendering mismatch has cost this project twice:

  1. `_render` in llm_explainer/client.py maps DIFF_RENDERING="auto" to word-diff
     only under OUTPUT_CONTRACT v2/v3. This is a new contract, so auto already
     resolves to unified - no override needed at inference.
  2. Word-diff is what the v3 corpus used, and gpt-oss-120b - which never saw it
     - quoted `{+...+}` markers as source and filed three bogus syntax findings.
     Anything reading these commits from git gets unified.
  3. The mined diffs are `git show --unified=3` already.

INFERENCE MUST MATCH: serve this checkpoint with ORACLE_OUTPUT_CONTRACT=repair
(or anything that is not v2/v3) so `_render` leaves the diff alone.

Loss masking
------------
`train_sft.py` already sets SFTConfig(assistant_only_loss=True), so the loss is
taken over response tokens only. Nothing extra is needed here; the record just
has to be a well-formed messages list for the chat template to segment.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Imported, NOT redefined. These two literals are the contract, and a second
# copy here is how a corpus and its inference prompt drift apart without any
# test failing. schema.py is the single source; `_PROMPTS["repair"]` serves the
# same bytes to the model at inference that this file bakes into the corpus.
from dataset_builder.schema import (_SYSTEM_PROMPT_REPAIR as SYSTEM,  # noqa: E402
                                    _USER_TEMPLATE_REPAIR as USER)

MAX_DIFF_CHARS = 6000
# Token budget for the WHOLE sequence. The diff is trimmed until the record fits,
# so the assistant turn is never what gets cut.
#
# The tokenizer truncates from the RIGHT, which is where the target lives. At
# max_seq_length=1152 that silently chopped the assistant turn on 69% of this
# corpus (p50 is 1580 tokens). Trimming the diff here instead means the target
# always survives, and the model still sees the head and tail of the change -
# the middle of a long hunk is the least informative part of it.
MAX_SEQ_TOKENS = 2048
KEEP_HEAD_FRAC = 0.6          # more of the start than the end when eliding


def fit_diff(tok, system: str, subject: str, files: str, diff: str,
             assistant: str) -> tuple[str, bool]:
    """Trim the middle of the diff until the full record fits the budget."""
    def total(d: str) -> int:
        msgs = [{"role": "system", "content": system},
                {"role": "user", "content": USER.format(subject=subject, files=files,
                                                        diff=d)},
                {"role": "assistant", "content": assistant}]
        return len(tok(tok.apply_chat_template(msgs, tokenize=False)).input_ids)

    if total(diff) <= MAX_SEQ_TOKENS:
        return diff, False
    lines = diff.splitlines()
    lo, hi = 0, len(lines)
    while hi - lo > 4:
        mid = (lo + hi) // 2
        head = int(mid * KEEP_HEAD_FRAC)
        cand = "\n".join(lines[:head] + ["... (diff elided) ..."] + lines[len(lines) - (mid - head):])
        if total(cand) <= MAX_SEQ_TOKENS:
            lo = mid
        else:
            hi = mid
    head = int(lo * KEEP_HEAD_FRAC)
    return ("\n".join(lines[:head] + ["... (diff elided) ..."]
                      + lines[len(lines) - (lo - head):]), True)


def split_holdout(rows, frac, by, seed):
    """Split off a holdout set. Returns (train, held).

    WHY THIS EXISTS: the first repair run trained on all 1164 records with no
    held-out set at all, so nothing measured whether the model ever answered
    `defect_found: true`. It answered `false` to 40/40 of its own training
    positives and still logged loss 0.23 and 93% token accuracy for sixteen
    hours. A split is what makes that visible in the first epoch instead of the
    last.

    by="label"    stratified random, holdout shares projects with train. Low
                  variance, and the right thing for a training-health GATE --
                  but it is not a generalisation number, because style learned
                  from a project in train is available on the same project here.
    by="project"  whole projects held out, so nothing in the holdout was seen.
                  Higher variance (29 projects, the top 5 hold 67% of records)
                  and the label ratio drifts, but this is the honest one to
                  report.
    """
    import random
    rng = random.Random(seed)

    if by == "project":
        projects = sorted({r["project"] for r in rows})
        rng.shuffle(projects)
        want, held_projects, n = int(len(rows) * frac), set(), 0
        # Largest-first would blow past the target on one project; this walks
        # the shuffled order and stops as soon as the quota is met.
        for proj in projects:
            size = sum(1 for r in rows if r["project"] == proj)
            if n + size > want and held_projects:
                continue
            held_projects.add(proj)
            n += size
            if n >= want:
                break
        held = [r for r in rows if r["project"] in held_projects]
        train = [r for r in rows if r["project"] not in held_projects]
        return train, held

    # label-stratified: draw frac of each class so the positive rate survives
    held = []
    for lab in sorted({r["label"] for r in rows}):
        pool = [r for r in rows if r["label"] == lab]
        rng.shuffle(pool)
        held += pool[:round(len(pool) * frac)]
    held_ids = {id(r) for r in held}
    train = [r for r in rows if id(r) not in held_ids]
    # Shuffle the holdout: it is built class-by-class, so written in that order
    # every prefix of it is all-negative. A capped eval would then measure recall
    # over zero positives and report `nan` -- a metric reading nothing, which is
    # the failure this split exists to prevent.
    rng.shuffle(held)
    return train, held


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=ROOT / "data/sft_repair_clean.jsonl")
    ap.add_argument("--out", type=Path, default=ROOT / "data/sft_repair_msgs.jsonl")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--holdout", type=float, default=0.1, metavar="FRAC",
                    help="fraction held out for evaluation (0 disables)")
    ap.add_argument("--holdout-by", choices=("label", "project"), default="label",
                    help="label: stratified random, a training-health gate. "
                         "project: whole projects held out, the honest number")
    ap.add_argument("--holdout-out", type=Path, default=None,
                    help="default: --out with a _holdout suffix")
    ap.add_argument("--split-seed", type=int, default=17)
    args = ap.parse_args()

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-Coder-3B-Instruct")

    rows = [json.loads(l) for l in open(args.src)]
    out, skipped = [], Counter()
    for r in rows:
        subject, files = r["subject"][:120], ", ".join(r["files"])
        # Keys in the order the schema lists them, so the model always emits the
        # verdict before the prose that justifies it.
        t = r["target"]
        assistant = json.dumps({
            "defect_found": t["defect_found"],
            "confidence": t["confidence"],
            "target_file": t["target_file"],
            "affected_identifiers": t["affected_identifiers"],
            "explanation": t["explanation"],
            "repair_direction": t["repair_direction"],
        }, ensure_ascii=False)
        diff, elided = fit_diff(tok, SYSTEM, subject, files, r["diff"], assistant)
        if elided:
            skipped["elided"] += 1
        # The elision removes the MIDDLE of the diff, which can take an
        # identifier the target names with it. The upstream filter checked
        # grounding against the full diff, so this is the last place the
        # invariant can be enforced: what the model is shown must contain every
        # symbol its target names, or the record teaches the model to name
        # things it cannot see - the exact failure this corpus exists to fix.
        named = re.findall(r"`([^`]+)`", t["explanation"] or "")
        if any(n not in diff for n in named):
            skipped["elided past a named identifier"] += 1
            continue
        user = USER.format(subject=subject, files=files, diff=diff)
        out.append({"messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ], "label": r["label"], "project": r["project"], "rev": r["rev"]})

    d = sum(1 for o in out if o["label"] == 1)
    print(f"{len(out)} SFT records  ({d} defective {100*d//len(out)}% / {len(out)-d} clean)")
    print(f"  diffs elided to fit {MAX_SEQ_TOKENS} tokens: {skipped['elided']}")
    print(f"  dropped, elision cut a named identifier: "
          f"{skipped['elided past a named identifier']}")
    lens = sorted(len(o["messages"][0]["content"]) + len(o["messages"][1]["content"])
                  for o in out)
    print(f"  prompt chars: median {lens[len(lens)//2]}, p90 {lens[int(len(lens)*0.9)]}, max {lens[-1]}")
    # every assistant turn must be valid JSON with the exact schema
    bad = 0
    for o in out:
        try:
            j = json.loads(o["messages"][-1]["content"])
            if set(j) != {"defect_found", "confidence", "target_file",
                          "affected_identifiers", "explanation", "repair_direction"}:
                bad += 1
        except Exception:
            bad += 1
    print(f"  assistant turns failing schema: {bad}")
    print(f"  projects: {len({o['project'] for o in out})}")

    if args.audit:
        print("\n--- one record ---")
        print(json.dumps(out[0]["messages"][1]["content"][:400], ensure_ascii=False)[:420])
        print(out[0]["messages"][-1]["content"][:260])
        return
    train, held = (out, [])
    if args.holdout > 0:
        train, held = split_holdout(out, args.holdout, args.holdout_by,
                                    args.split_seed)

    def rate(rs):
        d = sum(1 for r in rs if r["label"] == 1)
        return f"{len(rs)} ({d} defective, {100 * d / max(1, len(rs)):.0f}%)"

    def write(path, rs):
        with open(path, "w") as fh:
            for o in rs:
                fh.write(json.dumps(o, ensure_ascii=False) + "\n")

    write(args.out, train)
    print(f"\n-> {args.out}   train    {rate(train)}")
    if held:
        hp = args.holdout_out or args.out.with_name(
            args.out.stem + "_holdout" + args.out.suffix)
        write(hp, held)
        shared = ({r["project"] for r in train} & {r["project"] for r in held})
        print(f"-> {hp}   holdout  {rate(held)}")
        print(f"   split by {args.holdout_by}, seed {args.split_seed}; "
              f"{len(shared)} projects appear in both")
        if args.holdout_by == "label":
            print("   NOTE: holdout shares projects with train — read it as a "
                  "training-health gate, not a generalisation number.")
        if not any(r["label"] == 1 for r in held):
            raise SystemExit("holdout contains no defective records — it cannot "
                             "measure the thing this split exists to measure")


if __name__ == "__main__":
    main()
