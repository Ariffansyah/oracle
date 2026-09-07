#!/usr/bin/env python
"""What ORACLE would run in each repo, and what that command could prove.

    python bench/detect_probe.py ~/Documents
    python bench/detect_probe.py ~/Documents/booknesa --diffs

Two questions this answers at a glance. Which projects name a command ORACLE
can find -- a repo it cannot is one that asks the user before it can review
anything. And of those, which name a command that could only ever check STYLE:
those get a review that says behaviour was never checked, and no amount of
running it harder changes that.

`--diffs` additionally runs the diff-only claims over the repo's recent
commits, which is what ORACLE falls back on when the command measures nothing.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from oracle_reviewer.core import command_class, suggest_run       # noqa: E402
from oracle_reviewer.static_claims import (cosmetic_only,         # noqa: E402
                                           membership_changed,
                                           risky_edits,
                                           ui_text_change)


def repos(root: pathlib.Path) -> list[pathlib.Path]:
    if (root / ".git").exists():
        return [root]
    return sorted(d for d in root.iterdir()
                  if d.is_dir() and (d / ".git").exists())


def scan(root: pathlib.Path) -> None:
    rows = []
    for d in repos(root):
        cmd, why = suggest_run(str(d))
        rows.append((d.name, cmd, command_class(cmd) if cmd else "-", why))
    print(f"{'repo':26} {'command':34} {'proves':9} why")
    for n, c, k, w in rows:
        print(f"{n:26} {c or '(none — would ask)':34} {k:9} {w}")
    found = sum(1 for _, c, _, _ in rows if c)
    blind = sum(1 for _, _, k, _ in rows if k in ("style", "types", "build"))
    print(f"\n  a command was found     {found}/{len(rows)}")
    print(f"  ...that cannot see behaviour  {blind}"
          f"   (these get 'Behaviour Unchecked')")


def diffs(repo: pathlib.Path, n: int) -> None:
    """What the diff-only claims say about this repo's recent commits."""
    log = subprocess.run(["git", "-C", str(repo), "log", "--format=%h %s",
                          f"-n{n}"], capture_output=True, text=True).stdout
    print(f"\n{repo.name}: the last {n} commits, read from the diff alone\n")
    hit = 0
    for line in log.splitlines():
        sha, _, subject = line.partition(" ")
        d = subprocess.run(["git", "-C", str(repo), "diff", f"{sha}^..{sha}"],
                           capture_output=True, text=True).stdout
        claims = []
        if cosmetic_only(d):
            claims.append("PROVABLY SAFE")
        if ui_text_change(d):
            claims.append("UI TEXT")
        if membership_changed(d):
            claims.append("FILTER CHANGED")
        for h in risky_edits(d):
            claims.append("HAZARD: " + re.sub(r"^line \d+: ", "", h)[:58])
        hit += bool(claims)
        print(f"  {sha}  {subject[:44]:44} "
              f"{claims[0] if claims else '—'}")
        for extra in claims[1:]:
            print(f"  {'':52} {extra}")
    print(f"\n  {hit}/{len(log.splitlines())} got a claim without running anything")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=pathlib.Path)
    ap.add_argument("--diffs", action="store_true",
                    help="also read the recent commits for diff-only claims")
    ap.add_argument("-n", type=int, default=12)
    a = ap.parse_args()
    root = a.path.expanduser().resolve()
    scan(root)
    if a.diffs:
        for r in repos(root):
            diffs(r, a.n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
