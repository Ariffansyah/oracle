"""Turn mined clean commits into `Analysis` targets the model can be trained on.

    python -m dataset_builder.build_clean_targets
    python -m dataset_builder.build_clean_targets --audit    # measure, write nothing

What this has to avoid
----------------------
v4's `check` was built from a ten-key dictionary keyed on the case's category.
The corpus had two categories, so 366 targets carried 100 distinct checks, 357
of them containing "the edit touches", and the trained model pushed that to 100%
of its output. Two independently trained seeds then emitted the byte-identical
`check` on 62% of held-out cases. Rewriting it was a whole training cycle.

A generator is a template engine unless it is fed per-case content. So every
sentence here is composed from identifiers actually present in THIS diff - the
functions it adds, the symbols it removes, the files it touches - and the
connective forms are rotated by a hash of the revision so two commits of the
same shape do not get the same frame. `--audit` runs the same checks that caught
the v4 defect: distinct checks, distinct openers, longest shared word-run, and
leave-one-out self-similarity.

Direction
---------
Always `unchanged`. The v6 corpus already uses that value for renames and
extractions, i.e. "behaviour preserved", and adding a function preserves the
behaviour of the code that was already there. A fourth enum value would mean
editing schema.py's v3 prompt, which is baked into sft_v6_suggest.jsonl and
would make every existing checkpoint incomparable.

Confidence
----------
By the corpus rule - does the diff alone settle it. A docs-only change settles
itself (`likely`). A change inside a shared code path depends on callers the
diff does not show (`possible`). The field is currently seed-bimodal, so
feeding it targets that vary for a STATED reason is the only chance it carries
information.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Definitions a diff introduces or removes, across the four languages mined.
_DEF = re.compile(
    r"(?:^|\s)(?:"
    r"def\s+([A-Za-z_]\w*)"                        # python, ruby
    r"|class\s+([A-Za-z_]\w*)"                     # all four
    r"|function\s+([A-Za-z_$][\w$]*)"              # js
    r"|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=" # js
    r"|(?:public|private|protected|static|final)\s+[\w<>\[\], ]+?\s+([A-Za-z_]\w*)\s*\("  # java
    r")")

# Any backticked-worthy symbol on a changed line: call sites, attributes, keys.
_SYMBOL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b")
# Language keywords and English scaffolding. Without this the extractor
# produced "`with` is new in src/attr/_funcs.py" - `with` is a Python keyword,
# matched because the regex does not know what it is looking at.
_KEYWORDS = {
    "self", "this", "return", "import", "from", "class", "def", "function",
    "const", "let", "var", "public", "private", "protected", "static", "final",
    "true", "false", "null", "none", "nil", "new", "int", "str", "boolean",
    "string", "void", "if", "else", "elif", "for", "while", "with", "try",
    "except", "catch", "finally", "raise", "throw", "yield", "await", "async",
    "lambda", "pass", "break", "continue", "assert", "del", "global", "print",
    "end", "do", "then", "begin", "module", "require", "package", "extends",
    "implements", "interface", "enum", "super", "and", "not", "the", "or",
    "in", "is", "as", "of", "to", "it", "be", "was", "are", "you", "your",
}
_STOP = _KEYWORDS

# A line that is only a comment carries prose, and prose gave us "`Extract`" as
# though it were a symbol. Cheap per-language prefixes; a trailing comment on a
# code line is left alone because the code half is still real.
_COMMENT = re.compile(r"^\s*(#|//|/\*|\*|<!--|--)")


def changed_lines(diff: str, sign: str, code_only: bool = False) -> str:
    out = []
    for l in diff.splitlines():
        if not l.startswith(sign) or l.startswith(sign * 3):
            continue
        body = l[1:]
        if code_only and (_COMMENT.match(body) or not body.strip()):
            continue
        out.append(body)
    return "\n".join(out)


def defs_in(text: str) -> list[str]:
    out = []
    for m in _DEF.finditer(text):
        name = next((g for g in m.groups() if g), None)
        if name and name not in out and name.lower() not in _KEYWORDS:
            out.append(name)
    return out


def symbols_in(text: str, limit: int = 6) -> list[str]:
    counts = Counter(s for s in _SYMBOL.findall(text)
                     if s.lower() not in _STOP and not s.isupper())
    return [s for s, _ in counts.most_common(limit)]


# Test files describe the change rather than being it. Picking one as the entry
# file turned "add text parameter to config.from_file" into "tests/test_config.py
# gains test_config_from_file_json" - the wrong file and the wrong change.
_TESTISH = re.compile(r"(^|/)(tests?|spec|__tests__)/|(_test|_spec|\.test|\.spec)\.")


def pick(rev: str, salt: str, options: list[str]) -> str:
    """Deterministic rotation: same commit always gets the same frame."""
    h = int(hashlib.sha1(f"{rev}{salt}".encode()).hexdigest(), 16)
    return options[h % len(options)]


def entry_file(rec: dict) -> str:
    """The file a reader would open first: the one carrying the most change."""
    per = {}
    cur = None
    for line in rec["diff"].splitlines():
        m = re.match(r"^\+\+\+ b/(.+)$", line)
        if m:
            cur = m.group(1)
            per.setdefault(cur, 0)
        elif cur and line[:1] in "+-" and not line.startswith(("+++", "---")):
            per[cur] += 1
    if not per:
        return rec["files"][0] if rec["files"] else ""
    source = {f: n for f, n in per.items() if not _TESTISH.search(f)}
    return max(source or per, key=(source or per).get)


def hunks_for(diff: str, path: str) -> str:
    """Just the section of a multi-file diff belonging to `path`.

    Names have to come from the file the sentence names. Taking them from the
    whole diff produced "src/flask/config.py gains `test_config_from_file_json`"
    - correct file, name lifted from the test file beside it.
    """
    out, keep = [], False
    for line in diff.splitlines():
        m = re.match(r"^\+\+\+ b/(.+)$", line)
        if m:
            keep = (m.group(1) == path)
            continue
        if line.startswith(("diff --git", "index ", "--- ")):
            continue
        if keep:
            out.append(line)
    return "\n".join(out)


def build_check(rec: dict, added: list[str], removed: list[str],
                syms: list[str]) -> str:
    rev, shape, f = rec["rev"], rec["shape"], entry_file(rec)
    a = f"`{added[0]}`" if added else None
    r = f"`{removed[0]}`" if removed else None
    other = ", ".join(f"`{s}`" for s in syms[:2]) if syms else "the surrounding code"

    if shape == "docs" or not rec["language"]:
        return pick(rev, "d", [
            f"nothing to execute. The diff touches only {f}, so compare what it "
            f"now says against the behaviour {other} actually implements.",
            f"there is no code path here to run — {f} is the only file changed. "
            f"Read the new wording against {other} if you want to confirm it matches.",
            f"no test applies: {f} carries the whole diff and no source file is "
            f"in it. The only thing to check is that the text agrees with {other}.",
        ])
    if shape == "test":
        return pick(rev, "t", [
            f"run the tests in {f}. They exercise {other}; the code under test is "
            f"not modified by this diff, so a failure would be in the new test "
            f"rather than in the behaviour it covers.",
            f"execute {f} on its own. Nothing outside the test file changes here, "
            f"so any red is the assertion's, not {other}'s.",
        ])
    if shape in ("dependency", "release", "ci_config"):
        return pick(rev, "c", [
            f"build once with the pinned versions in {f} and confirm the suite "
            f"still runs. No call site moves in this diff; {other} is untouched.",
            f"re-run the build against {f}. The change is configuration, so the "
            f"thing to watch is the toolchain resolving, not {other} behaving.",
        ])
    if shape == "refactor" and removed:
        return pick(rev, "r", [
            f"exercise whatever called {r} in {f}. It is gone from this diff, so "
            f"the question is whether every caller moved with it — {other} is "
            f"where to look.",
            f"call the path that used {r}. The definition is removed in {f}; check "
            f"that {other} no longer reaches for it.",
        ])
    if added:
        return pick(rev, "a", [
            f"call {a} directly with a value it accepts, then call {other} the way "
            f"it was called before. {a} is new in {f}, so nothing had its behaviour "
            f"until now; what matters is that the existing path is unmoved.",
            f"exercise {a} on its own, and separately re-run whatever already used "
            f"{other}. The definition in {f} is an addition, so the pre-existing "
            f"callers are the half that could regress.",
            f"invoke {a} with the arguments the diff shows, and compare {other} "
            f"against its previous behaviour. Only the second of those can have "
            f"changed — {a} did not exist before {f} was edited.",
        ])
    return pick(rev, "x", [
        f"re-run whatever exercises {other} in {f}. The edit stays inside the "
        f"existing shape, so a difference there would be the thing to chase.",
        f"drive {other} through {f} the way it was driven before. Nothing in this "
        f"diff introduces a new entry point.",
    ])


def build_summary(rec: dict, added: list[str], removed: list[str],
                  syms: list[str]) -> str:
    rev, shape, f = rec["rev"], rec["shape"], entry_file(rec)
    a = f"`{added[0]}`" if added else None
    r = f"`{removed[0]}`" if removed else None
    other = ", ".join(f"`{s}`" for s in syms[:2]) if syms else "the surrounding code"

    if shape == "docs" or not rec["language"]:
        head = pick(rev, "ds", [
            f"A documentation change in {f}.",
            f"{f} is the only file in this diff, and it is prose.",
            f"This edits {f} and nothing else.",
        ])
        return f"{head} No source file is touched, so no behaviour can move."
    if shape == "test":
        head = pick(rev, "ts", [
            f"This adds coverage in {f}.",
            f"New assertions land in {f}.",
            f"{f} gains a test.",
        ])
        return (f"{head} The code it exercises — {other} — is not modified here, "
                f"so the commit adds a check rather than changing what is checked.")
    if shape in ("dependency", "release", "ci_config"):
        head = pick(rev, "cs", [
            f"This is a build-configuration change in {f}.",
            f"{f} moves version or toolchain settings.",
            f"Configuration only: {f} carries the diff.",
        ])
        return (f"{head} No call site changes, so the risk is in the toolchain "
                f"resolving rather than in {other} behaving differently.")
    if shape == "refactor" and removed:
        head = pick(rev, "rs", [
            f"{r} is removed from {f}.",
            f"This deletes {r} in {f}.",
            f"{f} drops {r}.",
        ])
        return (f"{head} The surrounding structure is otherwise intact. Worth "
                f"confirming no caller still reaches for it, but the removal "
                f"itself introduces nothing.")
    if added:
        head = pick(rev, "as", [
            f"This adds {a} to {f}.",
            f"{a} is new in {f}.",
            f"{f} gains {a}.",
        ])
        return (f"{head} Existing callers of {other} take the path they already "
                f"took — an addition has no prior behaviour to contradict. "
                f"Nothing to raise on this commit.")
    head = pick(rev, "xs", [
        f"This reworks {other} inside {f}.",
        f"{f} is edited around {other}.",
    ])
    return (f"{head} The change stays within the existing shape rather than "
            f"introducing a new path. Nothing here reads as a defect.")


def confidence(rec: dict, added: list[str], removed: list[str]) -> str:
    # Does the diff alone settle it? A prose or config change settles itself.
    # Anything reaching into a shared code path depends on callers not shown.
    if shape_is_inert(rec):
        return "likely"
    return "possible"


def shape_is_inert(rec: dict) -> bool:
    return rec["shape"] in ("docs", "release") or not rec["language"]


def target_for(rec: dict) -> dict:
    # Scope every extracted name to the file the target will name.
    scoped = hunks_for(rec["diff"], entry_file(rec)) or rec["diff"]
    plus = changed_lines(scoped, "+", code_only=True)
    minus = changed_lines(scoped, "-", code_only=True)
    added = defs_in(plus)
    removed = [d for d in defs_in(minus) if d not in added]
    syms = [s for s in symbols_in(plus + "\n" + minus)
            if s not in added and s not in removed]
    return {"effect": {"trigger": f"running {entry_file(rec)} as written",
                       "direction": "unchanged",
                       "check": build_check(rec, added, removed, syms),
                       "confidence": confidence(rec, added, removed)},
            "summary": build_summary(rec, added, removed, syms),
            "findings": []}


# --- audit: the checks that caught the v4 defect ---------------------------
def longest_run(a: str, b: str) -> int:
    A, B = a.lower().split(), b.lower().split()
    best = 0
    for i in range(len(A)):
        for j in range(len(B)):
            k = 0
            while i + k < len(A) and j + k < len(B) and A[i + k] == B[j + k]:
                k += 1
            best = max(best, k)
    return best


def audit(targets: list[dict]) -> None:
    checks = [t["effect"]["check"] for t in targets]
    summaries = [t["summary"] for t in targets]
    opens = [" ".join(s.split()[:4]) for s in summaries]
    n = len(targets)
    print(f"\n=== audit over {n} targets ===")
    print(f"  distinct checks          {len(set(checks)):>4} / {n}")
    print(f"  distinct summaries       {len(set(summaries)):>4} / {n}")
    print(f"  distinct 4-word openers  {len(set(opens)):>4} / {n}")
    pairs = list(itertools.combinations(range(n), 2))
    worst = max(pairs, key=lambda p: longest_run(checks[p[0]], checks[p[1]]))
    print(f"  longest shared word-run  {longest_run(*[checks[i] for i in worst]):>4}"
          f"   (v4 corpus-wide: 117)")
    top = Counter(" ".join(c.lower().split()[i:i + 4])
                  for c in checks
                  for i in range(max(0, len(c.split()) - 3))).most_common(1)
    if top:
        phrase, hits = top[0]
        print(f"  most repeated 4-gram     {hits:>4} / {n}  \"{phrase}\"")
    print(f"  confidence split         {dict(Counter(t['effect']['confidence'] for t in targets))}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=ROOT / "data/clean_commits.jsonl")
    ap.add_argument("--out", type=Path, default=ROOT / "data/clean_targets.jsonl")
    ap.add_argument("--audit", action="store_true", help="measure, write nothing")
    ap.add_argument("--show", type=int, default=0, help="print N targets")
    args = ap.parse_args()

    recs = [json.loads(l) for l in open(args.src) if l.strip()]
    targets = [target_for(r) for r in recs]
    audit(targets)

    if args.show:
        for rec, t in list(zip(recs, targets))[:args.show]:
            print(f"\n--- {rec['shape']} / {rec['language'] or 'no code'} / "
                  f"{rec['project']}\n    {rec['subject'][:70]}")
            print("    check  :", t["effect"]["check"][:200])
            print("    summary:", t["summary"][:200])

    if args.audit:
        return
    with open(args.out, "w") as fh:
        for rec, t in zip(recs, targets):
            fh.write(json.dumps({**rec, "target": t}, ensure_ascii=False) + "\n")
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
