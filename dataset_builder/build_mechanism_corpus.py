"""Build the combined SFT corpus: word-diffs, mechanism cases, clean direction.

`data/sft_mechanism_v1.jsonl` was assembled by hand and had no builder, so the
26 Aug result rested on a file nothing in the repo could regenerate. This script
is that builder, and it fixes three things measured after that run:

1. **Word-diff rendering.** Six of `mechanism-v1`'s seven false alarms make one
   identical false claim - that a call was *removed* - when the diff shows it
   edited in place. A unified diff genuinely does render an in-place edit as
   remove+add, so the model was describing its input. Switching the rendering at
   inference was measured and lost (41/46 -> 36/46) because the model had never
   seen the notation; the fix is to train on it.

2. **The clean direction.** Every one of the 27 mechanism cases is `buggy: true`.
   Recall went to 33/33 and precision to 6/13, which is what a one-directional
   corpus predicts. `bench/clean_direction` supplies the same constructs as
   fixes and as behaviour-preserving refactors.

3. **The sequence budget, which is the big one.** `MAX_SEQ_LENGTH` is 1024 and
   TRL truncates `keep_start`, so a record whose *prompt* alone exceeds 1024
   loses its whole assistant turn and TRL drops it as fully masked. Measured on
   `sft_mechanism_v1`: 858 of 1748 records (49%) never contributed a gradient,
   which the run's own step count confirms - 224 steps x 8 accum / 2 epochs =
   896 records, not 1748. This builder measures every record against the real
   tokenizer and shrinks the diff until the answer fits, so the corpus that is
   written is the corpus that trains.

    python -m dataset_builder.build_mechanism_corpus \\
        --tokenizer artifacts/base-3b --out data/sft_mechanism_v2.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import OUTPUT_CONTRACT
from dataset_builder.schema import (SYSTEM_PROMPT, Analysis, Effect,
                                    build_user_message)
from dataset_builder.worddiff import to_word_diff

ROOT = Path(__file__).resolve().parent.parent
LANGS8 = ["go", "javascript", "php", "java", "rust", "python", "typescript", "ruby"]


# --------------------------------------------------------------------------
# rendering


def case_diff(d: Path, cid: str, ext: str) -> str:
    """A case directory rendered the way the benchmark renders it."""
    p = subprocess.run(
        ["git", "diff", "--no-index", "--no-color", "--src-prefix=a/",
         "--dst-prefix=b/", str(d / f"pre.{ext}"), str(d / f"post.{ext}")],
        capture_output=True, text=True)
    name = f"{cid}.{ext}"
    return (p.stdout.replace(str(d / f"pre.{ext}"), name)
                    .replace(str(d / f"post.{ext}"), name))


def executed_effect(root: Path, m: dict) -> Effect | None:
    """Build the `effect` field by RUNNING the case, never by describing it.

    This is the whole point of the v2 contract. The v1 fix template said "the
    program's output changes from {was} to {now}" and filled it from the note,
    which taught the model the *form* of citing executed output without teaching
    that the citation must be real - and it went on to invent panic traces and
    absolute paths for files that do not exist (RESULTS.md, 27 Aug).

    Here `before` and `after` are the actual bytes the two versions printed, so
    every target's behavioural claim is true by construction.

    Returns None under the v1 contract, which keeps the old corpus byte-for-byte
    reproducible.
    """
    if OUTPUT_CONTRACT != "v2":
        return None
    import bench.basic_bench as bb  # imported late: only v2 needs a runner
    prev, bb.ROOT = bb.ROOT, root
    try:
        rc_pre, out_pre = bb._run(m, "pre")
        rc_post, out_post = bb._run(m, "post")
    finally:
        bb.ROOT = prev
    label = m.get("label") or ("buggy" if m.get("buggy") else "clean")
    direction = {"buggy": "post-breaks", "fix": "post-fixes"}.get(label, "unchanged")

    def obs(rc: int, out: str) -> str:
        out = " ".join(out.split())[:200]
        return out or f"exit status {rc}, no output"

    return Effect(
        # Thin on purpose, and the weakest part of this corpus: every case is a
        # single file with one entry point, so the honest trigger is "run it".
        # Real commits are what make this field carry information; do not invent
        # variety here that the cases do not have.
        trigger=f"running {m['id']}.{m['ext']} as written",
        before=obs(rc_pre, out_pre),
        after=obs(rc_post, out_post),
        direction=direction,
    )


def record(diff: str, analysis: Analysis, subject: str, files: str,
           word: bool) -> dict:
    return {"messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(
            to_word_diff(diff) if word else diff, subject, files,
            include_schema=False)},
        {"role": "assistant", "content": analysis.to_json()},
    ]}


# --------------------------------------------------------------------------
# sources


def bulk(path: Path, word: bool) -> list[dict]:
    """The 8-language teacher-labelled corpus, re-rendered.

    Reproduces `data/sft_multilang8.jsonl` when `word` is off: same source, same
    language filter, same 1667 records.
    """
    out = []
    for line in open(path):
        if not line.strip():
            continue
        r = json.loads(line)
        if not r.get("diff") or r.get("language") not in LANGS8:
            continue
        analysis = (Analysis.model_validate(r["analysis"]) if r.get("analysis")
                    else Analysis(summary="This change is behaviour-preserving; "
                                          "no defect found."))
        out.append(record(r["diff"], analysis, r.get("subject", ""),
                          ", ".join(r.get("files", [])), word))
    return out


def mechanism(word: bool, times: int) -> list[dict]:
    """The hand-authored mechanism cases, from files this repo can regenerate.

    The assistant turns live beside each case as `analysis.json`; before this
    they existed only inside an unreproducible JSONL.
    """
    out = []
    for meta in sorted((ROOT / "bench/mechanism_pilot").glob("*/meta.json")):
        m = json.loads(meta.read_text())
        ap = meta.parent / "analysis.json"
        if not ap.exists():
            print(f"  !! {m['id']} has no analysis.json — skipped")
            continue
        a = Analysis.model_validate(json.loads(ap.read_text()))
        a.effect = executed_effect(ROOT / "bench/mechanism_pilot", m)
        d = case_diff(meta.parent, m["id"], m["ext"])
        out += [record(d, a, f"({m['id']})", f"{m['id']}.{m['ext']}", word)] * times
    return out


_CHANGED = re.compile(r"\[-(.*?)-\]|\{\+(.*?)\+\}", re.S)


def _changed_words(diff: str, limit: int = 6) -> str:
    seen: list[str] = []
    for a, b in _CHANGED.findall(to_word_diff(diff)):
        for tok in (a or b or "").split():
            if tok not in seen:
                seen.append(tok)
    return ", ".join(f"`{t}`" for t in seen[:limit])


def clean_direction(word: bool, times: int) -> list[dict]:
    """Fixes and refactors of the same constructs the mechanism cases teach.

    The summaries are composed from each case's own executed before/after output
    so no two targets are byte-identical: half the `sft-cve` corpus shared one assistant
    turn, the model memorised it, and ten GPU hours produced one output for
    every input. `distinct_targets()` exists because of that run.
    """
    out = []
    for meta in sorted((ROOT / "bench/clean_direction").glob("*/meta.json")):
        m = json.loads(meta.read_text())
        d = case_diff(meta.parent, m["id"], m["ext"])
        eff = executed_effect(ROOT / "bench/clean_direction", m)
        if m["label"] == "fix":
            if eff is not None:
                # v2: the observable output lives in `effect`, where it is real
                # and gradable. Keeping it in the prose as well is what taught
                # the model to quote output it never ran.
                summary = (
                    f"This commit repairs the {m['category']} in "
                    f"{m['parent']}.{m['ext']}: the function goes back to its "
                    f"correct form, and introduces no new defect.")
            else:
                # The note carries the executed before/after output, so the
                # summary states a behaviour change that was actually observed
                # rather than one inferred from reading the diff.
                was, _, now = m["note"].partition(": ")[2].partition(" -> ")
                summary = (
                    f"This commit repairs the {m['category']} in "
                    f"{m['parent']}.{m['ext']}: the function goes back to its "
                    f"correct form, and the program's output changes from {was} "
                    f"to {now}. The change removes a defect and introduces none.")
        else:
            old_name, new_name = m.get("renamed", ["a local", "a new name"])
            tail = ("the program's behaviour is unchanged." if eff is not None
                    else "the program's output is unchanged at "
                         f"{m['note'].rsplit('stays ', 1)[-1]}.")
            summary = (
                f"This commit renames `{old_name}` to `{new_name}` in "
                f"{m['parent']}.{m['ext']}. Every use is updated in place — the "
                f"declaration and its readers are edited, not deleted — and "
                f"{tail}")
        out += [record(d, Analysis(effect=eff, summary=summary, findings=[]),
                       f"({m['id']})", f"{m['id']}.{m['ext']}", word)] * times
    return out


# --------------------------------------------------------------------------
# fitting the sequence budget


class Fitter:
    """Shrink a record's diff until prompt+answer fit `max_len` tokens."""

    MARK = "\n... [diff truncated] ...\n"

    def __init__(self, tokenizer, max_len: int):
        self.tok, self.max_len = tokenizer, max_len
        self.shrunk = self.dropped = 0

    def _len(self, messages: list[dict]) -> int:
        text = self.tok.apply_chat_template(messages, tokenize=False)
        return len(self.tok(text, add_special_tokens=False)["input_ids"])

    def _split(self, user: str) -> tuple[str, str, str]:
        head, _, rest = user.partition("```diff\n")
        body, sep, tail = rest.rpartition("\n```")
        return head + "```diff\n", body, sep + tail

    def fit(self, rec: dict) -> dict | None:
        if self._len(rec["messages"]) <= self.max_len:
            return rec
        head, body, tail = self._split(rec["messages"][1]["content"])
        if not body:
            self.dropped += 1
            return None
        lo, hi, best = 0, len(body), None
        while lo <= hi:                       # largest diff that still fits
            mid = (lo + hi) // 2
            trial = dict(rec)
            trial["messages"] = list(rec["messages"])
            trial["messages"][1] = dict(rec["messages"][1])
            trial["messages"][1]["content"] = head + body[:mid] + self.MARK + tail
            if self._len(trial["messages"]) <= self.max_len:
                best, lo = trial, mid + 1
            else:
                hi = mid - 1
        if best is None:
            self.dropped += 1
            return None
        self.shrunk += 1
        return best


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labelled", type=Path, default=ROOT / "data/labelled_all.jsonl")
    ap.add_argument("--out", type=Path, default=ROOT / "data/sft_mechanism_v2.jsonl")
    ap.add_argument("--tokenizer", help="model dir whose tokenizer sets the budget")
    ap.add_argument("--max-seq-length", type=int, default=1024)
    ap.add_argument("--mechanism-times", type=int, default=6,
                    help="upsample factor for the 28 mechanism cases")
    ap.add_argument("--clean-times", type=int, default=3,
                    help="upsample factor for the 54 clean-direction cases")
    ap.add_argument("--unified", action="store_true",
                    help="keep unified diffs (the v1 rendering) instead of word-diffs")
    args = ap.parse_args(argv)

    word = not args.unified
    parts = {
        "bulk (8 langs, teacher-labelled)": bulk(args.labelled, word),
        f"mechanism x{args.mechanism_times}": mechanism(word, args.mechanism_times),
        f"clean-direction x{args.clean_times}": clean_direction(word, args.clean_times),
    }
    rows = [r for group in parts.values() for r in group]
    for name, group in parts.items():
        print(f"  {name}: {len(group)}")

    if args.tokenizer:
        from transformers import AutoTokenizer
        fitter = Fitter(AutoTokenizer.from_pretrained(args.tokenizer),
                        args.max_seq_length)
        fitted = [f for f in (fitter.fit(r) for r in rows) if f]
        print(f"\nsequence budget ({args.max_seq_length} tokens): "
              f"{len(rows) - fitter.shrunk - fitter.dropped} fit as written, "
              f"{fitter.shrunk} had the diff shrunk, {fitter.dropped} dropped")
        rows = fitted
    else:
        print("\n!! no --tokenizer: sequence budget NOT enforced. TRL truncates "
              "keep_start and drops fully-masked records, so an unfitted corpus "
              "trains on an unknown subset of itself.")

    from dataset_builder.build_sft_data import write_jsonl
    write_jsonl(rows, args.out)
    clean = sum(1 for r in rows
                if not json.loads(r["messages"][-1]["content"])["findings"])
    print(f"{len(rows)} SFT examples -> {args.out}  "
          f"({len(rows) - clean} with findings, {clean} clean, "
          f"{100 * clean / max(len(rows), 1):.0f}% clean)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
