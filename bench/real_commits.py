"""Grade findings on real commits, so the n stops being 46 hand-written cases.

The two standing objections to ORACLE's explanation result are that n=46 is thin
and that all 46 are synthetic. Real commits fix both and cost nothing - the
repositories are already cloned. A TUI session on 26 Aug saw the same
locus/mechanism/wrong split on real code that the hand-grade found on the 46,
but produced no counts, which is the gap this closes.

Sampling is deliberately narrow and recorded:

  * only the five held-out projects. The `apache__*` clones are leaked into the
    gate's training set, and `ml8_train` covers the rest.
  * only commits that touch code, are small enough to read, and are not merges.
    A grader who cannot hold the diff in their head cannot verify a mechanism
    claim about it, and an unverifiable claim is worse than no claim.
  * a fixed seed, with every revision written to the output, so the sample is
    reproducible and quotable.

    python bench/real_commits.py --sample 40 --out data/real_commits.jsonl
    python bench/real_commits.py --run  data/real_commits.jsonl   # needs a server
    python bench/real_commits.py --sheet data/real_commits.jsonl  # grading sheet

`--run` is separate from `--sample` on purpose: sampling needs no GPU, and on a
6GB card the model cannot be served while a training run holds the memory.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPOS = ROOT / "data" / "repos"

# The five projects in neither SFT corpus nor the gate's training set.
HELD_OUT = {
    "axios__axios": "javascript",
    "clap-rs__clap": "rust",
    "gin-gonic__gin": "go",
    "fastapi__fastapi": "python",
    "spring-projects__spring-boot": "java",
}

CODE_EXT = {".js", ".mjs", ".ts", ".rs", ".go", ".py", ".java"}

MAX_DIFF_CHARS = 6000     # a grader has to be able to read the whole thing
MIN_DIFF_CHARS = 120      # a one-word change carries no mechanism to get wrong


def git(repo: Path, args: list[str]) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True)
    return p.stdout


def candidates(repo: Path, limit: int = 4000) -> list[str]:
    """Non-merge revisions touching code, newest first."""
    out = git(repo, ["log", "--no-merges", f"-n{limit}", "--format=%H"])
    return [r for r in out.split() if r]


def commit_record(repo: Path, project: str, rev: str) -> dict | None:
    subject = git(repo, ["show", "-s", "--format=%s", rev]).strip()
    date = git(repo, ["show", "-s", "--format=%cI", rev]).strip()
    files = [f for f in git(repo, ["show", "--format=", "--name-only", rev]).split()
             if f]
    if not files or not any(Path(f).suffix in CODE_EXT for f in files):
        return None
    if len(files) > 5:
        return None
    diff = git(repo, ["show", "--format=", "--unified=3", rev])
    if not (MIN_DIFF_CHARS <= len(diff) <= MAX_DIFF_CHARS):
        return None
    return {"project": project, "language": HELD_OUT[project], "rev": rev,
            "subject": subject, "date": date, "files": files, "diff": diff}


def sample(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    per = max(1, n // len(HELD_OUT))
    picked: list[dict] = []
    for project in sorted(HELD_OUT):
        repo = REPOS / project
        if not (repo / ".git").exists() and not (repo / "HEAD").exists():
            print(f"  !! {project} not cloned at {repo} — skipped")
            continue
        revs = candidates(repo)
        rng.shuffle(revs)
        taken = 0
        for rev in revs:
            if taken >= per:
                break
            rec = commit_record(repo, project, rev)
            if rec:
                picked.append(rec)
                taken += 1
        print(f"  {project}: {taken} of {len(revs)} candidate revisions")
    return picked


def run_model(rows: list[dict], backend: str, host: str | None,
              model_name: str | None) -> list[dict]:
    from llm_explainer.client import OracleClient

    kw = {"backend": backend}
    if host:
        kw["ollama_host"] = host
    if model_name:
        kw["ollama_model"] = model_name
    client = OracleClient(**kw)
    print(f"  include_schema={client.include_schema} — this must match the "
          f"corpus the checkpoint was trained on")

    for i, r in enumerate(rows, 1):
        try:
            a = client.analyze(r["diff"], subject=r["subject"],
                               files=", ".join(r["files"]), chunked=False)
            r["predicted"] = a.model_dump()
            r["error"] = None
        except Exception as e:
            r["predicted"] = {"summary": "", "findings": []}
            r["error"] = f"{type(e).__name__}: {e}"
        n = len(r["predicted"].get("findings") or [])
        print(f"  [{i}/{len(rows)}] {r['project']:<28} {r['rev'][:10]} "
              f"{n} finding(s){' ERROR' if r['error'] else ''}")
    return rows


def sheet(rows: list[dict], out: Path) -> None:
    """A worksheet with one row per finding, for a human to fill in.

    Grades are `locus` (right place, right mechanism), `mechanism` (right place,
    wrong or inverted causal claim) and `wrong` (neither). The distinction is
    the whole point: the automated scorer cannot see the middle one, and it is
    22 points wide on the 46.
    """
    lines = ["# Real-commit grading sheet",
             "",
             "Fill `grade` with locus | mechanism | wrong, and `verified_by`",
             "with the command that proves it. A mechanism claim that was not",
             "executed is not graded - leave it blank rather than guess.",
             ""]
    n = 0
    for r in rows:
        findings = (r.get("predicted") or {}).get("findings") or []
        head = (f"## {r['project']} {r['rev'][:12]}  ({r['language']})\n"
                f"- subject: {r['subject']}\n"
                f"- files: {', '.join(r['files'])}\n"
                f"- date: {r['date']}\n"
                f"- summary: {(r.get('predicted') or {}).get('summary', '')}\n")
        lines.append(head)
        if not findings:
            lines.append("- (no findings reported)\n")
            continue
        for j, f in enumerate(findings, 1):
            n += 1
            lines.append(
                f"### finding {j}: {f.get('category')}\n"
                f"- file: {f.get('file')}\n"
                f"- explanation: {f.get('explanation')}\n"
                f"- grade: \n"
                f"- verified_by: \n")
    out.write_text("\n".join(lines))
    print(f"{n} findings over {len(rows)} commits -> {out}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, help="how many commits to draw")
    ap.add_argument("--seed", type=int, default=20260826)
    ap.add_argument("--out", type=Path, default=ROOT / "data/real_commits.jsonl")
    ap.add_argument("--run", type=Path, metavar="ROWS.jsonl",
                    help="score sampled commits with a served checkpoint")
    ap.add_argument("--sheet", type=Path, metavar="ROWS.jsonl",
                    help="write the grading worksheet for a scored file")
    ap.add_argument("--backend", default="ollama")
    ap.add_argument("--host")
    ap.add_argument("--model-name")
    args = ap.parse_args(argv)

    if args.sheet:
        rows = [json.loads(l) for l in open(args.sheet) if l.strip()]
        sheet(rows, args.sheet.with_suffix(".md"))
        return 0

    if args.run:
        # run_model prints one [i/n] line per commit, but redirected stdout is
        # block-buffered and a 40-commit run emits ~3KB - less than one 8KB
        # buffer - so the log stays EMPTY until the process exits and the run
        # reads as hung. Same bug, same fix as train_sft.py:52.
        sys.stdout.reconfigure(line_buffering=True)
        rows = [json.loads(l) for l in open(args.run) if l.strip()]
        rows = run_model(rows, args.backend, args.host, args.model_name)
        with open(args.run, "w") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"scored {len(rows)} commits -> {args.run}")
        return 0

    if not args.sample:
        ap.error("give --sample N, --run FILE or --sheet FILE")
    rows = sample(args.sample, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n{len(rows)} commits (seed {args.seed}) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
