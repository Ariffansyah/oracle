"""Turn SZZ output into a filtered, class-balanced JIT dataset.

    python -m dataset_builder.build_jit_dataset --bic out/bic_ma_*.json --report
    python -m dataset_builder.build_jit_dataset --bic out/bic_ma_*.json --out data/jit_dataset.jsonl

Why the filters and the ratio are what they are
------------------------------------------------
NOISE. Even refactoring-aware SZZ hands back commits whose diff is cosmetic, and
a 3B model cannot track a 40-file change without inventing things. Every filter
here is deterministic and drops LOW-SIGNAL commits, not inconvenient ones:

  comment/docstring/blank only   a diff with no executable change cannot induce
                                 a defect, whatever blame says
  metadata and build files       .gitignore, README, package.json, setup.py -
                                 no runtime behaviour to get wrong
  import-only                    moving imports is not a defect mechanism
  churn ceiling                  >500 changed lines or >5 files. Measured on the
                                 1 Sep hand-grade: fabrication rose sharply on
                                 the larger diffs, and a scattered change gives
                                 the model more surface to invent from

BALANCE. NOT 1:1. The v6 corpus is 48% defective / 52% clean, and the model
trained on it flags 29 of 40 real commits while the untuned base model flags 9.
A balanced corpus teaches the model that flagging is half the answer. The
natural rate is ~10% defective; 30/70 keeps enough positives to learn from
without teaching that reflex.

HARD NEGATIVES. A clean commit drawn at random is an easy negative: if the
defective ones are large and branch-heavy and the clean ones are one-line
renames, the model learns "big diff = bug" and scores well without reading
anything. So clean commits are sampled to MATCH the defective distribution on:

  churn      stratified over the same line-count bins
  structure  the same share touching conditionals, loops or arithmetic

What "clean" cannot mean here
-----------------------------
A commit no fix has blamed is not proven defect-free - it may induce a defect
nobody has fixed yet. This is the standard SZZ limitation and it belongs in
threats to validity, not in a footnote: the negative class is "not known to be
defect-inducing", which is weaker than "clean".
"""
from __future__ import annotations

import argparse
import glob
import json
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REPOS = ROOT / "data" / "repos"

MAX_LINES = 500
MAX_FILES = 5
DEFECT_SHARE = 0.30

# Target languages only. PySZZ parses comments natively for .py and .js, and
# this project patched .java onto tree-sitter - but .c/.h/.cpp/.cs still route to
# srcML, which is not installed here, so those files get NO comment ranges and
# silently degrade MA-SZZ to B-SZZ. Excluding them keeps every commit in the
# dataset one whose labels actually had comment-aware blame.
TARGET_EXT = {".py", ".js", ".mjs", ".ts", ".tsx", ".java"}
SRC_EXT = TARGET_EXT
META_NAMES = {".gitignore", ".gitattributes", "readme", "readme.md", "license",
              "package.json", "package-lock.json", "yarn.lock", "setup.py",
              "pyproject.toml", "go.sum", "cargo.lock", "pom.xml", "build.gradle",
              "changelog.md", "makefile", "dockerfile"}
COMMENT = re.compile(r"^\s*(//|#|/\*|\*|\*/|<!--|--)")
IMPORT = re.compile(r"^\s*(import|from|#include|use|require|package)\b")
# Structure a defect can hide in: a branch, a loop, or arithmetic.
STRUCTURE = re.compile(r"\b(if|else|elif|for|while|switch|case|catch|when)\b"
                       r"|[<>!=]=|[-+*/%]=|\+\+|--")


def git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True).stdout.decode("utf8", "replace")


def repo_path(project: str) -> Path:
    return REPOS / project


def changed_lines(diff: str) -> list[str]:
    return [l[1:] for l in diff.splitlines()
            if l[:1] in "+-" and not l.startswith(("+++", "---"))]


def profile(repo: Path, rev: str) -> dict | None:
    """Churn, structure and file mix for one commit, or None if it is noise."""
    files = [f for f in git(repo, "show", "--format=", "--name-only", rev).split() if f]
    if not files or len(files) > MAX_FILES:
        return None
    if not any(Path(f).suffix in SRC_EXT for f in files):
        return None
    # A commit is only as trustworthy as its least-parsed file: one .c file in
    # the diff means part of the blame ran without comment awareness.
    if any(Path(f).suffix not in TARGET_EXT and Path(f).suffix in
           {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".cs"} for f in files):
        return None
    if any(Path(f).name.lower() in META_NAMES for f in files):
        return None
    diff = git(repo, "show", "--format=", "--unified=3", rev)
    lines = changed_lines(diff)
    if not lines or len(lines) > MAX_LINES:
        return None
    real = [l for l in lines if l.strip() and not COMMENT.match(l)]
    if not real:
        return None                      # comment/blank only: cannot be a defect
    if all(IMPORT.match(l) for l in real):
        return None                      # import-only
    return {"rev": rev, "files": files, "n_lines": len(real),
            "structured": bool(any(STRUCTURE.search(l) for l in real)),
            "diff": diff,
            "subject": git(repo, "show", "-s", "--format=%s", rev).strip()}


def lang_of(files: list[str]) -> str:
    """The language a commit is 'about': first target extension it touches."""
    exts = [Path(f).suffix for f in files]
    for e in (".java", ".py", ".ts", ".tsx", ".js", ".mjs"):
        if e in exts:
            return {".tsx": ".ts", ".mjs": ".js"}.get(e, e)
    return "?"


def churn_bin(n: int) -> int:
    for i, hi in enumerate((5, 15, 40, 100, 250, MAX_LINES)):
        if n <= hi:
            return i
    return 6


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bic", required=True, help="PySZZ output json (glob ok)")
    ap.add_argument("--out", type=Path, default=ROOT / "data/jit_dataset.jsonl")
    ap.add_argument("--seed", type=int, default=20260901)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    paths = sorted(glob.glob(args.bic))
    if not paths:
        raise SystemExit(f"no SZZ output matching {args.bic}")
    szz = json.load(open(paths[-1]))
    print(f"SZZ output: {paths[-1]}  ({len(szz)} fixes)")

    # --- defective class: every BIC any fix blames -------------------------
    bic_by_project: dict[str, set] = defaultdict(set)
    for r in szz:
        proj = r["repo_name"].replace("/", "__")
        for h in r.get("inducing_commit_hash") or []:
            bic_by_project[proj].add(h)
    n_raw = sum(len(v) for v in bic_by_project.values())
    print(f"  {n_raw} distinct bug-inducing commits before filtering")

    rng = random.Random(args.seed)
    defective, dropped = [], Counter()
    for proj, hashes in bic_by_project.items():
        repo = repo_path(proj)
        if not repo.exists():
            dropped["repo missing"] += len(hashes); continue
        for h in hashes:
            p = profile(repo, h)
            if p is None:
                dropped["noise filters"] += 1; continue
            p.update(project=proj, label=1)
            defective.append(p)
    print(f"  {len(defective)} defective survive  (dropped: {dict(dropped)})")
    if not defective:
        raise SystemExit("nothing left after filtering")

    # --- clean class: never blamed, matched on churn and structure ---------
    want_clean = round(len(defective) * (1 - DEFECT_SHARE) / DEFECT_SHARE)
    target_bins = Counter(churn_bin(d["n_lines"]) for d in defective)
    target_struct = sum(d["structured"] for d in defective) / len(defective)
    print(f"\n  target: {len(defective)} defective / {want_clean} clean "
          f"({DEFECT_SHARE:.0%}/{1-DEFECT_SHARE:.0%})")
    print(f"  matching churn bins {dict(sorted(target_bins.items()))} "
          f"and {target_struct:.0%} structured")

    # LANGUAGE QUOTA. Without this the clean class came out 98% Java while
    # .py/.ts/.js were 92-96% defective - the file extension predicted the label
    # and a model could score ~90% without reading any code. The cause was
    # iterating projects in sorted() order: apache__* sorts first and filled
    # every churn quota before the Python and JS repos were reached. Churn was
    # matched perfectly and language was destroyed silently.
    target_lang = Counter(lang_of(d["files"]) for d in defective)
    need_lang = Counter({l: round(c * want_clean / len(defective))
                         for l, c in target_lang.items()})
    print(f"  matching languages {dict(target_lang.most_common())}")

    clean: list[dict] = []
    need = Counter({b: round(c * want_clean / len(defective))
                    for b, c in target_bins.items()})
    # Interleave projects so no single repo (or language) fills the quotas first.
    projects = sorted(bic_by_project)
    rng.shuffle(projects)
    for proj in projects:
        repo = repo_path(proj)
        if not repo.exists() or sum(need.values()) <= 0:
            continue
        blamed = bic_by_project[proj]
        revs = [r for r in git(repo, "log", "--no-merges", "-n800",
                               "--format=%H").split() if r not in blamed]
        rng.shuffle(revs)
        for rev in revs:
            if sum(need.values()) <= 0:
                break
            p = profile(repo, rev)
            if p is None:
                continue
            l = lang_of(p["files"])
            if need_lang.get(l, 0) <= 0:
                continue                 # this language already has its share
            b = churn_bin(p["n_lines"])
            if need[b] <= 0:
                continue
            have = sum(c["structured"] for c in clean) / max(1, len(clean))
            if clean and p["structured"] and have > target_struct + 0.12:
                continue
            if clean and not p["structured"] and (1 - have) > (1 - target_struct) + 0.12:
                continue
            p.update(project=proj, label=0)
            clean.append(p); need[b] -= 1; need_lang[l] -= 1

    rows = defective + clean
    rng.shuffle(rows)
    print(f"\n{len(rows)} commits: {len(defective)} defective / {len(clean)} clean "
          f"({100*len(defective)//max(1,len(rows))}% defective)")
    for name, grp in (("defective", defective), ("clean", clean)):
        if not grp:
            continue
        ln = sorted(d["n_lines"] for d in grp)
        print(f"  {name:<10} median churn {ln[len(ln)//2]:>4} lines | "
              f"{100*sum(d['structured'] for d in grp)//len(grp):>3}% structured | "
              f"median {sum(len(d['files']) for d in grp)/len(grp):.1f} files")

    if args.report:
        return
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
