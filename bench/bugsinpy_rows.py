"""Turn reproduced BugsInPy runs into rows ORACLE can be evaluated on.

The synthetic bench had a tidy before/after: a ten-line program printed one
thing, then printed another. A real bug does not. What a real bug produces is a
test that fails with a specific, concrete signature -- `TypeError: 'GalaxyAPI'
object is not iterable`, `assert None == '  0%|          | 0/1000 ...'` -- and a
test that then passes. So the measured pair here is:

    before   the exception the triggering test actually raised
    after    the test passing

and `after` carries almost no information, which changes what is worth scoring.
On the synthetic corpus the question was "does it quote both values". Here the
question is the one that actually separates a grounded explanation from a
fluent one:

    names_exception   the explanation names the exception the test really raised
    quotes_signature  it quotes a distinctive fragment of the real message
    invents_exception it names a DIFFERENT exception and not the real one

The third is the counter-example the synthetic bench could never produce. An
explanation that says a change "raises a ValueError" when the measured failure
is a TypeError is wrong in a way no rubric about fluency detects, and it is the
exact failure the 2 Sep hand-grade found on real Go code.

    python bench/bugsinpy_rows.py --out data/bugsinpy_rows.jsonl
    python bench/bugsinpy_rows.py --show 5        # eyeball the extraction
"""

from __future__ import annotations

import argparse
import glob
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOME = ROOT / "data" / "bugsinpy"
REPOS = HOME / "repos"

SYSTEM = """You are ORACLE, a code reviewer. You are given one commit from a real project.

Answer with one JSON object and one key:

  "explanation"   one or two sentences telling a developer what this change does
                  to the behaviour the project's own tests observe. Name the
                  construct that changed, and quote the exact failure it fixes."""

# A pytest failure marks the operative line with `E`. A unittest failure does
# not, and ends its traceback with a bare `SomeError: message`. Both appear in
# this corpus, in roughly equal numbers, and reading only the first form loses
# tornado and youtube-dl entirely.
_E_LINE = re.compile(r"^E\s+(\S.*)$", re.M)
_EXC_LINE = re.compile(
    r"^(?:[A-Za-z_][\w.]*\.)?([A-Z]\w*(?:Error|Exception|Exit|Interrupt|Warning)):\s*(.*)$",
    re.M)
_EXC_NAME = re.compile(r"\b([A-Z]\w*(?:Error|Exception))\b")
_PASS = re.compile(r"^(?:=+\s*)?(\d+ passed[^=]*?)(?:\s+in\s+[\d.]+s?e?c?o?n?d?s?)?\s*(?:=+)?\s*$",
                   re.M)


def scrub(text: str, work: str) -> str:
    """Absolute paths make a signature unquotable and leak the machine."""
    text = text.replace(work, "<repo>")
    text = re.sub(r"/venv/lib/python3\.\d+/site-packages/", "<site-packages>/", text)
    text = re.sub(r"\s+in\s+\d+\.\d+\s*s(?:econds)?\b", "", text)
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    return text


# pytest prints its ERRORS section (collection and teardown problems) BEFORE
# its FAILURES section, so "the first E line" is often not the bug. tqdm-1 read
# as `OSError: 1 tqdm instances still in existence POST-test` -- a teardown
# complaint -- when the actual defect was `TypeError: 'int' object is not
# subscriptable`. The short test summary names the operative class; use it to
# pick which E line to believe.
_SUMMARY_FAILED = re.compile(
    r"^(?:FAILED|ERROR)\s+\S+\s+-\s+(?:[\w.]*\.)?([A-Z]\w*(?:Error|Exception)):", re.M)
_SECTION = re.compile(r"^=+\s*(FAILURES|ERRORS)\s*=+$", re.M)


def _failures_span(text: str) -> tuple[int, int]:
    """Character range of the FAILURES section, or the whole text."""
    marks = [(m.start(), m.group(1)) for m in _SECTION.finditer(text)]
    for i, (pos, kind) in enumerate(marks):
        if kind == "FAILURES":
            end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
            return pos, end
    return 0, len(text)


def signature(before: str, work: str) -> tuple[str, str]:
    """(exception class, one-line failure signature) as actually observed."""
    b = scrub(before, work)
    want = _SUMMARY_FAILED.search(b)
    wanted = want.group(1) if want else ""
    lo, hi = _failures_span(b)

    def pick(region: str, cls: str) -> tuple[str, str] | None:
        for m in _E_LINE.finditer(region):
            line = m.group(1).strip()
            if not line or line.startswith(("+", "-", "?")):
                continue
            name = _EXC_NAME.search(line)
            if cls and (not name or name.group(1) != cls):
                continue
            return (name.group(1) if name else ""), line[:400]
        return None

    for region, cls in ((b[lo:hi], wanted), (b, wanted),
                        (b[lo:hi], ""), (b, "")):
        hit = pick(region, cls)
        if hit:
            return hit
    hits = _EXC_LINE.findall(b)
    if hits:
        cls, msg = hits[-1]
        return cls, (f"{cls}: {msg}".strip()[:400])
    for line in b.split("\n"):
        if line.startswith("FAILED") or line.startswith("FAIL:"):
            return "", line.strip()[:400]
    tail = [l for l in b.strip().split("\n") if l.strip()]
    return "", (tail[-1].strip()[:400] if tail else "")


def after_signature(after: str, work: str) -> str:
    a = scrub(after, work)
    m = _PASS.search(a)
    if m:
        return m.group(1).strip().rstrip("=").strip()
    for line in reversed([l for l in a.strip().split("\n") if l.strip()]):
        if line.strip() in ("OK", "OK (skipped=1)") or line.startswith("OK"):
            return line.strip()
    tail = [l for l in a.strip().split("\n") if l.strip()]
    return (tail[-1].strip()[:200] if tail else "")


def commit_subject(project: str, rev: str) -> str:
    repo = REPOS / project
    if not repo.exists():
        return ""
    try:
        r = subprocess.run(["git", "show", "-s", "--format=%s", rev],
                           cwd=repo, capture_output=True, text=True,
                           timeout=60, stdin=subprocess.DEVNULL)
        return (r.stdout or "").strip().split("\n")[0][:200]
    except Exception:
        return ""


def build(rows: list[dict], manifest: dict[str, dict]) -> list[dict]:
    """Reproduced bugs, plus the ones that did not reproduce -- both are rows.

    A `passes-before` bug is not a failure of the harness. It is a commit whose
    triggering test passes on BOTH sides here, and the reason is usually written
    on the commit itself: cookiecutter-1 is "wrong encoding on Windows" and
    PySnooper-1 is a unicode fix, so on Linux under the pinned CPython there is
    nothing to observe. That makes them the negative class this corpus would
    otherwise lack -- real commits, measured, where the honest answer is that
    the observed behaviour did not change. Without them the eval cannot tell a
    grounded model from one that always claims a failure.
    """
    out = []
    for r in rows:
        status = r.get("status")
        if status not in ("reproduced", "passes-before"):
            continue
        m = manifest.get(r["id"], {})
        work = str(HOME / "work" / r["id"])
        differs = status == "reproduced"
        if differs:
            exc, sig = signature(r.get("before", ""), work)
        else:
            exc, sig = "", after_signature(r.get("before", ""), work)
        aft = after_signature(r.get("after", ""), work)
        if not sig:
            continue
        subject = commit_subject(r["project"], r["fixed_commit"])
        diff = m.get("patch", "")
        user = (f"## Commit\n{subject or '(no subject)'}\n\n"
                f"## Changes\n```diff\n{diff}```")
        out.append({
            "id": r["id"],
            "project": r["project"],
            "family": r["project"],
            "differs": differs,
            "exception": exc,
            "before": sig,
            "after": aft,
            "patch_files": r.get("patch_files", []),
            "test_file": m.get("test_file", ""),
            "run_test": r.get("run_test", []),
            "buggy_commit": r.get("buggy_commit", ""),
            "fixed_commit": r.get("fixed_commit", ""),
            "subject": subject,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
                {"role": "assistant", "content": json.dumps({
                    "before": sig, "after": aft,
                    "explanation": ""})},
            ],
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exec-glob", default=str(ROOT / "data/bugsinpy_*exec*.jsonl")
                    + "," + str(ROOT / "data/bugsinpy_probe*.jsonl"))
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "data" / "bugsinpy_rows.jsonl")
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--census", action="store_true",
                    help="what reproduced, per project, and why the rest did not")
    args = ap.parse_args()

    manifest = {}
    mp = ROOT / "data" / "bugsinpy_manifest.jsonl"
    if mp.exists():
        for line in open(mp):
            r = json.loads(line)
            manifest[r["id"]] = r

    # A bug is usually present several times over: once per probe, once per
    # sweep, once more after an installer fix. Keep the most informative run
    # rather than the newest, or a bug rescued by a later fix is scored on the
    # run where the environment was still broken.
    RANK = {"reproduced": 3, "passes-before": 2, "fails-after": 1}
    best: dict[str, tuple[int, int, dict]] = {}
    order = 0
    for pat in args.exec_glob.split(","):
        for path in sorted(glob.glob(pat)):
            for line in open(path):
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                key = r.get("id")
                order += 1
                cand = (RANK.get(r.get("status"), 0), order, r)
                if key not in best or cand[:2] > best[key][:2]:
                    best[key] = cand
    rows = [v[2] for v in best.values()]

    built = build(rows, manifest)
    with open(args.out, "w") as fh:
        for r in built:
            fh.write(json.dumps(r) + "\n")
    tried = len(rows)
    print(f"wrote {args.out}  {len(built)} rows from {tried} bugs attempted "
          f"({sum(r.get('status') == 'reproduced' for r in rows)} reproduced, "
          f"{sum(r.get('status') == 'passes-before' for r in rows)} unchanged here, "
          f"{sum(r.get('status') not in ('reproduced', 'passes-before') for r in rows)} not runnable)")
    n_exc = sum(bool(r["exception"]) for r in built)
    n_pos = sum(r["differs"] for r in built)
    print(f"  behaviour changed: {n_pos}   unchanged: {len(built) - n_pos}")
    print(f"  with a named exception class: {n_exc}/{n_pos} of the changed rows")
    by = {}
    for r in built:
        by[r["project"]] = by.get(r["project"], 0) + 1
    print("  " + "  ".join(f"{k}={v}" for k, v in sorted(by.items())))

    if args.census:
        import collections
        per = collections.defaultdict(collections.Counter)
        for r in rows:
            per[r["project"]][r.get("status", "?")] += 1
        cols = ["reproduced", "passes-before", "fails-after", "timeout",
                "no-commit", "no-run", "error"]
        print(f"\n{'project':<14}{'tried':>6}" +
              "".join(f"{c[:9]:>11}" for c in cols) + "   rate")
        grand = collections.Counter()
        for proj in sorted(per, key=lambda k: -per[k]["reproduced"]):
            c = per[proj]
            grand.update(c)
            tried = sum(c.values())
            print(f"{proj:<14}{tried:>6}" +
                  "".join(f"{c[k]:>11}" for k in cols) +
                  f"   {c['reproduced'] / tried:.0%}")
        tried = sum(grand.values())
        print(f"{'TOTAL':<14}{tried:>6}" +
              "".join(f"{grand[k]:>11}" for k in cols) +
              f"   {grand['reproduced'] / tried:.0%}")

    for r in built[:args.show]:
        print("\n" + "=" * 70)
        print(f"{r['id']}  [{r['exception'] or 'no class'}]  {r['patch_files']}")
        print(f"  subject : {r['subject'][:100]}")
        print(f"  before  : {r['before'][:180]}")
        print(f"  after   : {r['after'][:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
