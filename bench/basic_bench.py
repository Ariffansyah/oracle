"""Basic-algorithm benchmark: can the reviewer get simple code right?

Every eval set in this repo labels commits by SZZ, which is inferred and noisy.
These cases are small enough to *run*, so ground truth is proved rather than
assumed: a buggy case is one where post misbehaves and pre does not, and a
clean case is one where both produce byte-identical output. `--verify` re-checks
that on every invocation, so a case cannot rot into a wrong label.

    python bench/basic_bench.py --verify
    python bench/basic_bench.py --backend ollama --model-name oracle-merged \
        --host http://localhost:8111

Scoring is deliberately harsher than detection F1, which cannot tell a correct
finding from a fluent one:

  verdict     did buggy/clean match
  identified  on a buggy case, does the explanation cite the code at fault
  clean       on a clean case, ANY finding is a false alarm
  halluc.     a wrong verdict with a confident finding, or a finding on clean
              code - the failure that sends someone to fix a non-bug
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent / "basic"

RUN = {
    "go":         lambda f: (["go", "run", f.name], True),
    "javascript": lambda f: (["node", f.name], False),
    "python":     lambda f: ([sys.executable, f.name], False),
    "c":          lambda f: (None, False),  # compiled below
}


def _run(case: dict, which: str) -> tuple[int, str]:
    """Run one side of a case. Returns (returncode, stdout+stderr)."""
    src = ROOT / case["id"] / f"{which}.{case['ext']}"
    lang = case["language"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        work = tmp / f"main.{case['ext']}"
        work.write_text(src.read_text())
        if lang == "c":
            # -fsanitize=address turns a silent out-of-bounds read into a
            # visible failure; without it c-array-bound often "passes".
            exe = tmp / "a.out"
            comp = subprocess.run(
                ["gcc", "-std=c11", "-Wall", "-fsanitize=address,undefined",
                 "-g", "-o", str(exe), str(work)],
                capture_output=True, text=True)
            if comp.returncode != 0:
                return comp.returncode, comp.stdout + comp.stderr
            cmd = [str(exe)]
        elif lang == "go":
            (tmp / "go.mod").write_text("module bench\ngo 1.21\n")
            cmd = ["go", "run", str(work)]
        elif lang == "javascript":
            cmd = ["node", str(work)]
        elif lang == "python":
            cmd = [sys.executable, str(work)]
        else:
            raise SystemExit(f"no runner for {lang}")
        p = subprocess.run(cmd, capture_output=True, text=True,
                           cwd=tmp, timeout=90)
        return p.returncode, (p.stdout + p.stderr).strip()


def load_cases() -> list[dict]:
    out = []
    for meta in sorted(ROOT.glob("*/meta.json")):
        out.append(json.loads(meta.read_text()))
    return out


def verify(cases: list[dict]) -> int:
    """Prove each label by execution. Returns the number of bad cases."""
    bad = 0
    print(f"{'case':<22}{'lang':<12}{'label':<8}{'pre':>6}{'post':>6}  verdict")
    for c in cases:
        rc_pre, out_pre = _run(c, "pre")
        rc_post, out_post = _run(c, "post")
        differs = (rc_pre, out_pre) != (rc_post, out_post)
        ok = differs if c["buggy"] else not differs
        bad += not ok
        print(f"{c['id']:<22}{c['language']:<12}"
              f"{'buggy' if c['buggy'] else 'clean':<8}{rc_pre:>6}{rc_post:>6}  "
              f"{'OK' if ok else 'BAD LABEL'}"
              + ("" if ok else f"   pre={out_pre[:40]!r} post={out_post[:40]!r}"))
    print(f"\n{len(cases) - bad}/{len(cases)} cases verified by execution")
    return bad


def diff_of(case: dict) -> str:
    d = ROOT / case["id"]
    name = f"{case['id']}.{case['ext']}"
    p = subprocess.run(
        ["git", "diff", "--no-index", "--no-color",
         f"--src-prefix=a/", f"--dst-prefix=b/",
         str(d / f"pre.{case['ext']}"), str(d / f"post.{case['ext']}")],
        capture_output=True, text=True)
    # git diff --no-index exits 1 when files differ, which is the normal case
    out = p.stdout
    return (out.replace(str(d / f"pre.{case['ext']}"), name)
               .replace(str(d / f"post.{case['ext']}"), name))


def identified(case: dict, said: dict) -> bool:
    """Does the answer cite the identifiers the real defect lives in.

    Searches the summary as well as the findings: the model often names the
    faulty construct in one and not the other, and scoring only explanations
    marked a correct py-range-bound answer as a hallucination.

    This checks *locus*, not correctness. It cannot detect an inverted claim -
    go-accum-reset described the hoisted accumulator as newly added inside the
    loop, cited the right identifier, and passed. Cases still need eyeballing;
    this number is a floor, not a verdict.
    """
    must = [m.lower() for m in case.get("must_mention", [])]
    if not must:
        return False
    blob = " ".join([said.get("summary", "")]
                    + [f.get("explanation", "") for f in said.get("findings") or []]).lower()
    return all(m in blob for m in must)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", action="store_true",
                    help="only re-prove the labels by execution, run no model")
    ap.add_argument("--backend", default="ollama")
    ap.add_argument("--model", help="local model dir, for --backend transformers")
    ap.add_argument("--model-name", help="served model name")
    ap.add_argument("--host", help="served host")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    cases = load_cases()
    if not cases:
        raise SystemExit(f"no cases in {ROOT}")

    bad = verify(cases)
    if bad:
        raise SystemExit(f"{bad} case(s) do not behave as labelled — fix before scoring")
    if args.verify:
        return 0

    from llm_explainer.client import OracleClient
    kw = {"backend": args.backend}
    if args.host:
        kw["ollama_host"] = args.host
    if args.model_name:
        kw["ollama_model"] = args.model_name
    client = OracleClient(args.model, **kw) if args.model else OracleClient(**kw)

    rows = []
    print(f"\n{'case':<22}{'label':<8}{'said':<8}{'findings':>9}  outcome")
    for c in cases:
        diff = diff_of(c)
        try:
            a = client.analyze(diff, subject=f"({c['id']})",
                               files=f"{c['id']}.{c['ext']}", chunked=False)
            said = a.model_dump()
            err = None
        except Exception as e:
            said, err = {"summary": "", "findings": []}, f"{type(e).__name__}: {e}"
        fs = said.get("findings") or []
        flagged = bool(fs)
        verdict_ok = flagged == c["buggy"]
        ident = identified(c, said) if c["buggy"] else False
        # A confident finding that is not about the real defect, or any finding
        # on code that provably did not change behaviour.
        halluc = (flagged and not c["buggy"]) or (flagged and c["buggy"] and not ident)
        rows.append({**{k: c[k] for k in ("id", "language", "buggy", "category")},
                     "predicted": said, "error": err, "verdict_ok": verdict_ok,
                     "identified": ident, "hallucinated": halluc})
        mark = ("correct" if (verdict_ok and (ident or not c["buggy"]))
                else "HALLUCINATION" if halluc else "miss")
        print(f"{c['id']:<22}{'buggy' if c['buggy'] else 'clean':<8}"
              f"{'buggy' if flagged else 'clean':<8}{len(fs):>9}  {mark}"
              + (f"   [{err}]" if err else ""))

    n = len(rows)
    v = sum(r["verdict_ok"] for r in rows)
    fully = sum(1 for r in rows
                if r["verdict_ok"] and (r["identified"] or not r["buggy"]))
    h = sum(r["hallucinated"] for r in rows)
    print(f"\n  verdict correct     {v}/{n}   ({100*v/n:.0f}%)")
    print(f"  fully correct       {fully}/{n}   ({100*fully/n:.0f}%)   <- the 8/10 target")
    print(f"  hallucinated        {h}/{n}   ({100*h/n:.0f}%)   <- must be 0")
    if args.out:
        args.out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        print(f"\nrows -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
