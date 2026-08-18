"""Mine defect-labelled commits from any repository, in any language.

ApacheJIT is Java by construction, so a gate trained on it scores every
TypeScript commit the same way. This builds the equivalent corpus from repos you
choose, using the repository's own history as the label source:

    python -m corpus.mine --repos vercel/next.js,fastapi/fastapi --limit 400

How the labels are derived (SZZ, the standard approach):

  1. find fix commits      - message matches "fix #123", "fixes NPE", "bugfix"
  2. take the lines they deleted or changed
  3. `git blame` those lines in the fix's parent
  4. the commits that last touched them INTRODUCED the defect -> buggy

Everything else, sampled from the same history, is the clean class. Language
comes from the file extensions in the diff, so the corpus can be balanced or
filtered per language later.

Clones are full, without checkout: blame and `git show` read everything from
disk, so SZZ never waits on the network. A full next.js clone is ~1 GB; the
partial-clone trick saved disk but made blame fetch blobs one at a time over
HTTPS, which is why the runs never finished.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ROOT

CLONE_DIR = ROOT / "data" / "repos"
OUT_PATH = ROOT / "data" / "multilang_commits.jsonl"

# Deliberately conservative: a commit that merely mentions "fix" in passing is
# not evidence. Requiring a bug-ish noun or an issue reference cuts most noise.
FIX_RE = re.compile(
    r"\b(fix(e[sd])?|bugfix|hotfix|patch(ed)?|resolve[sd]?|correct(ed)?)\b"
    r"(?!\s+(typo|lint|format|style|doc|readme|comment|test))",
    re.IGNORECASE)
ISSUE_RE = re.compile(r"(#\d+|[A-Z]+-\d+)")

EXT_LANG = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".java": "java",
    ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp",
    ".cs": "csharp", ".kt": "kotlin", ".swift": "swift", ".scala": "scala",
}


def git(args: list[str], repo: Path, default: str | None = None) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        if default is None:
            raise RuntimeError(f"git {' '.join(args[:2])}: {proc.stderr.strip()[:150]}")
        return default
    return proc.stdout


def clone(slug: str, dest: Path) -> Path | None:
    """Full clone, no checkout. Blame must not fetch blobs over the network
    one commit at a time — a partial clone makes SZZ crawl (the original
    bottleneck: data/mined.jsonl stayed empty while runs sat on the network).

    Single-branch: SZZ blames the default branch's history only, and other
    branches can double the size of a repo like next.js (which is also why it
    sits last in DEFAULT_REPOS — the small repos finish first, and if the big
    clone times out the run still lands most of the corpus)."""
    target = dest / slug.replace("/", "__")
    if (target / ".git").exists():
        return target
    dest.mkdir(parents=True, exist_ok=True)
    print(f"  cloning {slug} …", flush=True)
    try:
        proc = subprocess.run(
            ["git", "clone", "--single-branch", "--no-checkout", "--quiet",
             f"https://github.com/{slug}.git", str(target)],
            capture_output=True, text=True, timeout=5400)
    except subprocess.TimeoutExpired:
        print(f"  {slug}: clone timed out, skipping")
        return None
    if proc.returncode != 0:
        print(f"  {slug}: clone failed ({proc.stderr.strip()[:100]})")
        return None
    return target


def language_of(files: list[str]) -> str:
    counts = Counter(EXT_LANG.get(Path(f).suffix.lower(), "other") for f in files)
    counts.pop("other", None)
    return counts.most_common(1)[0][0] if counts else "other"


def is_fix(subject: str) -> bool:
    return bool(FIX_RE.search(subject)) and (
        bool(ISSUE_RE.search(subject)) or len(subject) > 20)


def changed_files(repo: Path, sha: str) -> list[str]:
    out = git(["show", "--name-only", "--format=", sha], repo, default="")
    return [l.strip() for l in out.splitlines() if l.strip()]


def blame_origins(repo: Path, sha: str, limit_files: int = 5) -> set[str]:
    """Commits that last touched the lines this fix removed - SZZ's core step."""
    origins: set[str] = set()
    diff = git(["show", "--unified=0", "--format=", sha], repo, default="")

    path, old_start = None, None
    for line in diff.splitlines():
        if line.startswith("--- a/"):
            path = line[6:].strip()
        elif line.startswith("@@"):
            m = re.search(r"-(\d+)(?:,(\d+))?", line)
            old_start = (int(m.group(1)), int(m.group(2) or 1)) if m else None
        elif line.startswith("-") and not line.startswith("---") and path and old_start:
            start, count = old_start
            if count == 0:
                continue
            out = git(["blame", "-l", "--porcelain",
                       "-L", f"{start},{start + max(count - 1, 0)}",
                       f"{sha}^", "--", path], repo, default="")
            for bl in out.splitlines():
                if re.fullmatch(r"[0-9a-f]{40} \d+ \d+( \d+)?", bl.strip()):
                    origins.add(bl.split()[0])
            old_start = None
            if len(origins) > limit_files * 4:
                return origins
    return origins


def diff_of(repo: Path, sha: str) -> str:
    return git(["show", "--format=", "--unified=3", sha], repo, default="")


def mine_repo(slug: str, repo: Path, limit: int, max_diff: int, min_diff: int,
              rng: random.Random) -> list[dict]:
    log = git(["log", "--format=%H%x00%s", "-n", str(limit * 6)], repo, default="")
    commits = [line.split("\x00", 1) for line in log.splitlines() if "\x00" in line]
    if not commits:
        return []

    fixes = [(sha, subj) for sha, subj in commits if is_fix(subj)]
    print(f"  {slug}: {len(commits)} commits, {len(fixes)} look like fixes",
          flush=True)

    buggy: set[str] = set()
    for sha, _subj in fixes[: limit // 2]:
        try:
            buggy |= blame_origins(repo, sha)
        except Exception:
            continue

    known = {sha for sha, _ in commits}
    buggy &= known                      # ignore origins outside the window
    clean_pool = [s for s, _ in commits if s not in buggy]
    rng.shuffle(clean_pool)

    picked = [(s, True) for s in list(buggy)[: limit // 2]]
    picked += [(s, False) for s in clean_pool[: limit - len(picked)]]
    rng.shuffle(picked)

    out = []
    for sha, is_buggy in picked:
        diff = diff_of(repo, sha)
        if not (min_diff <= len(diff) <= max_diff):
            continue
        files = changed_files(repo, sha)
        language = language_of(files)
        if language == "other":
            # Changelogs, JSON and docs carry no defect to learn from, and they
            # dominated the first sample (28 of 36 records).
            continue
        subject = next((s for h, s in commits if h == sha), "")
        out.append({
            "commit_id": sha,
            "project": slug,
            "language": language,
            "buggy": is_buggy,
            "subject": subject,
            "files": files,
            "diff": diff,
        })
    return out


DEFAULT_REPOS = [
    # Deliberately spread across ecosystems, not one language with extra steps.
    # Small repos first: each is minutes to clone, and next.js is the only one
    # that can take over an hour - it goes last so a timeout costs nothing.
    "fastapi/fastapi",         # python
    "pallets/flask",           # python
    "expressjs/express",       # javascript
    "gin-gonic/gin",           # go
    "sinatra/sinatra",         # ruby
    "laravel/framework",       # php
    "tokio-rs/tokio",          # rust
    "spring-projects/spring-boot",  # java
    "vercel/next.js",          # typescript / react — largest, cloned last
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repos", default=",".join(DEFAULT_REPOS),
                    help="comma-separated owner/name slugs")
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--clone-dir", type=Path, default=CLONE_DIR)
    ap.add_argument("--limit", type=int, default=300, help="commits per repo")
    ap.add_argument("--max-diff-bytes", type=int, default=6000)
    ap.add_argument("--min-diff-bytes", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    slugs = [s.strip() for s in args.repos.split(",") if s.strip()]

    done = set()
    if args.out.exists():
        done = {json.loads(l)["commit_id"] for l in open(args.out) if l.strip()}
        print(f"{len(done)} commits already mined, skipping those")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    total, by_lang, by_label = 0, Counter(), Counter()

    with open(args.out, "a") as fh:
        for slug in slugs:
            repo = clone(slug, args.clone_dir)
            if repo is None:
                continue
            try:
                records = mine_repo(slug, repo, args.limit, args.max_diff_bytes,
                                    args.min_diff_bytes, rng)
            except Exception as e:
                print(f"  {slug}: {type(e).__name__}: {str(e)[:120]}")
                continue
            written = 0
            for rec in records:
                if rec["commit_id"] in done:
                    continue
                fh.write(json.dumps(rec) + "\n")
                done.add(rec["commit_id"])
                by_lang[rec["language"]] += 1
                by_label["buggy" if rec["buggy"] else "clean"] += 1
                written += 1
            fh.flush()
            total += written
            print(f"  {slug}: +{written} records", flush=True)

    print(f"\n{total} new records -> {args.out}")
    print("languages:", dict(by_lang.most_common()))
    print("labels:   ", dict(by_label))
    if total:
        print(f"next:\n  python -m ml_model.train_gate --jsonl {args.out} --ablate")
    return 0


if __name__ == "__main__":
    # The fix-detector decides the whole label set, so it gets the self-check.
    assert is_fix("fix: correct null check in parser #4821")
    assert is_fix("Fixes NPE when the cache misses")
    assert is_fix("bugfix: session expiry off by one")
    assert not is_fix("fix typo"), "typo fixes are not defects"
    assert not is_fix("fix lint"), "lint fixes are not defects"
    assert not is_fix("add tests for parser"), "not a fix at all"
    assert not is_fix("update docs")

    assert language_of(["a/b.tsx", "c/d.ts", "e.py"]) == "typescript"
    assert language_of(["main.go"]) == "go"
    assert language_of(["README.md"]) == "other"
    print("fix detection + language detection ok")
    raise SystemExit(main())
