#!/usr/bin/env python3
"""Measure how much of a model's stored answer is copied verbatim from a corpus.

    python bench/template_audit.py --corpus data/sft_v3_extract.jsonl \
        --tags v2_pilot2 v2_seed7 v3 v3_seed7

    # each run against the corpus it was actually trained on, plus the
    # cross-corpus floor:
    python bench/template_audit.py --own

Why this script exists
----------------------
On 30 Aug the v3 checkpoints were read by hand on five held-out cases and both
looked like they were reciting sentences out of `data/sft_v3_extract.jsonl`
rather than reading the diff. Five hand-read cases is a story, not a
measurement, and this project has twice acted on a story. This turns it into a
number that a pre-registered condition can be checked against.

The metric
----------
Words are lowercased `[a-z0-9_]+` tokens taken from the PROSE of an answer -
`summary` plus every `findings[].explanation`. JSON keys, the `effect` literals
and punctuation are excluded, so the score cannot be inflated by the schema
every answer shares.

For each answer:

  coverage - the share of its words that sit inside at least one 8-word window
             appearing verbatim in the corpus. This is the headline. 0.0 means
             nothing longer than 7 words is shared; 1.0 means every word of the
             answer is inside copied text.
  longest  - the longest run of words reproduced exactly, verified against a
             single corpus record rather than inferred from overlapping
             windows.

An answer needs at least 8 prose words to be scored; shorter ones and errored
rows are counted under `skipped`.

Reading the numbers
-------------------
Copying is only meaningful against a floor. A model scores some overlap on any
corpus just by writing English about diffs in the ORACLE house style, so run
checkpoints that never saw a corpus against it (`--own` does this for you) and
read the trained-on column against the never-saw-it column. A run scoring the
same on both did not memorise anything; the shared words are the register.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

SETS = {"basic": "basic_bench",
        "mech_heldout": "heldout_mech",
        "clean_heldout": "heldout_clean"}

# Which corpus each published run tag was fine-tuned on. The two v2 tags are
# one corpus at two seeds; likewise the two v3 tags.
TRAINED_ON = {"v2_pilot2": "sft_v2_pilot2",
              "v2_seed7": "sft_v2_pilot2",
              "v3": "sft_v3_extract",
              "v3_seed7": "sft_v3_extract",
              # v4 trained on sft_v4_suggest, NOT sft_v5_suggest: v5 is the
              # same corpus with the token-trimming defect fixed, built after
              # the run started. A checkpoint is only auditable against the
              # corpus it actually saw, which is why v4 is kept on disk.
              "v4": "sft_v4_suggest",
              "v4_seed7": "sft_v4_suggest",
              "v4_ep1": "sft_v4_suggest",
              "v4_ep1_seed7": "sft_v4_suggest",
              "v6": "sft_v6_suggest",
              "v6_seed7": "sft_v6_suggest"}

WORD = re.compile(r"[a-z0-9_]+")


def words(text: str) -> list[str]:
    return WORD.findall(text.lower())


# Whether `effect.check` counts as prose. It is a sentence a human reads, so it
# belongs in a copying measurement - but every number this repo has published
# was computed WITHOUT it, and silently redefining the metric would make the v2
# and v4 rows incomparable to anything measured after. So it is a flag, off by
# default, and `--with-check` prints the wider figure beside the published one.
#
# It matters: the v4 `check` field was a per-category template in 357 of 366
# corpus targets and the model emitted "the edit touches" on 100% of cases, and
# NONE of that appeared in this script's output, because this script could not
# see the field. The measurement missing the defect is how the defect survived
# to a training run.
INCLUDE_CHECK = False


def prose(answer: dict) -> list[str]:
    """The natural-language part of an answer: summary + finding explanations."""
    out: list[str] = []
    if not isinstance(answer, dict):
        return out
    summary = answer.get("summary")
    if isinstance(summary, str):
        out += words(summary)
    findings = answer.get("findings")
    if isinstance(findings, list):
        for f in findings:
            if isinstance(f, dict) and isinstance(f.get("explanation"), str):
                out += words(f["explanation"])
    if INCLUDE_CHECK:
        eff = answer.get("effect")
        if isinstance(eff, dict) and isinstance(eff.get("check"), str):
            out += words(eff["check"])
    return out


# The corpus upsamples each case, so two records can be six copies of one case.
# A leave-one-out score that drops only the record itself then finds the case's
# own siblings and reports ~91% for every corpus ever built, which measures
# upsampling rather than templating. Group by the case, and leave the whole
# family out.
_SUBJECT = re.compile(r"^subject: \((.+?)\)$", re.M)


def _case_of(user: str) -> str:
    m = _SUBJECT.search(user or "")
    return m.group(1) if m else ""


def load_corpus(path: Path, groups: list[str] | None = None) -> list[list[str]]:
    """Prose word-lists for every assistant turn in an SFT corpus.

    `groups`, when passed, is filled with each record's case id, so
    `self_similarity` can leave a whole upsampled family out.
    """
    records = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            msgs = json.loads(line).get("messages", [])
            case = _case_of(next((m.get("content", "") for m in msgs
                                  if m.get("role") == "user"), ""))
            for m in msgs:
                if m.get("role") != "assistant":
                    continue
                content = m.get("content", "")
                if groups is not None:
                    groups.append(case)
                try:
                    answer = json.loads(content)
                except json.JSONDecodeError:
                    records.append(words(content))
                    continue
                records.append(prose(answer))
    return records


def build_index(records: list[list[str]], n: int) -> dict:
    """n-gram -> [(record index, offset), ...]"""
    index: dict[tuple, list[tuple[int, int]]] = {}
    for ri, toks in enumerate(records):
        for i in range(len(toks) - n + 1):
            index.setdefault(tuple(toks[i:i + n]), []).append((ri, i))
    return index


def score(pred: list[str], records, index, n: int, max_postings: int = 64):
    """(coverage, longest verbatim run) for one answer."""
    if len(pred) < n:
        return None
    hit = [False] * len(pred)
    longest = 0
    for i in range(len(pred) - n + 1):
        postings = index.get(tuple(pred[i:i + n]))
        if not postings:
            continue
        for j in range(i, i + n):
            hit[j] = True
        # extend each occurrence forward for the exact longest run
        for ri, pos in postings[:max_postings]:
            toks = records[ri]
            k = n
            while (i + k < len(pred) and pos + k < len(toks)
                   and pred[i + k] == toks[pos + k]):
                k += 1
            longest = max(longest, k)
    return sum(hit) / len(hit), longest


def load_runs(tag: str) -> dict[str, list[dict]]:
    """Stored bench rows for a run tag, per eval set. Missing files are skipped."""
    out = {}
    for label, stem in SETS.items():
        path = DATA / f"{stem}_{tag}.jsonl"
        if not path.exists():
            continue
        rows = []
        with path.open() as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        out[label] = rows
    return out


def audit(tag: str, corpus_name: str, records, index, n: int):
    """Per-set stats for one run tag against one corpus."""
    results = {}
    for label, rows in load_runs(tag).items():
        covs, longs, skipped = [], [], 0
        for row in rows:
            pred = row.get("predicted")
            toks = prose(pred) if isinstance(pred, dict) else []
            s = score(toks, records, index, n)
            if s is None:
                skipped += 1
                continue
            covs.append(s[0])
            longs.append(s[1])
        results[label] = {"n": len(covs), "skipped": skipped,
                          "mean": statistics.fmean(covs) if covs else 0.0,
                          "median": statistics.median(covs) if covs else 0.0,
                          "p90": (sorted(covs)[int(0.9 * (len(covs) - 1))]
                                  if covs else 0.0),
                          "max": max(covs) if covs else 0.0,
                          "heavy": sum(1 for c in covs if c >= 0.5),
                          "longest": max(longs) if longs else 0}
    return results


def worst_cases(tag: str, records, index, n: int, k: int = 5):
    """The k most-copied answers for a tag, for eyeballing what got recited."""
    out = []
    for label, rows in load_runs(tag).items():
        for row in rows:
            pred = row.get("predicted")
            toks = prose(pred) if isinstance(pred, dict) else []
            s = score(toks, records, index, n)
            if s is None:
                continue
            out.append((s[0], s[1], label, row.get("id"),
                        (pred or {}).get("summary", "")))
    out.sort(reverse=True, key=lambda r: r[0])
    return out[:k]


def self_similarity(records: list[list[str]], n: int,
                    groups: list[str] | None = None) -> dict:
    """How much of each target could be recited from the REST of the corpus.

    Leave-one-out: build the index over every other record and score this one
    against it. A corpus where the average target is 60% reproducible from its
    neighbours will produce a model that recites, whatever the training recipe
    is - and that is knowable before a GPU is booked, which is the point.

    This is the pre-flight the v4 run did not have. Its corpus put one sentence
    in 97% of targets and the run was launched anyway.
    """
    index: dict[tuple, list[tuple[int, int]]] = {}
    for ri, toks in enumerate(records):
        for i in range(len(toks) - n + 1):
            index.setdefault(tuple(toks[i:i + n]), []).append((ri, i))

    grp = groups if groups and len(groups) == len(records) else None
    covs, longs, skipped = [], [], 0
    for ri, toks in enumerate(records):
        if len(toks) < n:
            skipped += 1
            continue
        hit = [False] * len(toks)
        longest = 0
        for i in range(len(toks) - n + 1):
            # Leave out the whole upsampled family, not just this record.
            postings = [(r, o) for r, o in index.get(tuple(toks[i:i + n]), [])
                        if (grp[r] != grp[ri] if grp else r != ri)]
            if not postings:
                continue
            for j in range(i, i + n):
                hit[j] = True
            for rj, pos in postings[:64]:
                other = records[rj]
                k = n
                while (i + k < len(toks) and pos + k < len(other)
                       and toks[i + k] == other[pos + k]):
                    k += 1
                longest = max(longest, k)
        covs.append(sum(hit) / len(hit))
        longs.append(longest)
    if not covs:
        return {}
    return {"n": len(covs), "skipped": skipped,
            "mean": statistics.fmean(covs), "median": statistics.median(covs),
            "p90": sorted(covs)[int(0.9 * (len(covs) - 1))],
            "max": max(covs), "heavy": sum(1 for c in covs if c >= 0.5),
            "longest": max(longs)}


def print_table(title: str, per_tag: dict):
    print(f"\n{title}")
    print(f"{'run':<12} {'set':<14} {'n':>4} {'skip':>5} "
          f"{'mean':>7} {'med':>7} {'p90':>7} {'max':>7} {'>=50%':>6} {'longest':>8}")
    print("-" * 92)
    for tag, sets in per_tag.items():
        for label, s in sets.items():
            print(f"{tag:<12} {label:<14} {s['n']:>4} {s['skipped']:>5} "
                  f"{s['mean']:>6.1%} {s['median']:>6.1%} {s['p90']:>6.1%} "
                  f"{s['max']:>6.1%} {s['heavy']:>6} {s['longest']:>8}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", help="SFT corpus to measure copying against")
    ap.add_argument("--tags", nargs="+", default=list(TRAINED_ON),
                    help="run tags, i.e. the suffix on data/basic_bench_<tag>.jsonl")
    ap.add_argument("--own", action="store_true",
                    help="score every tag against every known corpus, so the "
                         "trained-on figure can be read against its floor")
    ap.add_argument("-n", type=int, default=8, help="window size in words (default 8)")
    ap.add_argument("--show", type=int, default=0,
                    help="also print the N most-copied answers per tag")
    ap.add_argument("--with-check", action="store_true",
                    help="count effect.check as prose too. Off by default: "
                         "every published number was computed without it")
    ap.add_argument("--self", dest="selfsim", action="store_true",
                    help="leave-one-out: how much of each CORPUS target could "
                         "be recited from the rest of the corpus. Run this "
                         "before booking a GPU, not after")
    args = ap.parse_args()

    global INCLUDE_CHECK
    INCLUDE_CHECK = args.with_check

    if args.own:
        corpora = sorted(set(TRAINED_ON.values()))
    elif args.corpus:
        corpora = [Path(args.corpus).stem]
    else:
        ap.error("pass --corpus <file> or --own")

    for name in corpora:
        path = DATA / f"{name}.jsonl"
        groups: list[str] = []
        records = load_corpus(path, groups)
        index = build_index(records, args.n)
        total = sum(len(r) for r in records)
        print(f"\n=== corpus {name}: {len(records)} assistant turns, "
              f"{total} prose words, {len(index)} distinct {args.n}-grams "
              f"({'with' if INCLUDE_CHECK else 'without'} effect.check) ===")
        if args.selfsim:
            s = self_similarity(records, args.n, groups)
            if s:
                fam = len(set(groups)) if groups else 0
                print(f"\nleave-one-CASE-out ({fam} cases): how much of a "
                      f"target is reachable from OTHER cases")
                print(f"{'corpus':<26} {'n':>4} {'mean':>7} {'med':>7} "
                      f"{'p90':>7} {'max':>7} {'>=50%':>6} {'longest':>8}")
                print("-" * 78)
                print(f"{name:<26} {s['n']:>4} {s['mean']:>6.1%} "
                      f"{s['median']:>6.1%} {s['p90']:>6.1%} {s['max']:>6.1%} "
                      f"{s['heavy']:>6} {s['longest']:>8}")
            if not args.tags or args.tags == list(TRAINED_ON):
                continue
        per_tag = {}
        for tag in args.tags:
            mark = " (trained on this)" if TRAINED_ON.get(tag) == name else ""
            per_tag[tag + mark] = audit(tag, name, records, index, args.n)
        print_table(f"verbatim {args.n}-word coverage of stored answers", per_tag)
        if args.show:
            for tag in args.tags:
                print(f"\n-- {tag}: {args.show} most-copied answers vs {name}")
                for cov, lng, label, cid, summary in worst_cases(
                        tag, records, index, args.n, args.show):
                    print(f"   {cov:5.1%} longest={lng:<4} {label:<14} {cid}")
                    print(f"      {summary[:150]}")


if __name__ == "__main__":
    main()
