"""Split a labelled corpus into train/heldout by PROJECT, not by commit.

A random commit split leaks: two commits touching the same file, or a fix and
its near-duplicate elsewhere in the same repo, land on both sides. Holding out
whole projects is the only split that makes "unseen code" mean it.

    python split_by_project.py data/labelled_all.jsonl \
        --holdout gin-gonic/gin pallets/flask axios/axios clap-rs/clap \
                  spring-projects/spring-boot \
        --train-out data/ml8_train.jsonl --heldout-out data/ml8_heldout.jsonl

    python split_by_project.py          # self-check
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path


def split(records: list[dict], holdout: set[str]) -> tuple[list[dict], list[dict]]:
    tr = [r for r in records if r.get("project") not in holdout]
    te = [r for r in records if r.get("project") in holdout]
    return tr, te


def summarise(name: str, rows: list[dict]) -> None:
    langs = collections.Counter(r.get("language", "?") for r in rows)
    buggy = sum(1 for r in rows if r.get("buggy"))
    print(f"{name:<10}{len(rows):>6} records  {buggy:>5} buggy ({100*buggy/max(len(rows),1):.1f}%)"
          f"  {len(set(r.get('project') for r in rows))} projects")
    print(f"{'':<10}{dict(langs.most_common())}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus", type=Path)
    ap.add_argument("--holdout", nargs="+", required=True, metavar="PROJECT")
    ap.add_argument("--train-out", type=Path, required=True)
    ap.add_argument("--heldout-out", type=Path, required=True)
    args = ap.parse_args(argv)

    records = [json.loads(l) for l in open(args.corpus) if l.strip()]
    known = {r.get("project") for r in records}
    missing = [p for p in args.holdout if p not in known]
    if missing:
        raise SystemExit(f"not in {args.corpus}: {', '.join(missing)}")

    tr, te = split(records, set(args.holdout))
    if not te:
        raise SystemExit("holdout is empty")
    for path, rows in ((args.train_out, tr), (args.heldout_out, te)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    summarise("train", tr)
    summarise("heldout", te)
    print(f"\n{args.train_out}  {args.heldout_out}")
    return 0


def _selftest() -> None:
    recs = [{"project": "a/x", "buggy": True}, {"project": "b/y", "buggy": False},
            {"project": "a/x", "buggy": False}]
    tr, te = split(recs, {"b/y"})
    assert len(tr) == 2 and len(te) == 1, (tr, te)
    assert all(r["project"] != "b/y" for r in tr)
    # A project named in the holdout must take every one of its records with it.
    tr, te = split(recs, {"a/x"})
    assert len(te) == 2 and len(tr) == 1
    print("split_by_project checks ok")


if __name__ == "__main__":
    sys.exit(main() if len(sys.argv) > 1 else (_selftest() or 0))
