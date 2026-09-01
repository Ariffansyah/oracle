"""Measure the `check` field itself: is it composed, or is it a template?

    python bench/check_field_audit.py --tags v4 v4_seed7 v6 v6_seed7

Why this script exists
----------------------
`bench/template_audit.py` scores copying over `summary` + `findings[].explanation`
and has never read `effect.check`. That is how the v4 corpus reached a training
run with a `check` field that was a per-category sentence in 357 of its 366
targets: the tool that measures recitation could not see the field, so the
defect did not appear in any number the plan was checked against.

Four things are measured here, and each one answers a question the copying
score cannot:

`distinct` / `distinct*`
    How many different `check` strings a checkpoint produced, raw and with the
    filename and the trailing token dump blanked. A field that is reasoned about varies with the case; a
    field that is recited does not - but every check names its own file, so the
    raw count is 46/46 even for a model emitting one sentence with a filename
    slot. `distinct*` is the number that means anything.

`saturation`
    The most common phrase across all answers, and its share. The v4 corpus put
    "the edit touches" in 97% of targets and the checkpoints pushed it to 100% -
    a model amplifying a corpus template past the corpus's own rate.

`cross-seed identity`
    How often two INDEPENDENTLY TRAINED seeds emit the byte-identical `check`
    on the same case. Two models that reason from a diff can agree on content
    and still differ in wording; two models reciting one corpus string agree on
    the bytes. Read against the same figure for `summary`, which is the control:
    v4's seeds matched on 30-59% of checks and 0/46 summaries.

`check_useful, with and without the trailing token list`
    The v4 corpus appended "- the edit touches `a`, `b`, `c`" to every check,
    and `_check_useful` grades by substring against the case's `must_mention`.
    So a token dump scores. Stripping it from the stored v4 answers drops
    mech_heldout from 20/21 to 11/21 and basic from 29/31 to 19/31: half the
    metric was the token list rather than the sentence. Any checkpoint whose two
    columns differ is being scored on a dump, not on a test.
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
DATA = ROOT / "data"

SETS = {"basic": ("basic_bench", "bench/basic"),
        "mech_heldout": ("heldout_mech", "bench/mechanism_heldout"),
        "clean_heldout": ("heldout_clean", "bench/clean_heldout")}

# The tail the v4 corpus appended to every check. Stripping it is what separates
# the sentence's score from the token dump's.
_TOKEN_TAIL = re.compile(r"\s*[—–-]\s*the edit touches\b.*$", re.S | re.I)

# Every check names the case's own file, so a raw distinct count is 46/46 for a
# checkpoint emitting one sentence with a filename slot - which is exactly what
# v4 does. Blank the filename first and the count measures the sentence.
_FILENAME = re.compile(r"\b[\w-]+\.(?:c|go|java|js|ts|php|py|rb|rs)\b")

WORD = re.compile(r"[a-z0-9_]+")


def load(stem: str, tag: str) -> list[dict]:
    p = DATA / f"{stem}_{tag}.jsonl"
    if not p.exists():
        return []
    with p.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def cases(root: str) -> dict[str, dict]:
    out = {}
    for meta in sorted((ROOT / root).glob("*/meta.json")):
        m = json.loads(meta.read_text())
        out[m["id"]] = m
    return out


def check_of(row: dict) -> str:
    pred = row.get("predicted")
    if not isinstance(pred, dict):
        return ""
    eff = pred.get("effect")
    return str(eff.get("check", "")) if isinstance(eff, dict) else ""


def summary_of(row: dict) -> str:
    pred = row.get("predicted")
    return str(pred.get("summary", "")) if isinstance(pred, dict) else ""


def top_phrase(texts: list[str], n: int = 4) -> tuple[str, int]:
    """The most repeated n-word phrase across a set of answers, and its count.

    Counted once per answer, so one answer repeating a phrase cannot inflate it.
    """
    c: Counter = Counter()
    for t in texts:
        toks = WORD.findall(t.lower())
        c.update({" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)})
    return c.most_common(1)[0] if c else ("", 0)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tags", nargs="+", required=True,
                    help="run tags, i.e. the suffix on data/basic_bench_<tag>.jsonl")
    ap.add_argument("--pairs", nargs="*", default=[],
                    help="seed pairs as TAG42:TAG7 for the cross-seed identity "
                         "check, e.g. v4:v4_seed7 v6:v6_seed7")
    args = ap.parse_args()

    from bench.basic_bench import _check_useful

    print(f"\n{'tag':<14}{'set':<14}{'n':>4}{'distinct':>9}{'distinct*':>10}"
          f"{'useful':>9}{'no tail':>9}   most repeated 4-gram")
    print("-" * 108)
    for tag in args.tags:
        for label, (stem, root) in SETS.items():
            rows = load(stem, tag)
            if not rows:
                continue
            cs = cases(root)
            checks = [check_of(r) for r in rows]
            checks = [c for c in checks if c]
            if not checks:
                continue
            full = bare = graded = 0
            for r in rows:
                c = cs.get(r["id"])
                chk = check_of(r)
                if not c or not c.get("buggy") or not chk:
                    continue
                graded += 1
                full += bool(_check_useful(c, chk))
                bare += bool(_check_useful(c, _TOKEN_TAIL.sub("", chk)))
            phrase, hits = top_phrase(checks)
            useful = f"{full}/{graded}" if graded else "n/a"
            notail = f"{bare}/{graded}" if graded else "n/a"
            # Blank BOTH the filename and the token dump: what is left is the
            # sentence, which is the thing that is supposed to vary with the
            # case. v4 keeps a high raw count purely because the dump differs.
            anon = {_FILENAME.sub("F", _TOKEN_TAIL.sub("", c)) for c in checks}
            print(f"{tag:<14}{label:<14}{len(checks):>4}"
                  f"{len(set(checks)):>9}{len(anon):>10}"
                  f"{useful:>9}{notail:>9}   "
                  f"{hits}/{len(checks)} \"{phrase}\"")

    if args.pairs:
        print(f"\ncross-seed byte identity — two independently trained seeds, "
              f"same case")
        print(f"{'pair':<22}{'set':<14}{'check':>12}{'summary':>12}"
              f"   (summary is the control)")
        print("-" * 78)
        for spec in args.pairs:
            a, _, b = spec.partition(":")
            for label, (stem, _root) in SETS.items():
                ra, rb = load(stem, a), load(stem, b)
                if not (ra and rb):
                    continue
                ib = {r["id"]: r for r in rb}
                shared = [r for r in ra if r["id"] in ib]
                if not shared:
                    continue
                ck = sum(1 for r in shared
                         if check_of(r) and check_of(r) == check_of(ib[r["id"]]))
                sm = sum(1 for r in shared
                         if summary_of(r) and summary_of(r) == summary_of(ib[r["id"]]))
                print(f"{a + '/' + b:<22}{label:<14}"
                      f"{f'{ck}/{len(shared)}':>12}{f'{sm}/{len(shared)}':>12}")


if __name__ == "__main__":
    main()
