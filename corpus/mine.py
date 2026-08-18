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
GUARD_PATH = ROOT / "data" / "guard_commits.jsonl"

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
    # errors="replace": git hands back whatever bytes are in the tree, and a
    # single latin-1 source file in an old repo (apache/commons-lang) raised
    # UnicodeDecodeError out of subprocess and cost the whole repository's
    # slice. A mangled character in one diff line is not worth a missing
    # language.
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
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


# --- guard-adding fixes -------------------------------------------------
#
# RESULTS ("Prompt rules cannot move the SFT'd 3B") measured the gap this
# targets: the student never reports an *absent* guard, because every SFT
# target it saw describes wrongness on a line that changed. A fix that only
# ADDS a check is the mirror image of that - the defect is the missing line -
# so the commit it blames back to is exactly the training example that is
# missing. Mine those specifically rather than hoping a general sample
# contains enough of them (it did not: 7 of 141 findings, ~5%).

TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|spec|specs|__tests__|testdata|fixtures?|mocks?|examples?)(/|$)"
    r"|_test\.|\.test\.|\.spec\.|Test\.java$|Tests\.java$|_spec\.rb$",
    re.IGNORECASE)

# An added line only counts as a guard if it opens a conditional or bails out.
# Without this, "len(" matches every second line of ordinary code.
COND_RE = re.compile(
    r"^\s*[)}\]]*\s*(?:if|elif|elsif|else\s+if|unless|when|guard|match)\b"
    # Ruby and Rust write the guard after the statement: `return if x.nil?`,
    # `return Err(e) if ...`. Without this the whole Ruby slice mines empty.
    r"|^\s*(?:return|raise|next|break|redo|throw)\b.*\b(?:if|unless)\b")
EXIT_RE = re.compile(
    r"^\s*(?:return|raise|throw|panic!|abort|exit|next|redo)\b")
COMMENT_RE = re.compile(r"^\s*(?://|#|/\*|\*|--|<!--)")

# Ordered most-specific first; a line is labelled with every kind it matches.
GUARD_PATTERNS = [
    # The motivating case: a divisor, modulus or denominator checked for zero.
    ("zero-check", re.compile(
        r"[!=]=\s*0(?:\.0+)?\b|\bchecked_(?:div|rem)\b"
        r"|\bZeroDivisionError\b|\bdivid|\bdenominator\b")),
    # nil / null / None / undefined, named explicitly.
    ("nil-check", re.compile(
        r"[!=]=\s*(?:nil|null|None|undefined|NULL)\b"
        r"|\bis\s+(?:not\s+)?None\b|\.nil\?|\bisset\s*\(|\bis_null\s*\("
        r"|\bObjects\.requireNonNull\b|\bif\s+let\s+Some\b"
        r"|\.ok_or(?:_else)?\s*\(|\bhasOwnProperty\b")),
    # Go's error return and its cousins in other languages.
    ("error-check", re.compile(
        r"\berr(?:or)?\s*!=\s*nil\b|\.is_err\s*\(|\.is_none\s*\("
        r"|\bcatch\s*\(|\brescue\b")),
    # Index and range guards.
    ("bounds-check", re.compile(
        r"<\s*0\b|>=?\s*(?:len\s*\(|\w+\.length\b|\w+\.size\s*\(\s*\))"
        r"|\bIndexError\b|\bIndexOutOfBounds|\bout\s+of\s+range\b")),
    # Emptiness - the same defect one level up from nil.
    ("empty-check", re.compile(
        r"\blen\s*\(|\.length\b|\.is_empty\s*\(|\.empty\s*\(|\bempty\s*\("
        r"|\.blank\?|\.any\?|\bcount\s*\(|\bsize\s*\(\s*\)")),
    # `if (!x)` / `if not x` / `unless x` - the untyped null check.
    ("falsy-check", re.compile(r"\(\s*!\s*[\w.$]|\bnot\s+[\w.]|\bunless\b")),
    # An explicit rejection of bad input.
    ("validation-raise", re.compile(
        r"\braise\s+(?:ValueError|TypeError|ArgumentError|InvalidArgument)"
        r"|\bthrow\s+new\s+(?:IllegalArgumentException|InvalidArgumentException"
        r"|TypeError|RangeError|Error)\b|\bpanic!\s*\(")),
]


def guard_kinds(diff: str) -> set[str]:
    """Which guard classes this diff ADDS, ignoring test files.

    Only added lines are read, and only those that open a conditional or bail
    out early - a fix that merely mentions `len(` in a reworked expression has
    not added a guard.
    """
    kinds: set[str] = set()
    path, saw_cond = "", False
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path, saw_cond = line[6:].strip(), False
            continue
        if line.startswith(("--- ", "@@", "diff --git")):
            saw_cond = False
            continue
        if not line.startswith("+") or TEST_PATH_RE.search(path):
            continue
        text = line[1:]
        if COMMENT_RE.match(text):
            continue
        if COND_RE.match(text):
            saw_cond = True
            for kind, pat in GUARD_PATTERNS:
                if pat.search(text):
                    kinds.add(kind)
        elif saw_cond and EXIT_RE.match(text):
            # `if x == nil {` then `return ErrNoValue` - the bail-out can name
            # the defect class the condition line left implicit.
            for kind, pat in GUARD_PATTERNS:
                if pat.search(text):
                    kinds.add(kind)
        else:
            saw_cond = False
    return kinds


def blame_at(repo: Path, sha: str, path: str, start: int, end: int) -> set[str]:
    """Commits that last touched [start, end] of `path` in this commit's parent."""
    if start < 1 or end < start:
        return set()
    out = git(["blame", "-l", "--porcelain", "-L", f"{start},{end}",
               f"{sha}^", "--", path], repo, default="")
    return {bl.split()[0] for bl in out.splitlines()
            if re.fullmatch(r"[0-9a-f]{40} \d+ \d+( \d+)?", bl.strip())}


def blame_insertion_context(repo: Path, sha: str, window: int = 3,
                            max_hunks: int = 12) -> set[str]:
    """SZZ for a fix that only adds lines.

    `blame_origins` blames the lines a fix deleted, which is the right rule and
    useless here: a commit that only inserts a guard deletes nothing, so it
    returns an empty set for exactly the commits this mode is looking for.
    The line that should have been guarded is the one the guard was inserted
    next to, so blame a small window around each insertion point instead.
    """
    origins: set[str] = set()
    diff = git(["show", "--unified=0", "--format=", sha], repo, default="")
    path, hunks = "", 0
    for line in diff.splitlines():
        if line.startswith("--- a/"):
            path = line[6:].strip()
        elif line.startswith("--- /dev/null"):
            path = ""                      # a new file has no history to blame
        elif line.startswith("@@") and path and not TEST_PATH_RE.search(path):
            m = re.search(r"-(\d+)(?:,(\d+))?", line)
            if not m:
                continue
            start, count = int(m.group(1)), int(m.group(2) or 1)
            if count:                      # lines were replaced: blame them
                origins |= blame_at(repo, sha, path, start, start + count - 1)
            elif start:                    # pure insertion after old line `start`
                origins |= blame_at(repo, sha, path,
                                    max(start - window + 1, 1), start + window)
            hunks += 1
            if hunks >= max_hunks:
                break
    return origins


def mine_guard_fixes(slug: str, repo: Path, scan: int, max_diff: int,
                     min_diff: int, max_fix_diff: int) -> list[dict]:
    """Introducing commits behind fixes that add a missing guard."""
    log = git(["log", "--format=%H%x00%s", "-n", str(scan)], repo, default="")
    commits = [line.split("\x00", 1) for line in log.splitlines() if "\x00" in line]
    subjects = dict(commits)
    fixes = [(sha, subj) for sha, subj in commits if is_fix(subj)]

    guarded = []
    for sha, subj in fixes:
        fix_diff = git(["show", "--format=", "--unified=0", sha], repo, default="")
        # A focused fix is the evidence; a 500-line refactor that happens to
        # contain an `if` is not.
        if not fix_diff or len(fix_diff) > max_fix_diff:
            continue
        kinds = guard_kinds(fix_diff)
        if kinds:
            guarded.append((sha, subj, sorted(kinds)))
    print(f"  {slug}: {len(commits)} commits, {len(fixes)} fixes, "
          f"{len(guarded)} add a guard", flush=True)

    known = set(subjects)
    out, seen = [], set()
    for fix_sha, fix_subj, kinds in guarded:
        try:
            origins = blame_insertion_context(repo, fix_sha)
        except Exception:
            continue
        for sha in origins & known:
            if sha in seen or sha == fix_sha:
                continue
            seen.add(sha)
            diff = diff_of(repo, sha)
            if not (min_diff <= len(diff) <= max_diff):
                continue
            files = changed_files(repo, sha)
            language = language_of(files)
            if language == "other":
                continue
            out.append({
                "commit_id": sha,
                "project": slug,
                "language": language,
                "buggy": True,
                "subject": subjects.get(sha, ""),
                "files": files,
                "diff": diff,
                # Why this commit is here. Never reaches the teacher prompt -
                # build_user_message() sends diff, subject and files only - so
                # it is provenance and eval material, not a label leak.
                "guard_fix": True,
                "guard_kinds": kinds,
                "fix_commit": fix_sha,
                "fix_subject": fix_subj,
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
    ap.add_argument("--guards", action="store_true",
                    help="mine only the commits behind fixes that ADD a "
                         "missing guard (see mine_guard_fixes)")
    ap.add_argument("--scan", type=int, default=20000,
                    help="--guards: commits of history to read per repo")
    ap.add_argument("--max-fix-diff-bytes", type=int, default=4000,
                    help="--guards: ignore fixes larger than this, where an "
                         "added `if` is incidental rather than the point")
    ap.add_argument("--langs", default="",
                    help="comma- or space-separated languages to keep")
    args = ap.parse_args(argv)
    if args.guards and args.out == OUT_PATH:
        args.out = GUARD_PATH
    keep_langs = {l for l in re.split(r"[,\s]+", args.langs) if l}

    rng = random.Random(args.seed)
    slugs = [s.strip() for s in args.repos.split(",") if s.strip()]

    done = set()
    if args.out.exists():
        done = {json.loads(l)["commit_id"] for l in open(args.out) if l.strip()}
        print(f"{len(done)} commits already mined, skipping those")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    total, by_lang, by_label, by_kind = 0, Counter(), Counter(), Counter()

    with open(args.out, "a") as fh:
        for slug in slugs:
            repo = clone(slug, args.clone_dir)
            if repo is None:
                continue
            try:
                if args.guards:
                    records = mine_guard_fixes(
                        slug, repo, args.scan, args.max_diff_bytes,
                        args.min_diff_bytes, args.max_fix_diff_bytes)
                else:
                    records = mine_repo(slug, repo, args.limit,
                                        args.max_diff_bytes,
                                        args.min_diff_bytes, rng)
            except Exception as e:
                print(f"  {slug}: {type(e).__name__}: {str(e)[:120]}")
                continue
            written = 0
            for rec in records:
                if rec["commit_id"] in done:
                    continue
                if keep_langs and rec["language"] not in keep_langs:
                    continue
                fh.write(json.dumps(rec) + "\n")
                done.add(rec["commit_id"])
                by_lang[rec["language"]] += 1
                by_label["buggy" if rec["buggy"] else "clean"] += 1
                by_kind.update(rec.get("guard_kinds", []))
                written += 1
            fh.flush()
            total += written
            print(f"  {slug}: +{written} records", flush=True)

    print(f"\n{total} new records -> {args.out}")
    print("languages:", dict(by_lang.most_common()))
    print("labels:   ", dict(by_label))
    if by_kind:
        print("guards:   ", dict(by_kind.most_common()))
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

    # guard_kinds decides which commits the targeted mine keeps, so it gets one
    # real hunk per language rather than a synthetic string.
    def kinds(body: str) -> set[str]:
        return guard_kinds("diff --git a/x b/x\n+++ b/x\n@@ -1 +1 @@\n" + body)

    assert "zero-check" in kinds("+    if divisor == 0:\n"
                                 "+        raise ValueError('no')"), "python div"
    assert "error-check" in kinds("+\tif err != nil {\n+\t\treturn err\n+\t}"), "go err"
    assert "nil-check" in kinds("+  if (user == null) {\n+    return;\n+  }"), "java nil"
    assert "falsy-check" in kinds("+  if (!options) return {};"), "js falsy"
    assert "nil-check" in kinds("+    if (!isset($row['id'])) {"), "php isset"
    assert "nil-check" in kinds("+    if let Some(v) = maybe {"), "rust option"
    assert "nil-check" in kinds("+    return if value.nil?"), "ruby nil"
    assert "bounds-check" in kinds("+  if (i < 0 || i >= arr.length) {"), "ts bounds"

    # Only added lines, only guards, and never a test file.
    assert not kinds("+    total = len(items) + 1"), "not a conditional"
    assert not kinds("-    if x == 0:\n-        return"), "removed, not added"
    assert not kinds("+    # if x == 0: guard here later"), "a comment is not code"
    assert not guard_kinds("diff --git a/t b/t\n+++ b/spec/user_spec.rb\n"
                           "@@ -1 +1 @@\n+  if user.nil?"), "tests excluded"
    assert TEST_PATH_RE.search("pkg/thing_test.go") and \
        TEST_PATH_RE.search("src/__tests__/a.js") and \
        not TEST_PATH_RE.search("src/latest/a.js"), "test paths"
    print("fix detection + language detection + guard detection ok")
    raise SystemExit(main())
