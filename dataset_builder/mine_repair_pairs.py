"""Pair each repair with the commit that introduced what it repaired (SZZ).

    python -m dataset_builder.mine_repair_pairs --repos apache__zookeeper --report
    python -m dataset_builder.mine_repair_pairs --sample 400

Why this exists
---------------
The 1 Sep hand-grade is the project's strongest evidence and its weakest
methodology: 40 commits, one grader, nothing executed. It does not scale, and
"single annotator" is the first thing an examiner will push on.

For a commit that induced a defect, a later commit REPAIRED it - and that
repair's diff is an objective answer key for the explanation, not just for the
verdict. Prior JIT work cannot use this, because a probability has nothing to
compare against. `evaluate.py:fix_agreement` was written for exactly this and
has sat inert since 26 Aug because no dataset carried a `fix_diff`.

This builds that dataset. Nothing here is hand-labelled.

What SZZ gets wrong, and what is done about it
----------------------------------------------
The naive version - blame every line a fix deleted - paired 31 of 60 fixes on
zookeeper and pulled `assertThat` and `format` out of test files as if they were
the defect. The literature puts SZZ precision around 50-70%, so the refinements
below are not polish; they are most of the signal:

  production files only   a fix's test changes are how it PROVES the repair, not
                          where the defect lived. Test hunks were the single
                          biggest source of junk identifiers in the probe.
  no whitespace/comment   a reformatted line blames whoever last reformatted it
  no merges, no reverts   a merge introduces nothing; a revert's "fix" is the
                          revert itself
  date sanity             a commit dated after the fix cannot have induced it -
                          blame can still return one through a rebase or a
                          rewritten history
  bounded fan-out         a fix touching 40 files blames 40 unrelated authors;
                          those pairs are noise and are dropped rather than kept
                          at low weight
  evidence kept           every pair records WHICH lines and files justified it,
                          so a later filter can tighten without re-mining

Even so the output is noisy supervision, not ground truth. That belongs in the
threats-to-validity section, not in a footnote.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REPOS = ROOT / "data" / "repos"

# A fix that names an issue is far more likely to be a real repair than one that
# merely contains the word "fix" - "fix typo", "fix build" and "fix formatting"
# are not defect repairs. The issue key is the precision lever.
ISSUE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")
FIXY = re.compile(r"\bfix(e[sd])?\b|\bbug\b|\bresolve[sd]?\b|\bcorrect(s|ed)?\b", re.I)
# Things that look like fixes and are not defect repairs.
NOT_A_DEFECT = re.compile(
    r"\btypo\b|\bformatting\b|\bcheckstyle\b|\blicen[cs]e\b|\bjavadoc\b|"
    r"\bcomment\b|\bspelling\b|\bwhitespace\b|\bimport(s)?\b|\brevert\b|"
    r"\bversion\b|\brelease\b|\bchangelog\b", re.I)

SRC_EXT = {".java", ".py", ".js", ".mjs", ".ts", ".go", ".rb", ".php", ".c", ".rs"}
TEST_PATH = re.compile(r"(^|/)(test|tests|spec|__tests__|testing)/|"
                       r"(Test|Tests|IT)\.java$|_test\.|test_|\.spec\.|\.test\.")

MAX_FIX_FILES = 8        # beyond this a "fix" is a refactor sweep
MAX_BLAME_LINES = 40     # per file, keeps blame bounded on huge hunks
MIN_EVIDENCE = 2         # lines a candidate must explain to be believed


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True).stdout.decode("utf8", "replace")


def is_source(path: str) -> bool:
    return Path(path).suffix in SRC_EXT and not TEST_PATH.search(path)


def meaningful(line: str) -> bool:
    """A removed line that could carry a defect: not blank, not a comment."""
    s = line.strip()
    if not s:
        return False
    return not s.startswith(("//", "#", "/*", "*", "*/", "<!--"))


def fix_commits(repo: Path, limit: int) -> list[tuple[str, str]]:
    out = []
    for line in git(repo, "log", "--no-merges", f"-n{limit}",
                    "--format=%H%x00%s").splitlines():
        h, _, subj = line.partition("\x00")
        if not h or not FIXY.search(subj) or NOT_A_DEFECT.search(subj):
            continue
        out.append((h, subj))
    return out


def removed_ranges(repo: Path, rev: str) -> dict[str, list[tuple[int, int]]]:
    """Per source file, the pre-image line ranges the fix removed or replaced."""
    diff = git(repo, "show", "--format=", "--unified=0", rev)
    ranges: dict[str, list[tuple[int, int]]] = defaultdict(list)
    cur = None
    pending: list[str] = []
    start = n = 0
    for line in diff.splitlines():
        m = re.match(r"^\+\+\+ b/(.+)$", line)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r"^@@ -(\d+)(?:,(\d+))? ", line)
        if m:
            if cur and pending and any(meaningful(x) for x in pending) and n:
                ranges[cur].append((start, n))
            start, n, pending = int(m.group(1)), int(m.group(2) or 1), []
            continue
        if line.startswith("-") and not line.startswith("---"):
            pending.append(line[1:])
    if cur and pending and any(meaningful(x) for x in pending) and n:
        ranges[cur].append((start, n))
    return {p: r for p, r in ranges.items() if is_source(p)}


def blame_candidates(repo: Path, rev: str, path: str,
                     ranges: list[tuple[int, int]]) -> Counter:
    """Commits that last touched the removed lines, weighted by line count."""
    found: Counter = Counter()
    spent = 0
    for start, n in ranges:
        if n <= 0 or spent >= MAX_BLAME_LINES:
            continue
        end = start + min(n, MAX_BLAME_LINES - spent) - 1
        spent += end - start + 1
        # -w ignores whitespace-only changes so a reformat does not take credit
        out = git(repo, "blame", "-w", "-l", f"-L{start},{end}", f"{rev}^", "--", path)
        for bl in out.splitlines():
            sha = bl.split(" ", 1)[0].lstrip("^")
            if len(sha) >= 20:
                found[sha] += 1
    return found


def pairs_for_repo(repo_name: str, limit: int, want: int) -> list[dict]:
    repo = REPOS / repo_name
    if not (repo / ".git").exists() and not (repo / "HEAD").exists():
        return []
    out: list[dict] = []
    for rev, subj in fix_commits(repo, limit):
        if len(out) >= want:
            break
        ranges = removed_ranges(repo, rev)
        if not ranges or len(ranges) > MAX_FIX_FILES:
            continue
        fix_date = git(repo, "show", "-s", "--format=%ct", rev).strip()
        if not fix_date.isdigit():
            continue
        cand: Counter = Counter()
        evidence: dict[str, list[str]] = defaultdict(list)
        for path, rs in list(ranges.items())[:MAX_FIX_FILES]:
            for sha, weight in blame_candidates(repo, rev, path, rs).items():
                cand[sha] += weight
                evidence[sha].append(path)
        for sha, weight in cand.most_common(3):
            if weight < MIN_EVIDENCE:
                continue
            d = git(repo, "show", "-s", "--format=%ct", sha).strip()
            # A commit dated after the repair cannot have induced it. Blame can
            # still return one through a rebase or rewritten history.
            if not d.isdigit() or int(d) >= int(fix_date):
                continue
            out.append({
                "project": repo_name,
                "fix": rev, "fix_subject": subj,
                "inducing": sha,
                "inducing_subject": git(repo, "show", "-s", "--format=%s", sha).strip(),
                "issue": (ISSUE.search(subj).group(0) if ISSUE.search(subj) else None),
                "lines_explained": weight,
                "files": sorted(set(evidence[sha])),
            })
            break                    # one inducing commit per fix, the strongest
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repos", nargs="*", default=None)
    ap.add_argument("--sample", type=int, default=400, help="pairs wanted in total")
    ap.add_argument("--scan", type=int, default=3000, help="revisions scanned per repo")
    ap.add_argument("--out", type=Path, default=ROOT / "data/repair_pairs.jsonl")
    ap.add_argument("--report", action="store_true", help="print, write nothing")
    args = ap.parse_args()

    repos = args.repos or sorted(
        d.name for d in REPOS.iterdir()
        if d.is_dir() and ((d / ".git").exists() or (d / "HEAD").exists()))
    per = max(1, args.sample // max(1, len(repos)))
    rows: list[dict] = []
    for r in repos:
        got = pairs_for_repo(r, args.scan, per)
        rows.extend(got)
        print(f"  {r:<30} {len(got):>4} pairs")

    print(f"\n{len(rows)} pairs")
    withissue = sum(1 for r in rows if r["issue"])
    print(f"  with an issue key   : {withissue} ({100*withissue//max(1,len(rows))}%)")
    print(f"  median lines blamed : "
          f"{sorted(r['lines_explained'] for r in rows)[len(rows)//2] if rows else 0}")
    if args.report:
        print(f"\n{'project':<24}{'fix':<12}{'induced-by':<12}{'ln':>3}  subject")
        for r in rows[:20]:
            print(f"  {r['project'][:22]:<24}{r['fix'][:10]:<12}"
                  f"{r['inducing'][:10]:<12}{r['lines_explained']:>3}  "
                  f"{r['fix_subject'][:48]}")
        return
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
