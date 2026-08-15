"""Fetch real diffs for ApacheJIT commits, so the DPO corpus can be mined at
scale instead of hand-labelled one commit at a time.

ApacheJIT gives us 106k commits with SZZ defect labels but no code. Every row
carries `project` and `commit_id`, so the diff is one HTTP request away:

    https://github.com/apache/groovy/commit/<sha>.diff

    python dpo_pipeline/fetch_apachejit.py --limit 200
    python dpo_pipeline/fetch_apachejit.py --limit 2000 --projects groovy,camel

Output is one JSON object per commit in `data/apachejit_commits.jsonl`, carrying
the diff, the mined metrics, the model's risk score and the SZZ `buggy` label -
everything a review-mining pass needs.

The label is SZZ-derived and noisy: `buggy=True` means "a later fix touched lines
this commit introduced", not "this diff obviously contains a bug". Treat it as a
prior for triage, never as ground truth for a preference pair without review.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run as a script

from config import ROOT
from corpus.apachejit import DEFAULT_CSV, load_rows

OUT_PATH = ROOT / "data" / "apachejit_commits.jsonl"
CACHE_DIR = ROOT / "data" / "diff_cache"
DIFF_URL = "https://github.com/{project}/commit/{sha}.diff"


def fetch_diff(project: str, sha: str, cache: Path, session: requests.Session,
               retries: int = 3) -> str | None:
    """Diff text for one commit, cached on disk. None if unavailable."""
    blob = cache / f"{sha}.diff"
    if blob.exists():
        return blob.read_text(errors="replace")

    url = DIFF_URL.format(project=project, sha=sha)
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=60)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue

        if resp.status_code == 200:
            cache.mkdir(parents=True, exist_ok=True)
            blob.write_text(resp.text, errors="replace")
            return resp.text
        if resp.status_code in (403, 429):  # rate limited - back off hard
            wait = int(resp.headers.get("retry-after", 60 * (attempt + 1)))
            print(f"  rate limited, sleeping {wait}s", flush=True)
            time.sleep(wait)
            continue
        if resp.status_code == 404:  # force-pushed, or the repo moved
            return None
        time.sleep(2 ** attempt)
    return None


def summarise(diff: str) -> tuple[list[str], str]:
    """Changed file paths, and the first line as a stand-in subject."""
    files = [
        line[6:].strip() for line in diff.splitlines() if line.startswith("+++ b/")
    ]
    return files, f"({len(files)} files changed)"


def sample(rows: list[dict], limit: int, balance: bool, seed: int) -> list[dict]:
    """Pick commits to fetch, balanced across the buggy label by default.

    ApacheJIT is 26.5% buggy; an unbalanced sample makes the clean side dominate
    and the interesting cases rare.
    """
    rng = random.Random(seed)
    if not balance:
        rng.shuffle(rows)
        return rows[:limit]

    buggy = [r for r in rows if r["buggy"] == "True"]
    clean = [r for r in rows if r["buggy"] != "True"]
    rng.shuffle(buggy)
    rng.shuffle(clean)
    half = limit // 2
    picked = buggy[:half] + clean[: limit - half]
    rng.shuffle(picked)
    return picked


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--cache", type=Path, default=CACHE_DIR)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--projects", help="comma-separated filter, e.g. groovy,camel")
    ap.add_argument("--max-diff-bytes", type=int, default=40000,
                    help="skip diffs larger than this - they blow the context window")
    ap.add_argument("--min-diff-bytes", type=int, default=200,
                    help="skip trivial diffs with nothing to review")
    ap.add_argument("--no-balance", action="store_true",
                    help="sample by natural class rate instead of 50/50")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=1.0,
                    help="pause between requests; GitHub throttles hard without a token")
    args = ap.parse_args(argv)

    if not args.csv.exists():
        raise SystemExit(f"{args.csv} not found — run `python main.py train` first")

    rows = load_rows(args.csv)
    if args.projects:
        wanted = {p.strip() for p in args.projects.split(",")}
        rows = [r for r in rows
                if r["project"].split("/")[-1] in wanted or r["project"] in wanted]
        if not rows:
            raise SystemExit(f"no commits for projects {sorted(wanted)}")

    session = requests.Session()
    session.headers["User-Agent"] = "oracle-jit-research"
    if token := os.getenv("GITHUB_TOKEN"):
        session.headers["Authorization"] = f"Bearer {token}"
        print("using GITHUB_TOKEN")
    else:
        print("no GITHUB_TOKEN — unauthenticated fetches throttle quickly; "
              "export one to go faster")

    picked = sample(rows, args.limit, not args.no_balance, args.seed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.out.exists():  # resumable: re-running tops up the same file
        with open(args.out) as fh:
            done = {json.loads(line)["commit_id"] for line in fh if line.strip()}
        print(f"{len(done)} commits already in {args.out}, skipping those")

    kept = skipped = failed = 0
    started = time.time()
    with open(args.out, "a") as out:
        for n, row in enumerate(picked, 1):
            sha = row["commit_id"]
            if sha in done:
                continue

            cached = (args.cache / f"{sha}.diff").exists()
            diff = fetch_diff(row["project"], sha, args.cache, session)
            if not cached:
                time.sleep(args.sleep)

            if diff is None:
                failed += 1
                continue
            if not (args.min_diff_bytes <= len(diff) <= args.max_diff_bytes):
                skipped += 1
                continue

            files, subject = summarise(diff)
            out.write(json.dumps({
                "commit_id": sha,
                "project": row["project"],
                "buggy": row["buggy"] == "True",
                "diff": diff,
                "files": files,
                "subject": subject,
                "label": "unlabelled",
            }) + "\n")
            out.flush()  # crash-safe: a killed run keeps what it fetched
            kept += 1
            if n % 25 == 0 or kept == 1:
                rate = n / max(time.time() - started, 1e-9)
                print(f"  {n}/{len(picked)} seen, {kept} kept, {skipped} skipped, "
                      f"{failed} failed ({rate:.1f}/s)", flush=True)

    print(f"\n{kept} commits -> {args.out}  ({skipped} outside size limits, "
          f"{failed} unavailable)")
    if kept:
        print("next: review them, set each record's \"label\", then\n"
              f"  python dpo_pipeline/dataset_builder.py --input {args.out}")


if __name__ == "__main__":
    main()
