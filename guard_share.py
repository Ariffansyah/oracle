"""Guard-class share of the findings in a labelled corpus.

Step 2 of the guard-corpus plan: the whole point of mining guard-adding fixes
was to raise the share of findings that describe a *missing check*. One script
for every corpus so the numbers compare; the earlier 20.7% in RESULTS came from
an ad-hoc regex typed at a shell, which is why it could not be compared to the
hand count before it.

    .venv/bin/python guard_share.py data/labelled_multilang.jsonl data/labelled_guards.jsonl

A finding counts as guard-flavoured when the regex below matches its category or
its explanation. The regex is broad on purpose: it is a trend line between
corpora built the same way, not a precision instrument.
"""

import json
import re
import sys
from collections import Counter

GUARD_RE = re.compile(
    r"guard|missing check|missing.{0,12}(check|validation)|nil check|null check|"
    r"unchecked|without check|no check|validat|sanitiz|bounds|out of range|"
    r"divide by zero|division by zero|zero.{0,10}(check|divisor)|"
    r"empty (check|string|slice|list)|(nil|null)[ -]?(pointer|deref)",
    re.I,
)


def scan(path):
    findings, guards, cats, guard_cats = 0, 0, Counter(), Counter()
    records = 0
    with open(path) as fh:
        for line in fh:
            records += 1
            for f in json.loads(line)["analysis"].get("findings") or []:
                findings += 1
                cat = f.get("category", "?")
                cats[cat] += 1
                if GUARD_RE.search(cat + " " + f.get("explanation", "")):
                    guards += 1
                    guard_cats[cat] += 1
    return records, findings, guards, cats, guard_cats


def main(paths):
    for path in paths:
        records, findings, guards, cats, guard_cats = scan(path)
        pct = 100 * guards / findings if findings else 0
        print(f"\n{path}")
        print(f"  {records} records, {findings} findings, {guards} guard-flavoured ({pct:.1f}%)")
        for cat, n in cats.most_common():
            print(f"    {cat:20s} {n:4d}  guard {guard_cats[cat]:4d}")


def demo():
    assert GUARD_RE.search("no nil check before dereference")
    assert GUARD_RE.search("input-validation")
    assert GUARD_RE.search("null-dereference")  # the hyphenated category name
    assert GUARD_RE.search("divisor may be zero, causing a division by zero panic")
    assert not GUARD_RE.search("api-misuse the parameter order shifted")
    print("ok")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args) if args else demo()
