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
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent / "basic"

# A case is labelled one of three ways, not two. `buggy` and `clean` are what
# bench/basic carries; `fix` and `refactor` come from bench/clean_direction and
# exist because "behaviour-preserving" and "introduces no defect" are different
# claims. A commit that REPAIRS a bug changes behaviour and is still clean, so a
# two-value flag has to call it buggy and cannot express it.
#
#   buggy     pre and post must differ    -> a finding is expected
#   clean     pre and post must match     -> a finding is a PROVED false alarm
#   refactor  pre and post must match     -> same as clean, named for what it is
#   fix       pre and post must differ    -> a finding is a proved false alarm,
#                                            and the one the model gets wrong by
#                                            reporting the defect it just removed
MUST_DIFFER = {"buggy": True, "clean": False, "refactor": False, "fix": True}

# Case directories that are TRAINING data for the mechanism checkpoints. Scoring
# a model on these measures memorisation, and the resulting number is not an
# evaluation of anything. The guard exists because the directories sit beside
# the eval sets and `--root` makes them one flag away from a headline figure —
# which is precisely the class of mistake this project keeps finding in its own
# apparatus. `bench/mechanism_heldout` and `bench/clean_heldout` are the
# held-out counterparts: same style, families the training never saw.
TRAINING_ROOTS = {"mechanism_pilot", "clean_direction"}

# Languages that run a source file directly. Anything needing a compile or a
# module file gets an explicit branch in _run().
INTERP = {
    "javascript": ["node"],
    "python":     [sys.executable],
    # Deno runs .ts without a tsconfig or a tsc install, and `deno run` does
    # not type-check, so this measures runtime behaviour like every other case.
    "typescript": ["deno", "run", "-q"],
    "ruby":       ["ruby"],
    "php":        ["php"],
    # Java 11+ single-file source launcher: no javac step, no class-name match.
    "java":       ["java"],
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
        elif lang == "rust":
            # No -O: debug assertions are on by default, which is what turns a
            # silent integer overflow into a visible panic.
            exe = tmp / "a.out"
            comp = subprocess.run(["rustc", "-o", str(exe), str(work)],
                                  capture_output=True, text=True)
            if comp.returncode != 0:
                return comp.returncode, comp.stdout + comp.stderr
            cmd = [str(exe)]
        elif lang in INTERP:
            cmd = [*INTERP[lang], str(work)]
        else:
            raise SystemExit(f"no runner for {lang}")
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               cwd=tmp, timeout=90)
        except FileNotFoundError as e:
            # No runtime for this language on this machine. Say which one
            # instead of dumping a traceback from inside the verifier.
            raise SystemExit(
                f"{case['id']}: {lang} needs {e.filename!r}, which is not "
                f"installed here") from None
        return p.returncode, (p.stdout + p.stderr).strip()


def load_cases() -> list[dict]:
    """Every case under ROOT, with `label` and `buggy` both filled in.

    The two schemas are normalised here so the scorer never has to know which
    directory a case came from: only `fix`/`buggy` expect a finding.
    """
    out = []
    for meta in sorted(ROOT.glob("*/meta.json")):
        c = json.loads(meta.read_text())
        if "label" not in c:
            c["label"] = "buggy" if c.get("buggy") else "clean"
        c["buggy"] = c["label"] == "buggy"
        if c["label"] not in MUST_DIFFER:
            raise SystemExit(f"{meta}: unknown label {c['label']!r}; "
                             f"expected one of {sorted(MUST_DIFFER)}")
        out.append(c)
    return out


def verify(cases: list[dict]) -> int:
    """Prove each label by execution. Returns the number of bad cases."""
    bad = 0
    w = _idw(cases)
    print(f"{'case':<{w}}{'lang':<12}{'label':<9}{'pre':>6}{'post':>6}  verdict")
    for c in cases:
        rc_pre, out_pre = _run(c, "pre")
        rc_post, out_post = _run(c, "post")
        differs = (rc_pre, out_pre) != (rc_post, out_post)
        ok = differs == MUST_DIFFER[c["label"]]
        bad += not ok
        print(f"{c['id']:<{w}}{c['language']:<12}"
              f"{c['label']:<9}{rc_pre:>6}{rc_post:>6}  "
              f"{'OK' if ok else 'BAD LABEL'}"
              + ("" if ok else f"   pre={out_pre[:40]!r} post={out_post[:40]!r}"))
    print(f"\n{len(cases) - bad}/{len(cases)} cases verified by execution")
    return bad


def diff_of(case: dict, word: bool = False, module: bool = False) -> str:
    """Render one case as a diff. `word` switches to --word-diff=plain.

    A unified diff shows an edited line as a removal plus an addition, and the
    model reads that literally: on the pystruct annotation commit it reported
    that a docstring line was "removed" when the line was expanded in place.
    --word-diff marks the change inside the line - [-gone-]{+added+} - which
    makes an in-place edit unmistakable. It is a representation the model was
    NOT fine-tuned on, so it is measured, not assumed.

    `module` renders word-diffs with `dataset_builder.worddiff` instead of git,
    and that distinction is not cosmetic. The SFT corpora carry only diff text —
    the original blobs are gone — so `sft_mechanism_v2` was rendered by that
    module, whose output matches real git on 76% of cases and differs in
    difflib-vs-git alignment on the rest. Scoring a word-diff-trained checkpoint
    against git's rendering measures a train/inference mismatch, which is the
    exact failure the module was written to avoid. Use `module` for any model
    trained on word-diffs; `word` reproduces the 25 Aug inference-swap result.
    """
    if word and module:
        raise ValueError("pick one word-diff renderer, not both")
    d = ROOT / case["id"]
    name = f"{case['id']}.{case['ext']}"
    p = subprocess.run(
        ["git", "diff", "--no-index", "--no-color"]
        + (["--word-diff=plain"] if word else [])
        + [f"--src-prefix=a/", f"--dst-prefix=b/",
           str(d / f"pre.{case['ext']}"), str(d / f"post.{case['ext']}")],
        capture_output=True, text=True)
    # git diff --no-index exits 1 when files differ, which is the normal case
    out = p.stdout
    if module:
        from dataset_builder.worddiff import to_word_diff
        out = to_word_diff(out)
    return (out.replace(str(d / f"pre.{case['ext']}"), name)
               .replace(str(d / f"post.{case['ext']}"), name))


def _idw(cases: list[dict]) -> int:
    """Width of the case-id column, from the ids themselves.

    This was hardcoded at 22, which is exactly len("java-concurrent-modify"),
    so that row printed "java-concurrent-modifyjava" with no separating space.
    Deriving it means a longer id can never fuse the columns again.
    """
    return max((len(c["id"]) for c in cases), default=20) + 2


# Every dash-like character a model might emit. The 3B wrote "null\u2011coalescing"
# with a non-breaking hyphen, which an ASCII [-_] class does not match.
_DASHES = r"[-_\u2010\u2011\u2012\u2013\u2014\u2015\u2212]+"


def _flat(text: str) -> str:
    """Lowercase, and treat any dash or _ as a space, so "out-of-bounds",
    "out\u2011of\u2011bounds" and "out of bounds" all compare equal."""
    return re.sub(r"\s+", " ", re.sub(_DASHES, " ", text.lower()))


def identified(case: dict, said: dict) -> bool:
    """Does the answer cite the identifiers the real defect lives in.

    Searches the summary as well as the findings: the model often names the
    faulty construct in one and not the other, and scoring only explanations
    marked a correct py-range-bound answer as a hallucination.

    This checks *locus*, not correctness. It cannot detect an inverted claim -
    go-accum-reset described the hoisted accumulator as newly added inside the
    loop, cited the right identifier, and passed. Cases still need eyeballing;
    this number is a floor, not a verdict.

    Dashes and underscores are flattened to spaces on both sides: the base 3B
    wrote "out-of-bounds" where the case asks for "out of bounds", and a plain
    substring test graded that correct answer a hallucination.

    Each `must_mention` entry is a REQUIREMENT; a list is a set of ALTERNATIVES
    that satisfy it. All requirements must be met, any one alternative meets
    its own. A bare string is a one-alternative requirement, so old cases still
    work. Alternatives exist because a correct explanation may paraphrase
    rather than quote - sft-ml8-grounded said "returns the first n-1 elements
    instead of the first n" without ever writing `array_slice`, and demanding
    the token turned that correct answer into a reported hallucination.
    """
    must = case.get("must_mention", [])
    if not must:
        return False
    blob = _flat(" ".join([said.get("summary", "")]
                          + [f.get("explanation", "")
                             for f in said.get("findings") or []]))
    return all(
        any(_flat(alt) in blob
            for alt in ([req] if isinstance(req, str) else req))
        for req in must)


# Cache: grading the effect needs the real before/after, and `--score` would
# otherwise re-run every case for every stored file.
_OUT_CACHE: dict[str, tuple[str, str]] = {}


def outputs(case: dict) -> tuple[str, str]:
    """The executed (pre, post) output for a case, as the grader's ground truth."""
    key = case["id"]
    if key not in _OUT_CACHE:
        rc_pre, out_pre = _run(case, "pre")
        rc_post, out_post = _run(case, "post")
        _OUT_CACHE[key] = (f"rc={rc_pre} {out_pre}", f"rc={rc_post} {out_post}")
    return _OUT_CACHE[key]


# The model is never handed a filesystem path: `build_user_message` passes a
# bare `name.ext` and the diff headers carry `a/name.ext`. So an absolute path
# in an answer is fabricated by construction, not recalled. On 27 Aug six v2
# answers cited one, all under bench/mechanism_pilot/, none of which exist.
_ABS_PATH = re.compile(r"(?<![\w-])/(?:[\w.-]+/)+[\w.-]+")

_FAILURE_WORDS = (
    "panic", "exception", "error", "overflow", "out of range", "out of bounds",
    "index", "nil", "null", "undefined", "nan", "race", "deadlock", "timeout",
    "divide by zero", "zerodivision", "segfault", "segmentation",
)


def _obs_match(claim: str, actual: str) -> bool:
    """Does a claimed observable correspond to what the program actually did.

    Deliberately lenient, because the model paraphrases: a real trace runs to
    twenty lines and a correct answer says "panic: index out of range". Strict
    equality would score correct answers as wrong, which is the mistake the
    grounding checker already made once.

    Three ways to match, in order of strength: containment either way; the
    claim's integers all appear in the real output (a numeric result is the
    commonest observable); or claim and reality name the same runtime failure.
    """
    c, a = _flat(claim), _flat(actual)
    if not c or not a:
        return False
    if c in a or a in c:
        return True
    cn, an = set(re.findall(r"-?\d+", c)), set(re.findall(r"-?\d+", a))
    if cn and cn <= an:
        return True
    return any(w in c and w in a for w in _FAILURE_WORDS)


def grade_effect(case: dict, said: dict) -> dict:
    """Grade the v2 behavioural claim. All keys are None when none was made.

    Two tiers, because they answer different questions:

      direction_ok  did the model get which way the code moved. This is the
                    robust tier and the one that catches the failure that has
                    dominated every hand-grade - an answer that names the right
                    construct and describes the change backwards. `identified()`
                    cannot see that; this can.
      observable_ok did the claimed before/after correspond to what running the
                    code actually prints. The strict tier.

    `fabricated` is separate and is proof, not suspicion: an absolute path the
    model was never given, or a claimed behaviour change on a case whose two
    sides are byte-identical.
    """
    eff = said.get("effect")
    if not isinstance(eff, dict):
        return {"effect_claimed": False, "effect_direction_ok": None,
                "effect_observable_ok": None, "effect_fabricated": None}

    truth = {"buggy": "post-breaks", "fix": "post-fixes"}.get(case["label"], "unchanged")
    claimed = str(eff.get("direction", "")).strip().lower()

    pre_out, post_out = outputs(case)
    before, after = str(eff.get("before", "")), str(eff.get("after", ""))
    observable_ok = _obs_match(before, pre_out) and _obs_match(after, post_out)

    blob = " ".join([eff.get("trigger", ""), before, after])
    identical = pre_out == post_out
    fabricated = bool(_ABS_PATH.search(blob)) or (
        identical and claimed in ("post-breaks", "post-fixes"))

    return {"effect_claimed": True,
            "effect_direction_ok": claimed == truth,
            "effect_observable_ok": observable_ok,
            "effect_fabricated": fabricated}


def grade(case: dict, said: dict) -> dict:
    """Grade one answer.

    The live run and --score both go through here, so a re-score of stored rows
    can never disagree with the run that produced them.

    Two failures were once folded into one "hallucinated" count, and they are
    not the same claim:

      false_alarm   a finding on a case whose pre and post produce byte-identical
                    output. Execution PROVES nothing changed, so the finding is
                    fabricated. This is the number the goal means by "no
                    hallucination".
      unconfirmed   a correct verdict on a buggy case whose explanation did not
                    name the defect. The scorer could not confirm the locus,
                    which is weaker than proof of invention - four of these were
                    correct paraphrases that simply avoided the expected token.

    `hallucinated` stays as their union so stored rows keep their schema, but
    report the two apart: only false_alarm is evidence of fabrication.
    """
    flagged = bool(said.get("findings"))
    verdict_ok = flagged == case["buggy"]
    ident = identified(case, said) if case["buggy"] else False
    false_alarm = flagged and not case["buggy"]
    unconfirmed = flagged and case["buggy"] and not ident
    return {"flagged": flagged, "verdict_ok": verdict_ok, "identified": ident,
            "false_alarm": false_alarm, "unconfirmed": unconfirmed,
            "hallucinated": false_alarm or unconfirmed,
            **grade_effect(case, said)}


# A call that raises is scored as "said nothing", which on a clean case reads
# as a pass. That is the right treatment for one flaky request and the wrong
# one for an outage: pointing the runner at a dead port, or at a python without
# `requests`, produced "13/46, 0 false alarms" — every clean case passing by
# default — which looks like a result and is the absence of one. Anything above
# this share of errored calls is an apparatus failure, not a model score.
MAX_ERROR_RATE = 0.20


def summarise(rows: list[dict], label: str = "") -> None:
    n = len(rows)
    errs = sum(bool(r.get("error")) for r in rows)
    if n and errs / n > MAX_ERROR_RATE:
        kinds = sorted({str(r["error"]).split(":")[0] for r in rows if r.get("error")})
        raise SystemExit(
            f"\n{errs}/{n} calls FAILED ({100*errs/n:.0f}%) — {', '.join(kinds)}\n"
            f"No score is printed: a failed call is scored as 'no finding', so an\n"
            f"outage would report every clean case as a pass and look like a\n"
            f"result. Fix the backend and rerun.")
    v = sum(r["verdict_ok"] for r in rows)
    fully = sum(r["verdict_ok"] and (r["identified"] or not r["buggy"]) for r in rows)
    fa = sum(r.get("false_alarm", False) for r in rows)
    un = sum(r.get("unconfirmed", False) for r in rows)
    if label:
        print(f"\n{label}")
    if errs:
        print(f"\n  !! {errs}/{n} calls errored and are scored as 'no finding'")
    print(f"\n  verdict correct     {v}/{n}   ({100*v/n:.0f}%)")
    print(f"  fully correct       {fully}/{n}   ({100*fully/n:.0f}%)   <- the 8/10 target")
    print(f"  false alarms        {fa}/{n}   ({100*fa/n:.0f}%)   <- findings on code proved unchanged; must be 0")
    print(f"  locus unconfirmed   {un}/{n}   ({100*un/n:.0f}%)   <- right verdict, defect not named")

    # --- the v2 behavioural claim ------------------------------------------
    # Reported over the answers that MADE a claim, not over n. A v1 checkpoint
    # makes none, and printing 0/46 as though it had failed the tier would
    # misread "did not answer this question" as "answered it wrongly".
    claimed = [r for r in rows if r.get("effect_claimed")]
    if not claimed:
        # Say WHICH contract produced the zero. Under v1 it is expected; under v2
        # it is a finding, and the hardcoded "v1 contract" label hid exactly that
        # distinction when the row writer was dropping the effect_* keys.
        from config import OUTPUT_CONTRACT
        why = ("v1 contract: no checkable behavioural claim" if OUTPUT_CONTRACT != "v2"
               else "v2 contract: NO answer carried an effect - check the row writer "
                    "and the served prompt before reading this as a model result")
        print(f"  effect claimed      0/{n}   <- {why}")
        return
    c = len(claimed)
    d = sum(bool(r.get("effect_direction_ok")) for r in claimed)
    o = sum(bool(r.get("effect_observable_ok")) for r in claimed)
    f = sum(bool(r.get("effect_fabricated")) for r in claimed)
    print(f"  effect claimed      {c}/{n}   ({100*c/n:.0f}%)")
    print(f"  ├ direction right   {d}/{c}   ({100*d/c:.0f}%)   <- which way the code moved; catches inversions")
    print(f"  ├ observable right  {o}/{c}   ({100*o/c:.0f}%)   <- claimed before/after matches what ran")
    print(f"  └ FABRICATED        {f}/{c}   ({100*f/c:.0f}%)   <- invented path, or a change on identical output; must be 0")


def rescore(path: Path) -> list[dict]:
    """Re-grade a stored run with the CURRENT scorer.

    Scorer fixes land after runs do - the hyphen fix moved the base model a
    whole case - and a 44-case GPU run costs half an hour. Re-reading the
    stored answers costs nothing, so stored rows are never trusted for their
    own verdict; only `predicted` is.
    """
    cases = {c["id"]: c for c in load_cases()}
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        c = cases.get(r["id"])
        if c is None:
            continue  # a case deleted since the run; nothing to grade against
        out.append({**r, **grade(c, r["predicted"])})
    return out


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
    ap.add_argument("--root", type=Path,
                    help="directory of case dirs to score (default bench/basic). "
                         "bench/mechanism_pilot and bench/clean_direction have "
                         "never been scored as benchmarks, only used as training "
                         "data — this is how you score them.")
    ap.add_argument("--word-diff", action="store_true",
                    help="render cases with git --word-diff=plain instead of unified")
    ap.add_argument("--word-diff-module", action="store_true",
                    help="render word-diffs with dataset_builder.worddiff, the "
                         "renderer that built the sft_mechanism_v2 corpus. Use "
                         "this for word-diff-trained checkpoints: git and the "
                         "module agree on only 76%% of cases, so the other "
                         "renderer measures a train/inference mismatch.")
    ap.add_argument("--score", type=Path, metavar="ROWS.jsonl",
                    help="re-grade a stored run with the current scorer and exit; "
                         "runs no model and needs no language toolchain")
    args = ap.parse_args(argv)

    if args.root:
        globals()["ROOT"] = args.root.resolve()
        if not ROOT.is_dir():
            raise SystemExit(f"{ROOT} is not a directory")
        if ROOT.name in TRAINING_ROOTS and not args.verify:
            print(f"\n!!! {ROOT.name} is TRAINING data for the mechanism\n"
                  f"!!! checkpoints. A score here measures memorisation, not\n"
                  f"!!! ability, and must not be reported as an evaluation.\n"
                  f"!!! Use bench/mechanism_heldout or bench/clean_heldout.\n")

    if args.score:
        rows = rescore(args.score)
        w = _idw(load_cases())
        if not rows:
            raise SystemExit(f"no gradable rows in {args.score}")
        for r in rows:
            mark = ("correct" if (r["verdict_ok"] and (r["identified"] or not r["buggy"]))
                    else "FALSE ALARM" if r["false_alarm"]
                    else "unconfirmed" if r["unconfirmed"] else "miss")
            print(f"  {r['id']:<{w}}{r['language']:<12}{mark}")
        summarise(rows, f"{args.score.name}   {len(rows)} cases")
        return 0

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
    w = _idw(cases)
    print(f"\n{'case':<{w}}{'label':<8}{'said':<8}{'findings':>9}  outcome")
    for c in cases:
        diff = diff_of(c, word=args.word_diff, module=args.word_diff_module)
        try:
            a = client.analyze(diff, subject=f"({c['id']})",
                               files=f"{c['id']}.{c['ext']}", chunked=False)
            said = a.model_dump()
            err = None
        except Exception as e:
            said, err = {"summary": "", "findings": []}, f"{type(e).__name__}: {e}"
        fs = said.get("findings") or []
        g = grade(c, said)
        flagged, verdict_ok, ident, halluc = (
            g["flagged"], g["verdict_ok"], g["identified"], g["hallucinated"])
        # Spread `g` whole. Hand-picking its keys dropped every effect_* tier on
        # the way into the row, so summarise() saw no effect_claimed on any row
        # and printed the hardcoded "0/n - v1 contract" line no matter what the
        # model had emitted. The pilot's first run reported 0/46 effect claimed
        # while all 46 answers carried a well-formed effect object.
        rows.append({**{k: c[k] for k in ("id", "language", "buggy", "category")},
                     **g, "predicted": said, "error": err})
        mark = ("correct" if (verdict_ok and (ident or not c["buggy"]))
                else "HALLUCINATION" if halluc else "miss")
        print(f"{c['id']:<{w}}{'buggy' if c['buggy'] else 'clean':<8}"
              f"{'buggy' if flagged else 'clean':<8}{len(fs):>9}  {mark}"
              + (f"   [{err}]" if err else ""))

    summarise(rows)
    if args.out:
        args.out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        print(f"\nrows -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
