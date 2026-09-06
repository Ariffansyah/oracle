"""Score a reviewer against held-out commits it has never seen.

    python evaluate.py --model artifacts/oracle-merged --limit 200
    python evaluate.py --backend ollama --model-name qwen3-coder:latest   # baseline
    python evaluate.py --compare data/eval_tuned.jsonl data/eval_stock.jsonl

Five measures, chosen because each answers a question a reviewer will ask:

  valid JSON       did it answer in the contract at all
  detection P/R/F1 does "found a defect" agree with the SZZ label
  grounding        does every finding cite a file that is actually in the diff
  category match   does it pick the same defect class as the teacher
  fix agreement    does the finding name what the real repair actually changed
                   (inert: no dataset in data/ carries `fix_diff` yet)

The last one is the interesting one. For a commit SZZ flagged, a later commit
repaired those lines - so the fix's own diff is an objective answer key for the
*explanation*, not just for the verdict. Prior JIT work cannot do this: a
probability has nothing to compare against.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import ROOT
from corpus.mine import CLONE_DIR, clone

HELDOUT = ROOT / "data" / "labelled_heldout.jsonl"

_TOK = r"[A-Za-z_][A-Za-z0-9_.]{2,}"  # three chars up; `i`, `n`, `xs` stay out

# Words that carry defect meaning; everything else is scaffolding. Used for the
# overlap measures so "the" and "this" cannot inflate a score.
_STOP = set("""a an the and or but if then than that this these those is are was
were be been being to of in on at for with from by as it its into over under
new old code line lines change changes commit method function call calls when
which while not no null true false return returns set get add adds added remove
removed use used using should would could may might can will""".split())


def content_words(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text.lower())
    return {w for w in words if w not in _STOP}


def decorated(text: str) -> set[str]:
    """Names carrying a `_`, a `.` or a camelCase hump - unambiguously code."""
    return {t.lower().strip(".") for t in re.findall(_TOK, text)
            if "_" in t or "." in t or re.search(r"[a-z][A-Z]", t)}


def identifiers(text: str) -> set[str]:
    """Every name in the text: decorated ones, plus plain ones not in _STOP.

    Plain names used to be dropped entirely - only `_`, `.` or camelCase
    survived - so `main`, `buf`, `len`, `size` and all-caps macros like `CFLAGS`
    were invisible. In a C or Makefile diff that leaves the changed code with an
    EMPTY vocabulary, so no finding about it could ever ground, however correct.

    `_STOP` removes English scaffolding and language keywords ("the",
    "function", "return"): they occur in every diff and are evidence of nothing.
    That is not enough on its own - see `grounded()`, which decides how many
    plain matches are worth believing.
    """
    return decorated(text) | ({t.lower().strip(".")
                               for t in re.findall(_TOK, text)} - _STOP)


def files_in_diff(diff: str) -> set[str]:
    return {m.group(1) for m in re.finditer(r"^\+\+\+ b/(.+)$", diff, re.MULTILINE)}


def grounded(finding: dict, diff: str, scope: str = "changed") -> bool:
    """A finding is grounded when what it talks about appears in the code it reviews.

    `scope` picks WHICH code, and the two settings are not interchangeable:

      "changed"  (default) only the diff's +/- lines. This is what the corpus
                 builders and `dpo_pipeline` use and what every number in
                 docs/RESULTS.md was computed with, so it must not move.
      "context"  the whole hunk, context lines included.

    Measured 1 Sep against the hand-graded real commits, per seed:

        rule       true positives kept   false alarms dropped
        changed          0 / 1                 8 / 32   and  2 / 21
        context          1 / 1                 7 / 32   and  2 / 21

    "changed" discards every true positive to remove a quarter of the noise,
    which makes it unusable as an output filter however good it is as a corpus
    check. The one correct finding in 40 real commits said the code "attempts to
    use `window.Promise`" while the changed lines carry `P.polyfill` and
    `require('es6-promise')` - the model paraphrased instead of citing, and only
    the surrounding context redeems it. Use "context" at inference, "changed"
    when scoring a corpus.

    Under either scope the finding must cite identifiers occurring in that code.
    A finding sharing no vocabulary with what it reviews is describing something
    else. Everything below was measured under "changed" and the thresholds are
    unchanged by the new scope.

    Naming a touched file used to be sufficient on its own. That made this a
    no-op: on a single-file commit every finding names the only file, so all of
    them passed. Measured on 597 corpus findings, 108 (18.1%) qualified by
    filename alone while citing no changed identifier at all, and on live model
    output the shortcut passed 69 of 69 findings. The filename is still
    necessary when given - a finding about a file the commit does not touch is
    not about this commit - but it is no longer sufficient.

    Deleted lines still count. A commit that removes a guard is a real defect
    and the finding legitimately cites the removed code; only 27 of 597 corpus
    findings (4.5%) rest on deleted lines alone.

    One decorated name is enough; plain names need three, unless the changed
    code has no decorated names at all. Plain names are weak evidence - "value"
    and "error" appear in most diffs - and the thresholds were measured on three
    corpora against a control that scores each finding on a RANDOMLY PAIRED
    commit, which is the only way to tell grounding from shared English:

        rule                          real     mismatched    separation
        decorated only (old)         79-89%      0.5-1.5%    +78 to +88pp
        plain admitted freely        96-99%     18-36%       +63 to +72pp
        this rule                    93-94%      2.8-4.6%    +89 to +91pp

    So this is not a loosening: it finds more real groundings AND separates
    better than the old rule on every corpus. Admitting plain names without the
    threshold would ground a third of findings against an unrelated commit.
    """
    if finding.get("file") and finding["file"] not in files_in_diff(diff):
        return False
    if scope == "context":
        changed = "\n".join(l for l in diff.splitlines()
                            if not l.startswith(("diff --git", "index ", "+++",
                                                 "---", "@@")))
    else:
        changed = "\n".join(l for l in diff.splitlines()
                            if l.startswith(("+", "-"))
                            and not l.startswith(("+++", "---")))
    said = finding.get("explanation", "")
    if decorated(said) & decorated(changed):
        return True
    shared = identifiers(said) & identifiers(changed)
    if not decorated(changed):
        # Nothing decorated to match against - C, Makefile, shell. Plain names
        # are all this diff has, so one is all a finding can cite.
        return bool(shared)
    return len(shared) >= 3


def fix_agreement(finding: dict, fix_diff: str) -> float:
    """How much of the finding's vocabulary appears in the real repair.

    Not a proof - a fix touching the same identifiers is strong evidence the
    model pointed at the right thing, but two changes can share names. Reported
    as a rate over many commits, never as a verdict on one.
    """
    if not fix_diff:
        return float("nan")
    said = content_words(finding.get("explanation", ""))
    fixed = content_words(fix_diff)
    return len(said & fixed) / max(len(said), 1)


def confusion(pairs: list[tuple[bool, bool]]) -> dict:
    tp = sum(1 for p, a in pairs if p and a)
    fp = sum(1 for p, a in pairs if p and not a)
    fn = sum(1 for p, a in pairs if not p and a)
    tn = sum(1 for p, a in pairs if not p and not a)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": prec, "recall": rec,
            "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
            "accuracy": (tp + tn) / max(len(pairs), 1)}


def commit_context(repos: Path, rec: dict) -> tuple[str, str] | None:
    """The `-U50` diff and post-commit file bodies for one held-out record.

    Held-out records carry only `project` + `commit_id` + the plain diff, so the
    surrounding code has to come from a local clone. Returns None when the repo
    is not cloned or the commit is not in its history (`--single-branch` clones
    miss commits that never landed on the default branch), which is what lets a
    partial set of clones degrade to the bare-diff path per record instead of
    failing the run.
    """
    from llm_explainer.context import gather

    repo = repos / rec["project"].replace("/", "__")
    if not (repo / ".git").exists():
        return None
    ctx = gather(str(repo), rec["commit_id"])
    if not ctx.diff.strip():
        return None
    blocks = (ctx.context_block(), ctx.framework_block())
    return ctx.expanded_diff or ctx.diff, "\n".join(b for b in blocks if b)


def run(records: list[dict], client, progress=None,
        repos: Path | None = None) -> list[dict]:
    """Ask the model about each held-out commit, keep what it said.

    With `repos`, each commit is reviewed against its surrounding code, the way
    the TUI and `main.py analyze --commit` do. Without it the model sees the
    bare diff, which is what every number published before this flag existed
    measured. `context_chars` records which path each record actually took, so
    a half-cloned repo set cannot quietly average the two.
    """
    out = []
    for i, rec in enumerate(records, 1):
        started = time.time()
        diff, context = rec["diff"], ""
        if repos and (found := commit_context(repos, rec)):
            diff, context = found
        try:
            # chunked=False on purpose: the teacher labelled the whole commit in
            # one prompt and the SFT targets were built the same way. Per-file
            # review is a different task, and scoring it against these labels
            # would measure the chunker rather than the model.
            analysis = client.analyze(diff, subject=rec.get("subject", ""),
                                      files=", ".join(rec.get("files", [])),
                                      chunked=False, context=context)
            said = analysis.model_dump()
            error = None
        except Exception as e:
            said, error = {"summary": "", "findings": []}, f"{type(e).__name__}: {e}"
        out.append({**rec, "predicted": said, "error": error,
                    "context_chars": len(context),
                    "seconds": time.time() - started})
        if progress:
            progress(i, len(records), out[-1])
    return out


def score(results: list[dict]) -> dict:
    usable = [r for r in results if not r["error"]]
    pairs = [(bool(r["predicted"]["findings"]), bool(r["buggy"])) for r in usable]
    conf = confusion(pairs)

    findings = [(f, r) for r in usable for f in r["predicted"]["findings"]]
    grounded_n = sum(1 for f, r in findings if grounded(f, r["diff"]))

    # Detection needs only `buggy`, which SZZ gives for free. A teacher label is
    # required for category match alone, so a commit without one is still worth
    # scoring - which is what makes a large detection eval cost nothing but GPU
    # time.
    teacher_cats = [(set(f["category"] for f in r["analysis"]["findings"]),
                     set(f["category"] for f in r["predicted"]["findings"]))
                    for r in usable if r.get("analysis", {}).get("findings")]
    cat_match = sum(1 for t, p in teacher_cats if t & p)

    # No dataset in data/ carries `fix_diff`, so this is currently always
    # empty. ApacheJIT's `fix` column is a boolean ("is this a fix commit"),
    # not a hash, and the CVEfixes pairs are exact reverses of each other -
    # using the paired record as the repair would make this tautological,
    # since the "fix" holds the same identifiers with +/- swapped. Reported
    # as unavailable rather than hidden; see report().
    agreements = [fix_agreement(f, r.get("fix_diff", "")) for f, r in findings]
    agreements = [a for a in agreements if a == a]  # drop NaN

    return {
        "n": len(results),
        "with_context": sum(1 for r in results if r.get("context_chars")),
        "valid_json": len(usable) / max(len(results), 1),
        **conf,
        "findings_total": len(findings),
        "grounded": grounded_n / max(len(findings), 1),
        "category_match": cat_match / max(len(teacher_cats), 1) if teacher_cats else float("nan"),
        "fix_agreement": sum(agreements) / len(agreements) if agreements else float("nan"),
        "fix_agreement_n": len(agreements),
        "median_seconds": (sorted(r["seconds"] for r in results)[len(results) // 2]
                           if results else float("nan")),
        "categories": dict(Counter(f["category"] for f, _ in findings).most_common(6)),
    }


def paired_bootstrap(a: list[dict], b: list[dict], iters: int = 10000,
                     seed: int = 0) -> dict:
    """Is model A's separation really above model B's, on the same commits?

    Separation (TPR - FPR) rather than F1: at a 50/50 base rate always-buggy
    scores F1 0.67, so F1 rewards a model for saying yes, while separation is
    zero for any constant answer and is base-rate independent.

    Resampling is by `pair` when the records carry one. CVEfixes emits each
    commit twice - forward and reversed - and drawing those two independently
    would treat one commit as two observations and shrink the interval.
    """
    import random

    ka = {r["commit_id"]: r for r in a if not r["error"]}
    kb = {r["commit_id"]: r for r in b if not r["error"]}
    keys = sorted(set(ka) & set(kb))
    groups: dict[str, list[str]] = {}
    for k in keys:
        groups.setdefault(ka[k].get("pair", k), []).append(k)
    blocks = list(groups.values())

    def sep(rows):
        tp = sum(1 for r in rows if r["predicted"]["findings"] and r["buggy"])
        fn = sum(1 for r in rows if not r["predicted"]["findings"] and r["buggy"])
        fp = sum(1 for r in rows if r["predicted"]["findings"] and not r["buggy"])
        tn = sum(1 for r in rows if not r["predicted"]["findings"] and not r["buggy"])
        return tp / max(tp + fn, 1) - fp / max(fp + tn, 1)

    observed = sep([ka[k] for k in keys]) - sep([kb[k] for k in keys])
    rng = random.Random(seed)
    diffs = []
    for _ in range(iters):
        drawn = [k for _ in blocks for k in rng.choice(blocks)]
        diffs.append(sep([ka[k] for k in drawn]) - sep([kb[k] for k in drawn]))
    diffs.sort()
    return {"n": len(keys), "blocks": len(blocks), "diff": observed,
            "lo": diffs[int(0.025 * iters)], "hi": diffs[int(0.975 * iters)],
            "p": sum(1 for d in diffs if d <= 0) / iters}


def report(name: str, s: dict) -> None:
    print(f"\n=== {name} ===")
    print(f"  commits            {s['n']}")
    print(f"  with context       {s['with_context']}/{s['n']}"
          + ("   (bare diff — the pre-2026 published setting)"
             if not s["with_context"] else "   (-U50 + file bodies)"))
    print(f"  valid JSON         {s['valid_json']:.1%}")
    print(f"  detection          P={s['precision']:.2f} R={s['recall']:.2f} "
          f"F1={s['f1']:.2f}  acc={s['accuracy']:.2f}")
    print(f"                     tp={s['tp']} fp={s['fp']} fn={s['fn']} tn={s['tn']}")
    print(f"  findings           {s['findings_total']}")
    print(f"  grounded           {s['grounded']:.1%}   (cites code in the diff)")
    if s["category_match"] == s["category_match"]:
        print(f"  category match     {s['category_match']:.1%}  (vs teacher)")
    if s["fix_agreement"] == s["fix_agreement"]:
        print(f"  fix agreement      {s['fix_agreement']:.1%}  "
              f"(vs the real repair, n={s['fix_agreement_n']})")
    else:
        # Silence here read as "fine"; it meant the measure never ran.
        print("  fix agreement      unavailable — no `fix_diff` on these "
              "records, so the explanation is unscored")
    print(f"  median latency     {s['median_seconds']:.1f}s")
    print(f"  categories         {s['categories']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heldout", type=Path, default=HELDOUT)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--model", type=Path, help="local model dir (transformers)")
    ap.add_argument("--backend", choices=("auto", "transformers", "ollama"),
                    default="auto")
    ap.add_argument("--model-name", help="served model name, for --backend ollama")
    ap.add_argument("--host", help="served host, e.g. http://localhost:8111")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "eval_results.jsonl")
    ap.add_argument("--name", default="model")
    ap.add_argument("--context", action="store_true",
                    help="review against -U50 and full file bodies from local "
                         "clones, the way the TUI does (default: bare diff)")
    ap.add_argument("--repos", type=Path, default=CLONE_DIR,
                    help="where the clones live, for --context")
    ap.add_argument("--clone", action="store_true",
                    help="clone the projects --context needs, then continue")
    ap.add_argument("--compare", nargs="+", type=Path,
                    help="score existing result files instead of running a model")
    ap.add_argument("--paired", nargs=2, type=Path, metavar=("A", "B"),
                    help="paired bootstrap of A's separation against B's")
    args = ap.parse_args(argv)

    if args.compare or args.paired:
        for path in (args.compare or []) + (args.paired or []):
            rows = [json.loads(l) for l in open(path) if l.strip()]
            report(path.stem, score(rows))
        if args.paired:
            rows = [[json.loads(l) for l in open(p) if l.strip()] for p in args.paired]
            s = paired_bootstrap(*rows)
            print(f"\n=== {args.paired[0].stem} - {args.paired[1].stem} ===")
            print(f"  paired on         {s['n']} commits in {s['blocks']} blocks")
            print(f"  separation diff   {s['diff'] * 100:+.1f}pp   "
                  f"95% CI [{s['lo'] * 100:+.1f}, {s['hi'] * 100:+.1f}]")
            print(f"  bootstrap p       {s['p']:.4f}   "
                  f"({'significant' if s['hi'] * s['lo'] > 0 else 'CI spans zero'})")
        return 0

    if not args.heldout.exists():
        raise SystemExit(f"{args.heldout} not found — split the corpus first")

    records = [json.loads(l) for l in open(args.heldout) if l.strip()][: args.limit]
    print(f"{len(records)} held-out commits "
          f"({sum(r['buggy'] for r in records)} buggy)")

    repos = None
    if args.context:
        wanted = sorted({r["project"] for r in records})
        if args.clone:
            for slug in wanted:
                clone(slug, args.repos)
        have = [s for s in wanted
                if (args.repos / s.replace("/", "__") / ".git").exists()]
        # Fail here rather than after 200 slow calls: without clones every
        # record silently falls back to the bare diff and the run reports a
        # no-context number under a --context banner.
        if not have:
            raise SystemExit(
                f"--context needs clones in {args.repos}; none of "
                f"{len(wanted)} projects are there. Re-run with --clone.")
        if len(have) < len(wanted):
            print(f"  WARNING: {len(wanted) - len(have)} of {len(wanted)} "
                  f"projects not cloned; those commits fall back to the bare "
                  f"diff (see `with context` in the report)")
        repos = args.repos

    from llm_explainer.client import OracleClient

    kwargs = {"backend": args.backend}
    if args.model:
        kwargs["model_path"] = args.model
    if args.model_name:
        kwargs["ollama_model"] = args.model_name
    if args.host:
        kwargs["ollama_host"] = args.host
    client = OracleClient(**kwargs)
    print(f"backend: {client.backend}")

    def progress(i, n, row):
        mark = "!" if row["error"] else len(row["predicted"]["findings"])
        if i % 10 == 0 or i == 1:
            print(f"  {i}/{n}  findings={mark}  ({row['seconds']:.0f}s)", flush=True)

    results = run(records, client, progress, repos=repos)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as fh:
        for r in results:
            fh.write(json.dumps(r) + "\n")
    report(args.name, score(results))
    print(f"\nresults -> {args.out}")
    return 0


if __name__ == "__main__":
    # The scoring functions decide every number in the paper, so they get tested.
    diff = ("diff --git a/auth/session.py b/auth/session.py\n"
            "+++ b/auth/session.py\n"
            "@@ -1 +1 @@\n"
            "-        if token.expires_at > now():\n"
            "+        if token.expires_at >= now():\n")
    assert files_in_diff(diff) == {"auth/session.py"}

    good = {"category": "off-by-one", "file": "auth/session.py",
            "explanation": "token.expires_at now admits the boundary"}
    assert grounded(good, diff)
    vague = {"category": "other", "file": "",
             "explanation": "something somewhere may be wrong"}
    assert not grounded(vague, diff), "a finding citing nothing is not grounded"
    # The regression this function existed to catch and did not: naming the
    # touched file while citing nothing in it.
    named = {"category": "other", "file": "auth/session.py",
             "explanation": "something somewhere may be wrong"}
    assert not grounded(named, diff), "a filename alone does not ground a finding"
    # A finding about a file the commit never touched is not about this commit.
    elsewhere = {"category": "other", "file": "other/module.py",
                 "explanation": "token.expires_at now admits the boundary"}
    assert not grounded(elsewhere, diff), "wrong file is not grounded"

    # Plain names were invisible before: this diff carries no `_`, `.` or
    # camelCase hump, so its vocabulary read as EMPTY and no finding about it
    # could ever ground, however correct. C and Makefile diffs look like this.
    cdiff = ("diff --git a/util.c b/util.c\n+++ b/util.c\n@@ -1 +1 @@\n"
             "-    memcpy(buf, src, len);\n"
             "+    memcpy(buf, src, size);\n")
    # grounded() reads only the changed lines, and those carry no decorated
    # name - the `util.c` in the header does, which is why this checks the code.
    cbody = "-    memcpy(buf, src, len);\n+    memcpy(buf, src, size);"
    assert not decorated(cbody), "nothing in this diff's code is decorated"
    assert identifiers(cbody) >= {"memcpy", "buf", "src", "len", "size"}
    plain = {"category": "buffer-overflow", "file": "util.c",
             "explanation": "the copy now uses size rather than len, overrunning buf"}
    assert grounded(plain, cdiff), "a plain identifier must ground a finding"
    # ...but English scaffolding and language keywords still must not: they
    # occur in every diff and are evidence of nothing.
    assert "the" not in identifiers("the loop")
    assert "return" not in identifiers("return x")
    assert identifiers("CFLAGS was dropped") >= {"cflags"}, "all-caps macros count"
    prose = {"category": "other", "file": "util.c",
             "explanation": "this change may be wrong in some cases"}
    assert not grounded(prose, cdiff), "prose alone is not grounding"
    # Known limit, deliberately kept: the token regex needs three characters, so
    # `i`, `n` and `xs` stay invisible. Admitting two-character tokens would let
    # stray prose ("is", "as", "it") ground a finding, which is the failure this
    # function exists to catch.
    assert identifiers("i n xs") == set()

    # A diff that DOES carry decorated names needs three plain matches, so one
    # incidental word in common is not grounding.
    pydiff = ("+++ b/svc.py\n@@ -1 +1 @@\n"
              "-    result = client.fetch(size, retries)\n"
              "+    result = client.fetch(count, retries)\n")
    assert decorated(pydiff), "this diff has decorated names, so the threshold applies"
    one = {"category": "other", "file": "svc.py",
           "explanation": "the result may be wrong"}
    assert not grounded(one, pydiff), "one plain word in common is not grounding"
    three = {"category": "logic-error", "file": "svc.py",
             "explanation": "fetch now takes count where it took size, so retries is unchanged"}
    assert grounded(three, pydiff), "three plain names shared is grounding"

    # scope="context": the 1 Sep case. The finding paraphrases a symbol that is
    # in the file but not on a changed line, so "changed" rejects it and
    # "context" keeps it. Both behaviours are wanted, for different callers.
    ctxdiff = """diff --git a/lib/axios.js b/lib/axios.js
--- a/lib/axios.js
+++ b/lib/axios.js
@@ -5,7 +5,1 @@
 var utils = require('./utils');
 var nativePromise = window.Promise;
-  var P = require('es6-promise');
-  P.polyfill();
"""
    para = {"file": "lib/axios.js",
            "explanation": "axios attempts to use window.Promise, which throws "
                           "a ReferenceError in browsers without native support"}
    assert not grounded(para, ctxdiff), "changed-lines must still reject a paraphrase"
    assert grounded(para, ctxdiff, scope="context"), "context must keep it"
    # and the wrong-file guard has to survive the wider scope
    assert not grounded({"file": "nope.js", "explanation": "window.Promise"},
                        ctxdiff, scope="context"), "wrong file stays ungrounded"

    fix = "-        if token.expires_at >= now():\n+        if token.expires_at > now():\n"
    assert fix_agreement(good, fix) > 0.3, fix_agreement(good, fix)
    unrelated = {"category": "other", "explanation": "database connection pooling leaks"}
    assert fix_agreement(unrelated, fix) < 0.2

    c = confusion([(True, True), (True, False), (False, True), (False, False)])
    assert (c["tp"], c["fp"], c["fn"], c["tn"]) == (1, 1, 1, 1)
    assert abs(c["f1"] - 0.5) < 1e-9
    # The context path is the difference between a published number and a
    # different published number, so it gets a check too.
    import subprocess, tempfile

    with tempfile.TemporaryDirectory() as tmp:
        repos = Path(tmp)
        target = repos / "acme__widget"
        target.mkdir(parents=True)
        run_git = lambda *a: subprocess.run(["git", "-C", str(target), *a],
                                            check=True, capture_output=True)
        run_git("init", "-q")
        run_git("config", "user.email", "t@t")
        run_git("config", "user.name", "t")
        body = "\n".join(f"line {i}" for i in range(80))
        (target / "widget.py").write_text(body + "\nvalue = 1\n")
        run_git("add", "-A")
        run_git("commit", "-qm", "seed")
        (target / "widget.py").write_text(body + "\nvalue = 2\n")
        run_git("add", "-A")
        run_git("commit", "-qm", "bump")
        rev = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"],
                             capture_output=True, text=True).stdout.strip()

        rec = {"project": "acme/widget", "commit_id": rev}
        got = commit_context(repos, rec)
        assert got is not None, "a cloned repo must yield context"
        wide, context = got
        assert "line 40" in wide, "-U50 must reach well past the changed line"
        assert "value = 2" in context, "context block must carry the file body"

        assert commit_context(repos, {**rec, "project": "acme/absent"}) is None
        assert commit_context(repos, {**rec, "commit_id": "0" * 40}) is None

    print("scoring functions ok")
    raise SystemExit(main())
