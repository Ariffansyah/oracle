"""Drop repair targets whose identifiers are not identifiers.

    python -m dataset_builder.filter_repair_targets --report
    python -m dataset_builder.filter_repair_targets --out data/sft_repair_clean.jsonl

Why this exists as a file
-------------------------
This filter was applied ad-hoc on 1 Sep and never written down, so the corpus it
produced could not be rebuilt. It is a script now for the same reason the frame
counts are measured with the slots stripped: an unrecorded step is one nobody
can audit, and this project's recurring failure is a stage no metric reads.

What it drops, and why each rule is here
----------------------------------------
`symbols()` reads identifiers out of the diff text with a regex, so it also
picks up ordinary English from comments and prose. The observed damage:

    ids=['to']          "Rebinds `to` in blueprints.py"
    ids=['is']          "The exit paths of `is` ... are reorganised"
    ids=['get','has']   "Modifies the local execution path in `get`, `has`"

A target naming `to` teaches the model that any word in a comment is a symbol
worth reporting, which is the `no-such-entity` class in the 1 Sep grade -- 8 of
32 findings there named something absent from the diff. Training on it would be
teaching the failure directly.

  stopwords        an identifier that is an ordinary English word carries no
                   evidence, whatever the regex thinks
  grounded         the identifier must occur in the diff the model is shown.
                   This is the same rule the system prompt states ("Name no
                   identifier that is absent from the diff"), applied to the
                   targets so the corpus cannot contradict its own instruction
  source file      one target pointed `defect_found: true` at History.md. A
                   changelog has no runtime behaviour to get wrong
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

# Ordinary English that survives an identifier regex. Deliberately short: this
# is not a general stoplist, only words actually seen standing in for symbols.
STOPWORDS = {
    "to", "is", "as", "at", "by", "of", "on", "in", "if", "or", "and", "not",
    "the", "a", "an", "it", "its", "this", "that", "these", "those", "be",
    "was", "are", "were", "has", "have", "had", "do", "does", "did", "get",
    "set", "put", "any", "all", "no", "yes", "one", "two", "new", "old",
    "end", "start", "use", "used", "using", "can", "will", "may", "must",
    "should", "would", "when", "where", "which", "what", "how", "why",
    "from", "with", "for", "into", "out", "up", "down", "over", "under",
    "abs", "add", "run", "see", "note", "todo", "fixme", "true", "false",
    "null", "none", "nil", "undefined", "return", "class", "def", "function",
}
SRC_EXT = {".py", ".js", ".mjs", ".ts", ".tsx", ".java"}

# Grounding the defective identifiers costs defective rows (a commit whose repair
# touched nothing the commit itself touched cannot be described from the diff),
# so the 30:70 set in build_jit_dataset drifts. It is restored here, at the last
# stage, by subsampling the clean class - never by adding defective rows back.
DEFECT_SHARE = 0.30


def keep(row: dict) -> tuple[bool, str]:
    t = row["target"]
    ids = t.get("affected_identifiers") or []
    if not ids:
        return False, "no identifiers"
    if Path(t.get("target_file") or "").suffix not in SRC_EXT:
        return False, "target file is not source"
    real = [i for i in ids if i.lower() not in STOPWORDS and len(i) > 1]
    if not real:
        return False, "every identifier is a stopword"
    # The explanation names identifiers; each one it names must be in the diff.
    diff = row.get("diff") or ""
    named = re.findall(r"`([^`]+)`", t.get("explanation") or "")
    ungrounded = [n for n in named if n not in diff]
    if ungrounded:
        return False, f"explanation names {ungrounded[0]!r}, absent from the diff"
    return True, ""


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=ROOT / "data/sft_repair.jsonl")
    ap.add_argument("--out", type=Path, default=ROOT / "data/sft_repair_clean.jsonl")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--seed", type=int, default=20260901)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.src) if l.strip()]
    kept, dropped, why = [], [], Counter()
    for r in rows:
        ok, reason = keep(r)
        (kept if ok else dropped).append(r)
        if not ok:
            why[reason.split(",")[0]] += 1

    print(f"{len(rows)} in -> {len(kept)} kept, {len(dropped)} dropped")
    for reason, n in why.most_common():
        print(f"    {n:>4}  {reason}")

    # restore 30:70 by subsampling the clean class, stratified on churn bin so
    # the hard-negative matching done upstream is not undone here
    import random
    rng = random.Random(args.seed)
    dfc = [r for r in kept if r["label"] == 1]
    cln = [r for r in kept if r["label"] == 0]
    want = round(len(dfc) * (1 - DEFECT_SHARE) / DEFECT_SHARE)
    if len(cln) > want:
        by_bin: dict = {}
        for r in cln:
            by_bin.setdefault(min(6, r["n_lines"] // 40), []).append(r)
        for v in by_bin.values():
            rng.shuffle(v)
        picked, i = [], 0
        while len(picked) < want and any(by_bin.values()):
            for b in sorted(by_bin):
                if by_bin[b] and len(picked) < want:
                    picked.append(by_bin[b].pop())
            i += 1
        print(f"  clean subsampled {len(cln)} -> {len(picked)} to restore "
              f"{DEFECT_SHARE:.0%}/{1-DEFECT_SHARE:.0%}")
        cln = picked
    kept = dfc + cln
    rng.shuffle(kept)
    d = len(dfc)
    print(f"  {d} defective ({100*d//max(1,len(kept))}%) / {len(kept)-d} clean")

    if args.report:
        print("\n--- dropped ---")
        for r in dropped[:12]:
            print(f"  {r['rev'][:10]} {keep(r)[1][:60]:<62}"
                  f"{(r['target'].get('affected_identifiers') or [])[:4]}")
        return
    with open(args.out, "w") as fh:
        for r in kept:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
