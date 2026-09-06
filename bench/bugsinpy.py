"""BugsInPy: 501 real Python bugs, each with a test that fails before the fix
and passes after it.

Every number ORACLE reports today is measured on a benchmark ORACLE built. The
519 held-out rows are synthetic mutants of hand-written files, which makes three
of the five standing objections one objection: the corpus is ours, the bugs are
ours, and nobody else has a number on it. BugsInPy is the cheapest corpus that
answers all three at once -- real bugs, from real projects, with the triggering
test already identified, and published results from other groups to sit beside.

It also unblocks the `score` arm. That arm scored 39% against `diff`'s 39% with
p=0.699, but on synthetic rows the gate's 14 Kamei metrics are zero-filled and
it reaches AUC 0.557 -- so the honest reading was "a near-chance number tells
the explainer nothing", not "a defect probability tells it nothing". These are
real commits in repositories with full history, so the gate computes every
metric it was designed for, and the arm becomes answerable as asked.

What the corpus gives us, per bug:

  * a fix diff, `bug_patch.txt`, with test files already stripped out
  * the buggy commit and the fixed commit, in a clonable repository
  * the triggering test, and the command that runs it
  * pinned requirements and the Python version the authors used

410 of the 501 patches touch exactly one file, and the median patch changes 6
lines. That is the shape ORACLE's per-file execution model already assumes, and
it is a far better fit than the corpus we have.

    python bench/bugsinpy.py --fetch                 # clone the metadata repo
    python bench/bugsinpy.py --manifest              # -> data/bugsinpy_manifest.jsonl
    python bench/bugsinpy.py --census                # what is usable, and why not

`--fetch` is separate because the metadata repo is 11M of somebody else's git
history; it lives under data/bugsinpy/ and is gitignored.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOME = ROOT / "data" / "bugsinpy"
META = HOME / "BugsInPy"
UPSTREAM = "https://github.com/soarsmu/BugsInPy.git"

# bug.info is hand-maintained and inconsistent: 42 of the 501 files are CRLF,
# and some write `fixed_commit_id =` with a space before the `=`. Parsing them
# strictly drops those 42 silently, which is exactly the kind of loss that shows
# up later as an unexplained n.
_KV = re.compile(r'^\s*([A-Za-z_]+)\s*=\s*"?(.*?)"?\s*$')


# Some requirement files in the corpus are UTF-16 with a BOM. Decoded as UTF-8
# they come back as mojibake whose FIRST line is corrupted, so exactly one pin
# is silently lost -- `aiohttp` for black, `appdirs` for scrapy -- and the bug
# then fails with an unrelated NameError deep in a test. Detect the encoding.
def read_text_smart(p: pathlib.Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "utf-8", "latin-1"):
        try:
            t = raw.decode(enc)
        except Exception:
            continue
        if "\x00" not in t:
            return t
    return raw.decode("utf-8", "replace")


def parse_info(path: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in read_text_smart(path).replace("\r\n", "\n").split("\n"):
        m = _KV.match(line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def patch_files(diff: str) -> list[str]:
    """The b-side paths a unified diff touches."""
    return [m.group(1) for m in
            re.finditer(r'^diff --git a/\S+ b/(\S+)', diff, re.M)]


def patch_lines(diff: str) -> int:
    return sum(1 for l in diff.split("\n")
               if l[:1] in "+-" and l[:2] not in ("++", "--"))


def fetch() -> int:
    HOME.mkdir(parents=True, exist_ok=True)
    if META.exists():
        print(f"already there: {META}")
        return 0
    print(f"cloning {UPSTREAM} -> {META}")
    r = subprocess.run(["git", "clone", "--depth", "1", UPSTREAM, str(META)])
    return r.returncode


def bugs() -> list[dict]:
    """Every bug in the metadata repo, parsed, in project/id order."""
    rows = []
    for pdir in sorted((META / "projects").iterdir()):
        if not pdir.is_dir():
            continue
        proj = parse_info(pdir / "project.info") if (pdir / "project.info").exists() else {}
        bdir = pdir / "bugs"
        if not bdir.is_dir():
            continue
        for one in sorted(bdir.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else 0):
            info_p = one / "bug.info"
            if not info_p.exists():
                continue
            info = parse_info(info_p)
            diff = ""
            if (one / "bug_patch.txt").exists():
                diff = read_text_smart(one / "bug_patch.txt")
            reqs = ""
            if (one / "requirements.txt").exists():
                reqs = read_text_smart(one / "requirements.txt")
            run = ""
            if (one / "run_test.sh").exists():
                run = read_text_smart(one / "run_test.sh")
            files = patch_files(diff)
            rows.append({
                "id": f"{pdir.name}-{one.name}",
                "project": pdir.name,
                "bug": one.name,
                "github_url": proj.get("github_url", ""),
                "python_version": info.get("python_version", ""),
                "buggy_commit": info.get("buggy_commit_id", ""),
                "fixed_commit": info.get("fixed_commit_id", ""),
                "test_file": info.get("test_file", ""),
                "pythonpath": info.get("pythonpath", ""),
                "run_test": [l.strip() for l in run.replace("\r\n", "\n").split("\n")
                             if l.strip()],
                "patch_files": files,
                "n_files": len(files),
                "patch_lines": patch_lines(diff),
                "patch": diff,
                "requirements": reqs,
            })
    return rows


def usable(r: dict) -> str | None:
    """Why this bug cannot enter the corpus, or None if it can."""
    if not r["fixed_commit"]:
        return "no fixed_commit_id"
    if not r["buggy_commit"]:
        return "no buggy_commit_id"
    if not r["github_url"]:
        return "no github_url"
    if not r["run_test"]:
        return "no run_test.sh"
    if r["n_files"] == 0:
        return "empty patch"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--manifest", action="store_true")
    ap.add_argument("--census", action="store_true")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "data" / "bugsinpy_manifest.jsonl")
    args = ap.parse_args()

    if args.fetch:
        return fetch()
    if not META.exists():
        print("metadata not fetched; run: python bench/bugsinpy.py --fetch",
              file=sys.stderr)
        return 1

    rows = bugs()

    if args.manifest:
        with open(args.out, "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        ok = sum(usable(r) is None for r in rows)
        print(f"wrote {args.out}  {len(rows)} bugs, {ok} with complete metadata")

    if args.census:
        by_proj: dict[str, list[dict]] = {}
        for r in rows:
            by_proj.setdefault(r["project"], []).append(r)
        print(f"{'project':<14}{'bugs':>5}{'ok':>5}{'1-file':>8}{'med.lines':>11}"
              f"  pythons")
        for p, rs in sorted(by_proj.items(), key=lambda kv: -len(kv[1])):
            ok = [r for r in rs if usable(r) is None]
            one = sum(r["n_files"] == 1 for r in rs)
            lines = sorted(r["patch_lines"] for r in rs)
            med = lines[len(lines) // 2] if lines else 0
            pys = sorted({r["python_version"][:3] for r in rs if r["python_version"]})
            print(f"{p:<14}{len(rs):>5}{len(ok):>5}{one:>8}{med:>11}  {','.join(pys)}")
        bad: dict[str, int] = {}
        for r in rows:
            why = usable(r)
            if why:
                bad[why] = bad.get(why, 0) + 1
        print(f"\n{'total':<14}{len(rows):>5}"
              f"{sum(usable(r) is None for r in rows):>5}"
              f"{sum(r['n_files'] == 1 for r in rows):>8}")
        if bad:
            print("\nexcluded:")
            for why, n in sorted(bad.items(), key=lambda kv: -kv[1]):
                print(f"  {n:>4}  {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
