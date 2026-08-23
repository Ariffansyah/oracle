"""How much of a verdict survives reformatting the diff it was read from.

Every F1 in RESULTS.md is a single greedy pass over one exact rendering of each
commit. That is only meaningful if the model reads a commit, not a rendering of
it. A concurrency bug found on one Go diff was reported as `concurrency` on one
rendering and `null-dereference` on another that differed only in blob hashes
and where git put a blank line — same model, same greedy decode.

So this measures the noise floor: perturb the diff *without touching a single
line of code*, re-ask, and count how often the answer moves. The perturbations
edit only git metadata - the index line and the hunk header's trailing section
name - so any disagreement is the model reacting to text it should ignore.

    .venv/bin/python variance.py --limit 40 --backend ollama \
        --model-name oracle-merged --host http://localhost:8111

Rows stream to --out as they finish, so a killed run keeps its work. Report the
agreement rate next to the F1 it qualifies: a 0.04 F1 gap means nothing if the
verdict itself moves more than that under cosmetic edits.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HELDOUT = ROOT / "data" / "labelled_heldout.jsonl"

_INDEX_RE = re.compile(r"^index ([0-9a-f]+)\.\.([0-9a-f]+)(.*)$", re.M)
_HUNK_RE = re.compile(r"^(@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@)(.*)$", re.M)
# Rotating a hex digit keeps the hash a hash: same length, same alphabet, and
# git never reads it back, so the diff still describes the same change.
_ROT = str.maketrans("0123456789abcdef", "123456789abcdef0")


def base(diff: str) -> str:
    """The rendering the corpus stored, unchanged."""
    return diff


def no_index(diff: str) -> str:
    """Drop the `index <sha>..<sha> <mode>` line git writes above each file."""
    return _INDEX_RE.sub(lambda m: "", diff).replace("\n\n@@", "\n@@")


def rehash(diff: str) -> str:
    """Keep the index line, change the blob hashes it carries."""
    return _INDEX_RE.sub(
        lambda m: f"index {m[1].translate(_ROT)}..{m[2].translate(_ROT)}{m[3]}",
        diff)


def bare_hunk(diff: str) -> str:
    """Strip the enclosing-function name git appends after the `@@`."""
    return _HUNK_RE.sub(lambda m: m[1], diff)


VARIANTS = {"base": base, "no_index": no_index, "rehash": rehash,
            "bare_hunk": bare_hunk}


def verdict(said: dict) -> bool:
    """The binary the F1 is computed from: did it report anything at all."""
    return bool(said.get("findings"))


def categories(said: dict) -> list[str]:
    return sorted(f.get("category", "") for f in said.get("findings", []))


def score(rows: list[dict]) -> dict:
    """Agreement of each perturbed answer with the same commit's base answer."""
    # A failed call has empty findings, which is indistinguishable from an
    # honest "clean" verdict once it is in the table. Dropping errors keeps a
    # dead tunnel from being reported as the model changing its mind.
    errors = sum(1 for r in rows if r.get("error"))
    rows = [r for r in rows if not r.get("error")]

    by_commit: dict[str, dict[str, dict]] = {}
    for r in rows:
        by_commit.setdefault(r["commit_id"], {})[r["variant"]] = r

    verdict_hits = verdict_total = cat_hits = cat_total = 0
    unanimous = commits = 0
    noop = 0
    flipped: list[tuple[str, str, str]] = []
    for cid, variants in by_commit.items():
        if "base" not in variants:
            continue
        commits += 1
        ref = variants["base"]
        all_agree = True
        for name, row in variants.items():
            if name == "base":
                continue
            # A perturbation that could not apply (no index line, no section
            # name) re-sends the base text; counting it as agreement would
            # inflate the rate with comparisons that were never made.
            if row["diff_sha"] == ref["diff_sha"]:
                noop += 1
                continue
            verdict_total += 1
            same = verdict(row["predicted"]) == verdict(ref["predicted"])
            verdict_hits += same
            if not same:
                all_agree = False
                flipped.append((cid, name,
                                f"{verdict(ref['predicted'])} -> {verdict(row['predicted'])}"))
            cat_total += 1
            cat_hits += categories(row["predicted"]) == categories(ref["predicted"])
        unanimous += all_agree
    return {"commits": commits, "noop": noop, "errors": errors,
            "verdict_total": verdict_total, "verdict_hits": verdict_hits,
            "cat_total": cat_total, "cat_hits": cat_hits,
            "unanimous": unanimous, "flipped": flipped}


def report(name: str, s: dict) -> None:
    v = 100 * s["verdict_hits"] / s["verdict_total"] if s["verdict_total"] else 0.0
    c = 100 * s["cat_hits"] / s["cat_total"] if s["cat_total"] else 0.0
    u = 100 * s["unanimous"] / s["commits"] if s["commits"] else 0.0
    print(f"\n=== {name} ===")
    print(f"  commits              {s['commits']}")
    print(f"  comparisons          {s['verdict_total']}  "
          f"({s['noop']} skipped: perturbation did not apply, "
          f"{s['errors']} dropped: call failed)")
    print(f"  verdict agreement    {v:.1f}%   ({s['verdict_hits']}/{s['verdict_total']})")
    print(f"  category agreement   {c:.1f}%   ({s['cat_hits']}/{s['cat_total']})")
    print(f"  commits unanimous    {u:.1f}%   ({s['unanimous']}/{s['commits']})")
    if s["flipped"]:
        print(f"  verdict flips:")
        for cid, name_, how in s["flipped"][:15]:
            print(f"    {cid[:10]}  {name_:10s} {how}")
        if len(s["flipped"]) > 15:
            print(f"    … {len(s['flipped']) - 15} more")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heldout", type=Path, default=HELDOUT)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--backend", choices=("auto", "transformers", "ollama"),
                    default="auto")
    ap.add_argument("--model", type=Path, help="local model dir (transformers)")
    ap.add_argument("--model-name", help="served model name, for --backend ollama")
    ap.add_argument("--host", help="served host, e.g. http://localhost:8111")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "variance_results.jsonl")
    ap.add_argument("--name", default="variance")
    ap.add_argument("--score", type=Path,
                    help="score an existing results file instead of running")
    args = ap.parse_args(argv)

    if args.score:
        rows = [json.loads(l) for l in open(args.score) if l.strip()]
        report(args.score.stem, score(rows))
        return 0

    if not args.heldout.exists():
        raise SystemExit(f"{args.heldout} not found — split the corpus first")
    records = [json.loads(l) for l in open(args.heldout) if l.strip()][: args.limit]

    from llm_explainer.client import OracleClient

    kwargs = {"backend": args.backend}
    if args.model:
        kwargs["model_path"] = args.model
    if args.model_name:
        kwargs["ollama_model"] = args.model_name
    if args.host:
        kwargs["ollama_host"] = args.host
    client = OracleClient(**kwargs)

    total = len(records) * len(VARIANTS)
    print(f"{len(records)} commits x {len(VARIANTS)} renderings = {total} calls")
    print(f"backend: {client.backend}  ->  {args.out}")

    import hashlib

    done = 0
    with open(args.out, "w") as fh:
        for rec in records:
            for vname, fn in VARIANTS.items():
                diff = fn(rec["diff"])
                started = time.time()
                try:
                    # chunked=False and the same subject/files evaluate.py
                    # sends, so this agreement rate qualifies those F1 numbers
                    # rather than describing a different task.
                    said = client.analyze(diff, subject=rec.get("subject", ""),
                                          files=", ".join(rec.get("files", [])),
                                          chunked=False).model_dump()
                    error = None
                except Exception as e:
                    said, error = {"summary": "", "findings": []}, f"{type(e).__name__}: {e}"
                done += 1
                row = {"commit_id": rec["commit_id"], "variant": vname,
                       "diff_sha": hashlib.sha1(diff.encode()).hexdigest()[:12],
                       "buggy": rec.get("buggy"), "predicted": said,
                       "error": error, "seconds": time.time() - started}
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                mark = "!" if error else len(said["findings"])
                print(f"  [{done}/{total}] {rec['commit_id'][:10]} {vname:10s} "
                      f"{row['seconds']:5.1f}s  findings={mark}", flush=True)

    rows = [json.loads(l) for l in open(args.out) if l.strip()]
    report(args.name, score(rows))
    return 0


def demo():
    d = ("diff --git a/x.go b/x.go\n"
         "index fc27945..6188a19 100644\n"
         "--- a/x.go\n+++ b/x.go\n"
         "@@ -2,87 +2,38 @@ package main\n"
         " ctx\n-old\n+new\n")

    assert base(d) == d
    assert "index " not in no_index(d)
    assert "-old\n+new" in no_index(d)          # code lines survive every variant

    r = rehash(d)
    assert "index fc27945..6188a19" not in r
    assert re.search(r"^index [0-9a-f]{7}\.\.[0-9a-f]{7} 100644$", r, re.M), r
    assert "100644" in r                         # the mode is not a blob hash
    assert "-old\n+new" in r

    b = bare_hunk(d)
    assert "@@ -2,87 +2,38 @@\n" in b
    assert "package main" not in b
    assert "-old\n+new" in b

    # A diff with no metadata to perturb comes back unchanged - the scorer has
    # to skip those comparisons instead of scoring them as agreement.
    plain = " ctx\n-old\n+new\n"
    assert no_index(plain) == rehash(plain) == bare_hunk(plain) == plain

    def row(cid, variant, sha, cats):
        return {"commit_id": cid, "variant": variant, "diff_sha": sha,
                "predicted": {"findings": [{"category": c} for c in cats]}}

    failed = {**row("c", "rehash", "s9", []), "error": "InferenceError: no route"}
    s = score([row("a", "base", "s1", ["concurrency"]),
               row("a", "rehash", "s2", ["null-dereference"]),  # same verdict, new label
               row("a", "no_index", "s3", []),                  # verdict flipped
               row("b", "base", "s4", []),
               row("b", "rehash", "s4", []),                    # no-op, not counted
               row("c", "base", "s8", ["logic-error"]), failed])
    assert s["commits"] == 3, s
    assert s["errors"] == 1, s                   # a dead tunnel is not a flip
    assert s["noop"] == 1, s
    assert s["verdict_total"] == 2 and s["verdict_hits"] == 1, s
    assert s["cat_total"] == 2 and s["cat_hits"] == 0, s
    assert s["unanimous"] == 2, s                # b and c never disagreed
    print("ok")


if __name__ == "__main__":
    sys.exit(main()) if sys.argv[1:] else demo()
