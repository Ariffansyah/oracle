"""CVEfixes -> ORACLE records, with human-written explanations and no teacher.

CVEfixes (Bhandari et al., PROMISE 2021; dataset v1.0.8, Moonen & Vidziunas,
`10.5281/zenodo.13118970`, CC BY 4.0) maps CVEs to the commits that fixed them,
across many languages. Two things make it worth the 52 GB:

  * the **CVE description is a human-written explanation** of the defect, so the
    explanation target comes from a person rather than from a teacher model.
    No API cost, and no way for a hint in a labelling prompt to leak the answer.
  * the defect is **known to be present**. An SZZ-buggy label only says a later
    commit touched these lines; a CVE says this code was exploitable.

    python -m corpus.cvefixes --limit 500
    python -m corpus.cvefixes --languages Python,TypeScript,Go --limit 300

## What a `buggy` record is here

CVEfixes stores the *fix*, not the commit that introduced the vulnerability.
Recovering the real introducing commit needs SZZ over a full clone of every
repository; instead each fix commit is emitted **twice**, in both directions:

  `{hash}:intro`  the fix reversed  -> buggy=True,  findings=[the CVE]
  `{hash}:fix`    the fix as-is     -> buggy=False, findings=[]

so the positive and negative differ only in direction, and every confound that
usually decides these benchmarks - repository, language, file, diff size, even
which lines are touched - is held fixed. A model cannot win by noticing that
buggy commits are longer. It has to read which way the code is moving.

Two consequences to state in the paper:

  * the introducing commit is **synthetic**. It never existed in history, and a
    real vulnerability is rarely introduced by exactly reversing its fix.
  * records come in pairs. Bootstrap and train/test splits must resample on
    `pair` (the commit hash), never on the record, or the two halves of a pair
    land on both sides and the variance estimate is wrong.

The commit message is never used as `subject` - it usually names the CVE.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from config import ROOT

DEFAULT_DB = ROOT / "data" / "cvefixes" / "CVEfixes.db"
DEFAULT_OUT = ROOT / "data" / "cvefixes_eval.jsonl"

# Matched to `detect_eval.jsonl` (495..5979 chars) on purpose: comparing ORACLE
# across two datasets is only meaningful if the diffs are of comparable size.
MIN_DIFF, MAX_DIFF = 300, 6000

_HUNK = re.compile(r"^@@ -(\S+) \+(\S+) @@(.*)$")


def description(raw: str) -> str:
    """The English CVE text out of the stringified `[{'lang': ..., 'value': ...}]`."""
    try:
        entries = ast.literal_eval(raw)
        for e in entries:
            if e.get("lang") == "en":
                return e["value"].strip()
        return entries[0]["value"].strip()
    except Exception:
        return raw.strip()


def reverse_hunks(diff: str, flip: bool = True) -> str:
    """Invert a unified diff: applying the result undoes the original change.

    With `flip=False` the change is left alone and only the line order is
    normalised. Both directions go through this function on purpose: if only the
    reversed side were re-sorted, the sorting itself would become the tell.

    The `file_change.diff` column holds hunks only - no `---`/`+++` header - so
    swapping the leading character is safe here in a way it would not be on a
    full git diff.

    Flipping signs alone is semantically correct but leaves a tell: git always
    prints a run of `-` before its `+`, and a naive flip inverts that order. A
    model would learn "plus-before-minus means reversed" and score well without
    reading any code, so each changed run is re-sorted back into git's order.
    Line order *within* the minus lines and within the plus lines is preserved,
    which is what actually carries the file contents.
    """
    out: list[str] = []
    run: list[str] = []

    def flush():
        run.sort(key=lambda s: s[0] != "-")   # stable: '-' first, '+' after
        out.extend(run)
        run.clear()

    for line in diff.splitlines():
        m = _HUNK.match(line)
        if line[:1] in ("+", "-") and not m:
            sign = ("-" if line[0] == "+" else "+") if flip else line[0]
            run.append(sign + line[1:])
            continue
        flush()
        # `\ No newline at end of file` binds to the line above it, so it ends a
        # run rather than being sorted into one.
        out.append(f"@@ -{m.group(2)} +{m.group(1)} @@{m.group(3)}" if m else line)
    flush()
    return "\n".join(out) + "\n"


def render(files: list[dict], reverse: bool) -> str:
    """Per-file hunks -> one git-style diff, the shape every other corpus emits."""
    parts = []
    for f in files:
        old = f["old_path"] or f["filename"]
        new = f["new_path"] or f["filename"]
        if reverse:
            old, new = new, old
        body = reverse_hunks(f["diff"], flip=reverse)
        parts.append(f"diff --git a/{old} b/{new}\n--- a/{old}\n+++ b/{new}\n{body}")
    return "".join(parts)


def first_sentence(text: str) -> str:
    m = re.search(r"(?<=[.!?])\s", text)
    return text[: m.start()] if m else text


def commits(db: Path, languages: set[str] | None = None):
    """Yield one dict per fix commit: its CVE, its files, its hunks.

    `fixes` and `cve` are small enough to hold in memory, so no join is needed
    and the one large scan reads only the columns it uses - `code_before` and
    `code_after` are whole file snapshots and are what makes this database 52 GB.
    """
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cve_for_hash: dict[str, str] = {}
    for h, cve_id in con.execute("select hash, cve_id from fixes"):
        # A commit can fix several CVEs; the lowest id keeps the choice stable
        # across runs so re-running does not reshuffle the corpus.
        if h not in cve_for_hash or cve_id < cve_for_hash[h]:
            cve_for_hash[h] = cve_id
    descriptions = {c: description(d) for c, d in
                    con.execute("select cve_id, description from cve")}
    repo = dict(con.execute("select hash, repo_url from commits"))

    current, rows = None, []
    q = ("select hash, filename, old_path, new_path, programming_language, diff "
         "from file_change where change_type = 'ModificationType.MODIFY' "
         "and diff is not null order by hash")
    for h, filename, old_path, new_path, lang, diff in con.execute(q):
        if h != current:
            if rows:
                yield _group(current, rows, cve_for_hash, descriptions, repo, languages)
            current, rows = h, []
        rows.append({"filename": filename, "old_path": old_path,
                     "new_path": new_path, "language": lang, "diff": diff})
    if rows:
        yield _group(current, rows, cve_for_hash, descriptions, repo, languages)
    con.close()


def _group(h, rows, cve_for_hash, descriptions, repo, languages) -> dict | None:
    cve_id = cve_for_hash.get(h)
    text = descriptions.get(cve_id, "")
    if not cve_id or not text:
        return None
    # Language of the commit = the most common one among its files, ignoring
    # docs and data. A fix that only touches Markdown is not a code change.
    counts = Counter(r["language"] for r in rows
                     if r["language"] not in ("unknown", "Markdown", "None", None))
    if not counts:
        return None
    language = counts.most_common(1)[0][0]
    if languages and language not in languages:
        return None
    url = repo.get(h, "")
    return {"hash": h, "cve_id": cve_id, "description": text, "language": language,
            "project": "/".join(url.rstrip("/").split("/")[-2:]), "files": rows}


def records(commit: dict) -> list[dict]:
    """One fix commit -> its introducing/fixing pair, in our record shape."""
    out = []
    for direction, buggy in (("intro", True), ("fix", False)):
        diff = render(commit["files"], reverse=buggy)
        if not MIN_DIFF <= len(diff) <= MAX_DIFF:
            return []          # drop the pair, never half of one
        text = commit["description"]
        analysis = (
            {"summary": first_sentence(text),
             "findings": [{"category": "security", "explanation": text}]}
            if buggy else
            # The negative side has no human text - the CVE describes the defect,
            # not its repair - so this one line is templated. It is a detection
            # target, not an explanation target; score explanations on `intro`.
            {"summary": "This change removes a vulnerable code path. "
                        "No defect is introduced.", "findings": []}
        )
        out.append({
            "commit_id": f"{commit['hash']}:{direction}",
            "pair": commit["hash"],
            "project": commit["project"],
            "language": commit["language"],
            "buggy": buggy,
            # Never the commit message: it names the CVE. Same placeholder the
            # ApacheJIT detection set uses, so the two are prompt-comparable.
            "subject": f"({len(commit['files'])} files changed)",
            "files": [f["filename"] for f in commit["files"]],
            "diff": diff,
            "analysis": analysis,
            "cve_id": commit["cve_id"],
        })
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=500, help="commit pairs to emit")
    ap.add_argument("--languages", help="comma-separated, e.g. Python,Go,TypeScript")
    ap.add_argument("--max-per-project", type=int, default=20,
                    help="cap one repository's share; chromium and linux dominate")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.db.exists():
        raise SystemExit(f"{args.db} not found — restore the CVEfixes dump first")

    langs = set(args.languages.split(",")) if args.languages else None
    per_project: Counter = Counter()
    kept, seen = [], 0
    for commit in commits(args.db, langs):
        if commit is None:
            continue
        seen += 1
        if per_project[commit["project"]] >= args.max_per_project:
            continue
        pair = records(commit)
        if not pair:
            continue
        per_project[commit["project"]] += 1
        kept.extend(pair)
        if len(kept) >= args.limit * 2:
            break

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as fh:
        for r in kept:
            fh.write(json.dumps(r) + "\n")

    langs_seen = Counter(r["language"] for r in kept)
    print(f"{len(kept)} records ({len(kept) // 2} commit pairs) from {seen} candidates")
    print(f"  languages   {dict(langs_seen.most_common(8))}")
    print(f"  projects    {len(per_project)} repositories, "
          f"top {per_project.most_common(3)}")
    print(f"  buggy       {sum(r['buggy'] for r in kept)}/{len(kept)}")
    print(f"{args.out}")
    print(f"next:\n  python evaluate.py --heldout {args.out} --limit {len(kept)} "
          f"--model artifacts/sft-adapter/checkpoint-220 --out data/cve_sft220.jsonl")
    return 0


def selftest() -> int:
    d = "@@ -1,3 +1,4 @@ ctx\n keep\n-old\n+new\n+extra\n"
    r = reverse_hunks(d)
    # Minus before plus, as git writes it - the reversal must not be detectable
    # from line order alone.
    assert r == "@@ -1,4 +1,3 @@ ctx\n keep\n-new\n-extra\n+old\n", repr(r)
    assert reverse_hunks(r) == d, "reversal is its own inverse"
    assert reverse_hunks("@@ -1 +1 @@\n+a\n-b\n") == "@@ -1 +1 @@\n-a\n+b\n"

    f = [{"filename": "a.py", "old_path": "a.py", "new_path": "a.py", "diff": d}]
    fwd, back = render(f, reverse=False), render(f, reverse=True)
    assert fwd.startswith("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@")
    # The two directions must differ only in direction: same files, same size
    # class, no length cue a classifier could latch onto.
    assert abs(len(fwd) - len(back)) <= 2, (len(fwd), len(back))
    assert fwd.count("\n+") == back.count("\n-")
    # Both directions are normalised the same way, so neither carries a
    # line-order signature the other lacks.
    for text in (fwd, back):
        lines = [l for l in text.splitlines() if not l.startswith(("diff ", "---", "+++"))]
        assert not any(a.startswith("+") and b.startswith("-")
                       for a, b in zip(lines, lines[1:])), text

    raw = "[{'lang': 'en', 'value': \"a bug in x allows attackers to y.\"}]"
    assert description(raw) == "a bug in x allows attackers to y."
    assert description("not a list") == "not a list"
    assert first_sentence("One. Two.") == "One."
    assert first_sentence("No terminator") == "No terminator"

    c = {"hash": "abc", "cve_id": "CVE-1", "description": "X. Y.",
         "language": "Python", "project": "o/r", "files": f * 4}
    pair = records(c)
    assert [x["buggy"] for x in pair] == [True, False]
    assert pair[0]["analysis"]["findings"][0]["category"] == "security"
    assert pair[0]["analysis"]["summary"] == "X."
    assert pair[1]["analysis"]["findings"] == []
    assert pair[0]["pair"] == pair[1]["pair"] == "abc"
    assert "CVE" not in pair[0]["subject"] and "CVE" not in pair[0]["diff"]

    from dataset_builder.schema import Analysis
    Analysis.model_validate(pair[0]["analysis"])
    Analysis.model_validate(pair[1]["analysis"])
    print("cvefixes ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
