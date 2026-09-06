"""Mine ordinary, non-defect-introducing commits from real repositories.

    python -m dataset_builder.mine_clean_commits --sample 80
    python -m dataset_builder.mine_clean_commits --sample 80 --report   # no write

Why this exists
---------------
`data/sft_v6_suggest.jsonl` is 366 records of buggy diffs and clean VARIANTS of
buggy diffs - renames and fix-reversions of 5-8 line invented functions. It
contains no example of an ordinary commit with nothing to flag: no feature
addition, no CI change, no docs update, no annotation pass, no dependency bump.

The 1 Sep hand-grade measured what that costs. On 40 real commits the tuned
model flagged 29 (seed 42) and 22 (seed 7), almost all of them ordinary, with
1 correct finding apiece. The base model flagged 9 of 40 with 0 correct - so a
3B CAN be quiet here, and fine-tuning is what made it loud. The failure is not
that the model cannot detect; it is that it has never been shown that "a new
function was added and nothing is wrong" is a valid answer.

Project selection
-----------------
Two exclusions, and both matter:

  HELD_OUT      the five projects the 40 graded commits came from. Training on
                other commits from axios or gin would leak project style into
                the only real-world test set there is.
  GATE_TRAINED  the Apache projects in `data/apachejit_commits.jsonl`, which
                trained the stage-1 gate. Reusing them couples the two stages'
                training distributions and makes any later gate measurement on
                this corpus uninterpretable.

What "clean" means here, and what it does not
---------------------------------------------
Nothing is executed and no defect labels exist for these commits. The shapes
below are selected because they are *unlikely to introduce a defect*, not
because any have been proven not to - a docs commit can still break a build.
Every record is therefore a CANDIDATE. `--report` prints the sample for reading
before anything is turned into a training target, and the shape is recorded on
each record so a later pass can drop a category that turns out to be noisy.
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REPOS = ROOT / "data" / "repos"

# Test set. Never mine these.
HELD_OUT = {"axios__axios", "clap-rs__clap", "gin-gonic__gin",
            "fastapi__fastapi", "spring-projects__spring-boot"}

# Stage-1 gate training set (apachejit). Keeping the stages' data disjoint is
# what lets a gate result on this corpus mean anything later.
GATE_TRAINED = {
    "apache__camel", "apache__ignite", "apache__cassandra", "apache__groovy",
    "apache__hbase", "apache__hadoop", "apache__flink", "apache__activemq",
    "apache__hive", "apache__kafka", "apache__zeppelin", "apache__zookeeper",
    "apache__spark", "apache__hadoop-hdfs", "apache__hadoop-mapreduce",
}

LANG_BY_EXT = {".js": "javascript", ".mjs": "javascript", ".ts": "typescript",
               ".rs": "rust", ".go": "go", ".py": "python", ".java": "java",
               ".php": "php", ".rb": "ruby"}

MAX_DIFF_CHARS = 6000
MIN_DIFF_CHARS = 120
MAX_FILES = 5

# The shapes the corpus is missing, in the order they are tried. Each is a
# (name, subject regex) pair; a commit is classified by the FIRST that matches,
# so the more specific patterns come first.
# Subject patterns, tried only AFTER the file-path rules below. Subjects lie:
# "style: simplify string formatting" was classified ci_config because "format"
# appears in the CI pattern, and a docs commit that mentions CI in passing went
# the same way. What a commit TOUCHES is far more reliable than what it says.
SHAPES = [
    ("feature",    re.compile(r"^feat|^add\b|adding\b|introduce|support for|"
                              r"implement", re.I)),
    ("refactor",   re.compile(r"^refactor|^style\b|^cleanup|polish|rename|"
                              r"simplify|tidy|extract|move\b|inline\b", re.I)),
    ("dependency", re.compile(r"^(deps|dep)\b|bump|upgrade|dependenc", re.I)),
    ("release",    re.compile(r"^release\b|^v?\d+\.\d+\.\d|version \d", re.I)),
    ("docs",       re.compile(r"^(docs?|doc)\b|\bREADME\b|typo|comment", re.I)),
    ("test",       re.compile(r"^tests?\b|add(ing)? tests?|spec\b", re.I)),
    ("ci_config",  re.compile(r"^(ci|build|chore|infra)\b|workflow", re.I)),
]

DOC_SUFFIX = {".md", ".rst", ".txt", ".adoc"}
DEP_FILES = {"package.json", "package-lock.json", "yarn.lock", "go.mod",
             "go.sum", "cargo.toml", "cargo.lock", "pom.xml", "composer.json",
             "gemfile", "gemfile.lock", "requirements.txt", "pyproject.toml"}
CI_HINT = (".github/", ".circleci/", ".travis", "dockerfile", "makefile",
           "jenkinsfile", ".gitlab-ci")


def shape_from_files(files: list[str]) -> str | None:
    """Classify on what the commit touches. Decisive when every file agrees."""
    low = [f.lower() for f in files]
    if all(Path(f).suffix in DOC_SUFFIX or "/doc" in f or f.startswith("doc")
           for f in low):
        return "docs"
    if all(("test" in f or "spec" in f) for f in low):
        return "test"
    if all(Path(f).name in DEP_FILES for f in low):
        return "dependency"
    if all(any(h in f for h in CI_HINT) or f.endswith((".yml", ".yaml"))
           for f in low):
        return "ci_config"
    return None

# Anything that reads like a repair is EXCLUDED, not labelled clean. A fix
# commit is by definition adjacent to a defect, and the corpus already has 84
# post-fixes targets built from cases whose defect is known. Guessing here would
# put unverified fix/break direction labels into training data.
FIXY = re.compile(r"\bfix|\bbug\b|regress|revert|patch\b|CVE-|security|"
                  r"crash|leak|overflow|npe\b|null pointer", re.I)


def git(repo: Path, args: list[str]) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True).stdout


def classify(subject: str, files: list[str]) -> str | None:
    if FIXY.search(subject):
        return None
    by_files = shape_from_files(files)
    if by_files:
        return by_files
    for name, pat in SHAPES:
        if pat.search(subject):
            return name
    return None


def candidate_projects() -> list[str]:
    if not REPOS.exists():
        return []
    out = []
    for d in sorted(REPOS.iterdir()):
        if not d.is_dir() or d.name in HELD_OUT or d.name in GATE_TRAINED:
            continue
        if (d / ".git").exists() or (d / "HEAD").exists():
            out.append(d.name)
    return out


# Shapes whose target text has to name real code. For docs/CI/dependency/release
# "nothing to execute, only <file> changed" is a TRUE and sufficient thing to
# say; for a feature or a refactor it is filler. Measured on the first 80-record
# draw: 40 of them were feature/refactor/test with no extractable definition in
# their own entry file, so half the corpus would have carried vague text about
# real code - which is v4's templating failure rebuilt, one field over.
NEEDS_A_NAME = {"feature", "refactor", "test"}


def describable(rec: dict) -> bool:
    """Can a target name a definition this commit adds or removes?"""
    if rec["shape"] not in NEEDS_A_NAME:
        return True
    from dataset_builder.build_clean_targets import (changed_lines, defs_in,
                                                     entry_file, hunks_for)
    scoped = hunks_for(rec["diff"], entry_file(rec)) or rec["diff"]
    return bool(defs_in(changed_lines(scoped, "+", code_only=True))
                or defs_in(changed_lines(scoped, "-", code_only=True)))


def commit_record(repo: Path, project: str, rev: str) -> dict | None:
    subject = git(repo, ["show", "-s", "--format=%s", rev]).strip()
    files = [f for f in git(repo, ["show", "--format=", "--name-only", rev]).split()
             if f]
    if not files or len(files) > MAX_FILES:
        return None
    shape = classify(subject, files)
    if shape is None:
        return None
    langs = {LANG_BY_EXT[Path(f).suffix] for f in files
             if Path(f).suffix in LANG_BY_EXT}
    diff = git(repo, ["show", "--format=", "--unified=3", rev])
    if not (MIN_DIFF_CHARS <= len(diff) <= MAX_DIFF_CHARS):
        return None
    return {"project": project, "rev": rev, "subject": subject,
            "date": git(repo, ["show", "-s", "--format=%cI", rev]).strip(),
            "files": files, "shape": shape,
            # docs/ci commits legitimately touch no code file; the language is
            # recorded as "" rather than dropping them, because "a commit that
            # changes no code is not a defect" is exactly a lesson worth teaching.
            "language": sorted(langs)[0] if langs else "",
            "diff": diff}


# Target mix. Deliberately NOT the natural frequency of these shapes in git
# history, where dependency bumps and CI edits dominate. It mirrors the shapes
# that actually drew false alarms in the 1 Sep hand-grade:
#
#   feature   gin AbortWithStatusPureJSON / LINK+UNLINK / form bindings,
#             clap NonEmptyStringValueParser  - pure additions, all flagged
#   refactor  gin response_writer + writeHeaders, clap trait rename  - all flagged
#   ci_config fastapi "Add support for Python 3.14"  - flagged, twice, identically
#   docs      fastapi docs_src update and the JWT timing-attack docs  - flagged,
#             the second reported as an authentication bypass
#
# A corpus of dependency bumps would teach the easy half of the lesson.
QUOTA = {"feature": 0.30, "refactor": 0.20, "ci_config": 0.15, "docs": 0.15,
         "test": 0.10, "dependency": 0.05, "release": 0.05}

# Most records should carry real code. A model that only ever saw YAML and
# markdown under "nothing to flag" would learn a file-extension rule, which is
# not the lesson - `feature` and `refactor` commits are the ones that matter and
# they are code by definition.
MIN_CODE_FRACTION = 0.6

# Languages to mine, via --languages. The default is every language the v6
# corpus contains, in the proportions IT has, because the clean:buggy ratio per
# language is the thing that must not skew: a language seen only as clean (or
# only as buggy) lets the model decide from the file extension. The corpus is
#   python 21%  javascript 17%  ruby 17%  java 13%
#   php 11%     c 8%            go 8%     rust 4%   typescript 1%
# and it contains NO C++ at all, so mining C++ would give the model a language
# it has never seen labelled buggy. Narrowing the set is fine; the languages
# left out simply keep today's buggy-only treatment. Adding one that is not in
# the corpus is not.
CORPUS_SHARE = {"python": 0.21, "javascript": 0.17, "ruby": 0.17, "java": 0.13,
                "php": 0.11, "c": 0.08, "go": 0.08, "rust": 0.04,
                "typescript": 0.01}


def collect(seed: int, per_project: int = 40) -> list[dict]:
    """Gather far more candidates than needed, so the quota has something to pick from."""
    rng = random.Random(seed)
    picked: list[dict] = []
    for project in candidate_projects():
        repo = REPOS / project
        revs = [r for r in git(repo, ["log", "--no-merges", "-n4000",
                                      "--format=%H"]).split() if r]
        rng.shuffle(revs)
        taken = 0
        for rev in revs:
            if taken >= per_project:
                break
            rec = commit_record(repo, project, rev)
            if rec and describable(rec):
                picked.append(rec)
                taken += 1
        print(f"  {project:<28} {taken:>3} candidates of {len(revs)} revisions")
    return picked


def sample(n: int, seed: int, languages: set[str] | None = None) -> list[dict]:
    """Draw `n` records balanced by LANGUAGE first, then by shape within each.

    Language is the primary constraint because it is the one that can become a
    shortcut: a language the model only ever sees clean (or only ever buggy) is
    decidable from the file extension. Shape is balanced within each language,
    best-effort - a thin pool cannot always supply both.

    Record counts follow the corpus's own per-language shares, renormalised over
    whatever subset is requested, so no language's clean:buggy ratio moves.
    """
    rng = random.Random(seed)
    pool = collect(seed)
    if languages:
        unknown = languages - set(CORPUS_SHARE)
        if unknown:
            print(f"  !! {', '.join(sorted(unknown))} is not in the SFT corpus. "
                  f"Mining a language the model has never seen labelled buggy "
                  f"teaches it to decide from the file extension.")
        pool = [r for r in pool if not r["language"] or r["language"] in languages]
    if not pool:
        return []

    langs = languages or set(CORPUS_SHARE)
    langs = {l for l in langs if l in CORPUS_SHARE}
    total_share = sum(CORPUS_SHARE[l] for l in langs) or 1.0

    # A fifth of the draw is code-free (docs, CI, dependency bumps). Those are a
    # real and frequently mis-flagged shape, but they belong to no language, so
    # letting them float would quietly dilute every language target.
    n_nocode = round(n * 0.2)
    n_code = n - n_nocode

    def take(rows: list[dict], want: int) -> list[dict]:
        """Round-robin by project, shape-balanced, deterministic."""
        if want <= 0 or not rows:
            return []
        by_shape: dict[str, list[dict]] = {}
        for r in rows:
            by_shape.setdefault(r["shape"], []).append(r)
        for v in by_shape.values():
            rng.shuffle(v)
            seen: Counter = Counter()
            v.sort(key=lambda r: seen.update([r["project"]]) or seen[r["project"]])
        # Allocate per shape by QUOTA WEIGHT, not evenly. Cycling one-at-a-time
        # equalises the shapes instead of weighting them: it took `test` from 8
        # to 19 and `feature` from 24 to 13, inverting the mix the quota exists
        # to produce.
        order = [s for s, _ in sorted(QUOTA.items(), key=lambda kv: -kv[1])]
        idx = {s: 0 for s in order}
        out: list[dict] = []
        for shp in order:
            rows_s = by_shape.get(shp, [])
            n_shp = min(round(want * QUOTA[shp]), len(rows_s))
            out.extend(rows_s[:n_shp])
            idx[shp] = n_shp
        # Top up from whatever is left, so a shape running dry costs the draw
        # size rather than the whole record.
        while len(out) < want:
            progressed = False
            for shp in order:
                rows_s = by_shape.get(shp, [])
                if idx[shp] < len(rows_s) and len(out) < want:
                    out.append(rows_s[idx[shp]])
                    idx[shp] += 1
                    progressed = True
            if not progressed:
                break
        return out[:want]

    picked: list[dict] = []
    short: list[str] = []
    for lang in sorted(langs, key=lambda l: -CORPUS_SHARE[l]):
        want = round(n_code * CORPUS_SHARE[lang] / total_share)
        rows = [r for r in pool if r["language"] == lang]
        got = take(rows, want)
        picked.extend(got)
        if len(got) < want:
            short.append(f"{lang} {len(got)}/{want}")

    picked.extend(take([r for r in pool if not r["language"]], n_nocode))

    if short:
        print(f"  !! short of target: {', '.join(short)} — too few candidate "
              f"repos for those languages, so the draw is skewed toward the rest")
    return picked


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=80)
    ap.add_argument("--seed", type=int, default=20260901)
    ap.add_argument("--out", type=Path, default=ROOT / "data/clean_commits.jsonl")
    ap.add_argument("--languages", nargs="*", default=None,
                    help="restrict to these languages (default: all in the corpus)")
    ap.add_argument("--report", action="store_true",
                    help="print the sample and write nothing")
    args = ap.parse_args()

    projects = candidate_projects()
    print(f"{len(projects)} candidate projects "
          f"(excluded: {len(HELD_OUT)} held out, {len(GATE_TRAINED)} gate-trained)")
    rows = sample(args.sample, args.seed,
                  set(args.languages) if args.languages else None)
    if not rows:
        raise SystemExit("no candidates — is data/repos/ populated?")

    print(f"\n{len(rows)} candidates")
    print("  by shape:   ", dict(Counter(r["shape"] for r in rows).most_common()))
    print("  by language:", dict(Counter(r["language"] or "(none)"
                                         for r in rows).most_common()))
    if args.report:
        print(f"\n{'shape':<12}{'lang':<12}{'project':<24}subject")
        for r in sorted(rows, key=lambda x: (x["shape"], x["project"])):
            print(f"  {r['shape']:<12}{r['language'] or '-':<12}"
                  f"{r['project'][:22]:<24}{r['subject'][:58]}")
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n-> {args.out}")
    print("These are CANDIDATES. Read them before any becomes a training target.")


if __name__ == "__main__":
    main()
