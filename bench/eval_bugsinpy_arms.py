"""The three-arm ablation again, on real bugs instead of synthetic ones.

`bench/eval_explain_arms.py` ran exec / score / diff over 519 mutants and found
exec 93%, score 39%, diff 39%, with score and diff indistinguishable (p=0.699).
Two objections survived it, and both are about the corpus rather than the
result:

  * the rows were synthetic, so "quotes both values" is a claim about tidy
    ten-line programs, not about code anybody maintains
  * the gate had no history to work from, scored AUC 0.557, and therefore the
    score arm was narrating noise

This is the same comparison on BugsInPy: real projects, real bugs, the
project's own failing test, and a gate with all 14 metrics live.

What is scored changes with the corpus, and it has to. A real bug's `after` is
just "the test passes" and carries no information, so "quotes both values" would
be measuring nothing. What separates a grounded explanation from a fluent one
here is whether it gets the OBSERVED FAILURE right:

  names_exception    it names the exception class the test actually raised
  quotes_signature   it reproduces a distinctive part of the real message
  invents_exception  it names some OTHER exception, and not the real one
  names_file         it names the file the patch actually touches

`invents_exception` is the counter-example the synthetic corpus could not
produce, and it is the failure that matters: an explanation that confidently
reports a ValueError where the program raised a TypeError reads exactly as well
as a correct one.

    python bench/eval_bugsinpy_arms.py --arm exec  --out data/bip_arm_exec.json
    python bench/eval_bugsinpy_arms.py --arm score --out data/bip_arm_score.json
    python bench/eval_bugsinpy_arms.py --arm diff  --out data/bip_arm_diff.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SYSTEM = """You are ORACLE, a code reviewer. You are given one commit from a real project.

Answer with one JSON object and one key:

  "explanation"   one or two sentences telling a developer what this change does
                  to the behaviour the project's own tests observe. Name the
                  construct that changed, and quote the exact failure it fixes."""

EXTRA = {
    "exec": "\n\n## Measured by running the project's own test\n"
            "before: {before}\nafter:  {after}",
    "score": "\n\n## Defect predictor\nA just-in-time defect model scores this "
             "commit at {score:.1%} risk of introducing a defect.",
    "diff": "",
}

_EXC = re.compile(r"\b([A-Z]\w*(?:Error|Exception))\b")
_STOP = {"the", "and", "for", "with", "that", "this", "was", "not", "object",
         "has", "does", "have", "from", "are", "but", "its", "into", "such"}


# Shared so the brace-counting bug that blanked 18 BugsInPy rows -- and
# any review whose failure message contained a lone brace -- is fixed in
# exactly one place. See oracle_reviewer/jsonio.py.
from oracle_reviewer.jsonio import first_json  # noqa: E402


def diff_of(user: str) -> str:
    m = re.search(r"```diff\n(.*?)```", user, re.S)
    return m.group(1) if m else user


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def message_of(sig: str) -> str:
    """The part of a failure signature after the exception class."""
    m = re.match(r"^[A-Za-z_][\w.]*(?:Error|Exception):\s*(.*)$", sig.strip())
    return (m.group(1) if m else sig).strip()


def _tokens(msg: str) -> list[str]:
    """The parts of a failure message an explanation would have to reproduce.

    Numbers count. Half this corpus fails on a bare assertion -- `assert 0 == 6`,
    `assert not 'a' > 'a'` -- where the whole informative content IS the
    operands, and dropping short tokens left `assert` alone and scored a model
    that wrote "previously asserted 0 == 6" as having quoted nothing.
    """
    # \w+ and not [\w']+: these messages are full of quoted identifiers, and a
    # token of "'galaxyapi'" never matches an explanation that writes the name
    # without the quotes -- which is what an explanation normally does.
    out = []
    for t in re.findall(r"\w+", msg):
        if t.isdigit() or (len(t) > 2 and t not in _STOP):
            out.append(t)
    return out


def quotes_signature(expl: str, sig: str) -> bool:
    """Exact containment, or most of the message's distinctive tokens."""
    msg = norm(message_of(sig))
    if not msg:
        return False
    e = norm(expl)
    if msg and msg in e:
        return True
    toks = _tokens(msg)
    if len(toks) < 2:
        return False
    # A short or numeric token has to match as a word. Substring matching lets
    # "6" hit any explanation containing "16" or "60", and at these lengths that
    # is most of them.
    def hit(t: str) -> bool:
        if t.isdigit() or len(t) <= 3:
            return re.search(rf"\b{re.escape(t)}\b", e) is not None
        return t in e
    return sum(hit(t) for t in toks) / len(toks) >= 0.7


def invents_exception(expl: str, exc: str, signature: str = "") -> str | None:
    """An exception the explanation names that the measurement never produced.

    The measured signature can name more than one class, and both are measured.
    `AssertionError: ValueError not raised by follow` is a test asserting that a
    ValueError SHOULD have been raised: an explanation saying the commit now
    raises a ValueError is exactly right, and counting it as an invention was
    wrong. Same for cookiecutter-4, whose signature is `AttributeError: module
    'cookiecutter.exceptions' has no attribute 'FailedHookException'`. Anything
    the failure itself mentions is on the record; only names from nowhere count.
    """
    named = {m.group(1) for m in _EXC.finditer(expl or "")}
    if not named:
        return None
    measured = {m.group(1) for m in _EXC.finditer(signature or "")}
    if exc:
        measured.add(exc)
    # Naming something that was measured is grounding, and grounding is not
    # invention -- an explanation reading "a TypeError, not a ValueError" is
    # contrasting, not fabricating. Only an explanation that names an exception
    # and none of the measured ones has asserted a failure out of nothing.
    if named & measured:
        return None
    other = sorted(named - measured)
    if not other:
        return None
    seen = ", ".join(sorted(measured)) if measured else "no exception"
    return f"says {', '.join(other)}; the measured failure names {seen}"


_KEYWORDS = {"self", "none", "true", "false", "return", "import", "from",
             "class", "elif", "else", "with", "def", "for", "while", "not",
             "and", "or", "in", "is", "if", "try", "except", "raise", "pass",
             "lambda", "assert", "print", "type", "str", "int", "list", "dict"}


def names_symbol(expl: str, diff: str) -> bool:
    """Does the explanation name something the patch actually touched?

    Not the FILE. The model is asked to name the construct that changed, and it
    does exactly that -- "the `start` argument", "the `__gt__` method" -- so a
    file-name check scored 0/6 on explanations that had located the change
    correctly. What is worth checking is whether the identifier it names is one
    that appears on a changed line.
    """
    idents = set()
    for line in diff.split("\n"):
        if line[:1] not in "+-" or line[:2] in ("++", "--"):
            continue
        for t in re.findall(r"[A-Za-z_]\w{3,}", line):
            if t.lower() not in _KEYWORDS:
                idents.add(t)
    e = norm(expl)
    return any(t.lower() in e for t in idents)


def from_commit_message(expl: str, subject: str, exc: str) -> bool:
    """Was the exception it named taken from the commit message?

    httpie-1's subject is "Fixed #451 - OSError: [Errno 36] File name too long".
    The measured failure is an AttributeError. The model reported the OSError --
    it repeated what the author wrote instead of what the test did. ORACLE's own
    training prompt says to trust the code and not the message; this counts how
    often that instruction loses.
    """
    named = {m.group(1) for m in _EXC.finditer(expl or "")} - {exc}
    if not named:
        return False

    subj = norm(subject)
    return any(n.lower() in subj for n in named)


def generate_local(prompts: list[str], args) -> list[str]:
    """The 3B, here, on the GPU. `--no-adapter` gives the untrained base."""
    import torch
    from peft import PeftModel
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              BitsAndBytesConfig)
    from config import BASE_MODEL

    name = args.base_model or BASE_MODEL
    tok = AutoTokenizer.from_pretrained(name, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        name, device_map={"": 0},
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True))
    if not args.no_adapter:
        model = PeftModel.from_pretrained(model, str(args.adapter))
    model.eval()
    print(f"  {name}" + ("" if args.no_adapter else f" + {args.adapter.name}"),
          flush=True)

    # Batch, and batch rows of SIMILAR length together: these diffs run from a
    # few hundred characters to several thousand, and padding a short prompt out
    # to the longest in its batch spends the whole saving on nothing. Greedy
    # decoding makes this reordering safe -- each row's output does not depend on
    # what it is batched with -- and the original order is restored afterwards.
    if getattr(args, "prompt", "plain") == "strong":
        from bench.strong_prompt import messages as _turns
        print("  prompt: strong (system + 3 hand-written examples)", flush=True)
    else:
        def _turns(u):
            return [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": u}]
    prompts = [tok.apply_chat_template(_turns(u), tokenize=False,
                                       add_generation_prompt=True)
               for u in prompts]
    order = sorted(range(len(prompts)), key=lambda i: len(prompts[i]))
    texts: list[str] = [""] * len(prompts)
    for start in range(0, len(order), args.batch):
        idx = order[start:start + args.batch]
        # Length-sorting puts the LONGEST prompts in the final batches, so an
        # over-large batch does not fail early -- it fails at row 400 of 458 and
        # takes the whole run with it, because nothing is written until the end.
        # That happened once with `--prompt strong`, whose few-shot prefix adds
        # ~900 tokens to every row. Falling back to one row at a time costs a
        # few seconds on the handful of batches that need it.
        def _run(sel):
            batch = tok([prompts[i] for i in sel], return_tensors="pt",
                        padding=True).to(model.device)
            with torch.no_grad():
                out = model.generate(**batch, max_new_tokens=args.max_new_tokens,
                                     do_sample=False,
                                     pad_token_id=tok.pad_token_id)
            return batch, out
        try:
            batch, gen = _run(idx)
        except torch.OutOfMemoryError:
            torch.cuda.empty_cache()
            print(f"  OOM on a batch of {len(idx)}; retrying one at a time",
                  flush=True)
            for i in idx:
                try:
                    b1, g1 = _run([i])
                    texts[i] = tok.decode(g1[0][b1["input_ids"].shape[1]:],
                                          skip_special_tokens=True)
                except torch.OutOfMemoryError:
                    torch.cuda.empty_cache()
                    print(f"  OOM on a single row; skipping {i}", flush=True)
                    texts[i] = ""
            print(f"  {start + len(idx)}/{len(prompts)}", flush=True)
            continue
        cut = batch["input_ids"].shape[1]
        for k, i in enumerate(idx):
            texts[i] = tok.decode(gen[k][cut:], skip_special_tokens=True)
        done = start + len(idx)
        if done % 40 < args.batch:
            print(f"  {done}/{len(prompts)}", flush=True)
    return texts


def generate_api(prompts: list[str], args) -> list[str]:
    """A hosted model, for the "why not just use a big one" question.

    Reuses corpus.label.ask, which paces on the rate-limit headers and rotates
    keys -- on a free tier a 429 is the normal case, not an error.
    """
    from corpus.label import PROVIDERS, ask

    provider = PROVIDERS[args.provider]
    print(f"  {args.provider}:{args.api_model}", flush=True)
    texts = []
    for i, prompt in enumerate(prompts, 1):
        try:
            texts.append(ask(provider, args.api_model, SYSTEM, prompt,
                             temperature=0.0, timeout=90))
        except Exception as e:  # noqa: BLE001
            print(f"  row {i}: {type(e).__name__}: {e}"[:160], flush=True)
            texts.append("")
        if i % 40 == 0:
            print(f"  {i}/{len(prompts)}", flush=True)
    return texts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=list(EXTRA), required=True)
    ap.add_argument("--dataset", type=pathlib.Path,
                    default=ROOT / "data/bugsinpy_rows.jsonl")
    ap.add_argument("--scores", type=pathlib.Path,
                    default=ROOT / "data/bugsinpy_gate_scores.json")
    ap.add_argument("--adapter", type=pathlib.Path,
                    default=ROOT / "artifacts/oracle-reviewer-3b")
    ap.add_argument("--prompt", choices=("plain", "strong"), default="plain",
                    help="plain is the published arms; strong is the "
                         "hand-built few-shot baseline in bench/strong_prompt.py")
    ap.add_argument("--no-adapter", action="store_true",
                    help="the untrained base model, as the reference the trained "
                         "number needs")
    ap.add_argument("--base-model", default=None)
    ap.add_argument("--backend", choices=("local", "api"), default="local",
                    help="`api` asks a hosted model over an OpenAI-compatible "
                         "endpoint instead of loading weights here")
    ap.add_argument("--provider", default="groq")
    ap.add_argument("--api-model", default="openai/gpt-oss-120b")
    ap.add_argument("--limit", type=int, default=0)
    # 320 was the synthetic bench's budget. A real explanation here is one or
    # two sentences inside a small JSON object; 128 tokens has never truncated
    # one, and on a 1660 SUPER the difference is hours.
    ap.add_argument("--max-new-tokens", type=int, default=128)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--max-diff-chars", type=int, default=6000)
    ap.add_argument("--out", type=pathlib.Path)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.dataset)]
    if args.limit:
        rows = rows[:args.limit]
    scores = {}
    if args.arm == "score":
        scores = json.loads(args.scores.read_text())
        missing = [r["id"] for r in rows
                   if (scores.get(r["id"]) or {}).get("score") is None]
        if missing:
            print(f"WARNING: {len(missing)} rows have no gate score and are "
                  f"dropped from every arm to keep the comparison paired: "
                  f"{missing[:5]}")
        rows = [r for r in rows
                if (scores.get(r["id"]) or {}).get("score") is not None]

    prompts = []
    for r in rows:
        user = r["messages"][1]["content"]
        if len(user) > args.max_diff_chars:
            user = user[:args.max_diff_chars] + "\n...(diff truncated)\n```"
        user += EXTRA[args.arm].format(
            before=r["before"], after=r["after"],
            score=(scores.get(r["id"], {}) or {}).get("score", 0.0))
        prompts.append(user)

    if args.backend == "api":
        texts = generate_api(prompts, args)
    else:
        texts = generate_local(prompts, args)

    n = {"parsed": 0, "exception": 0, "signature": 0, "invented": 0,
         "from_message": 0, "symbol": 0, "grounded": 0}
    out_rows = []
    for i, r in enumerate(rows, 1):
        expl = str((first_json(texts[i - 1]) or {}).get("explanation") or "")

        exc_ok = bool(expl) and bool(r["exception"]) and r["exception"] in expl
        sig_ok = bool(expl) and quotes_signature(expl, r["before"])
        inv = invents_exception(expl, r["exception"], r["before"]) if expl else None
        f_ok = bool(expl) and names_symbol(expl, diff_of(r["messages"][1]["content"]))
        msg_ok = bool(inv) and from_commit_message(expl, r.get("subject", ""),
                                                   r["exception"])
        n["parsed"] += bool(expl)
        n["exception"] += exc_ok
        n["signature"] += sig_ok
        n["invented"] += bool(inv)
        n["from_message"] += msg_ok
        n["symbol"] += f_ok
        n["grounded"] += bool((exc_ok or sig_ok) and not inv)
        # `raw` is kept ONLY when nothing parsed. 18 rows of the v3 arm scored
        # "produced no explanation" and the arm file had no way to say whether
        # that was the model or the parser -- it was the parser, and diagnosing
        # it cost a re-run of all 458. Storing the unparsed text makes the same
        # question answerable from the file. It is capped and it is absent on
        # the ~96% of rows that parse, so the file does not grow meaningfully.
        row = {"id": r["id"], "project": r["project"],
               "exception": r["exception"], "before": r["before"],
               "explanation": expl[:800], "names_exception": exc_ok,
               "quotes_signature": sig_ok, "invented": inv,
               "from_message": msg_ok, "names_symbol": f_ok}
        if not expl:
            row["raw"] = str(texts[i - 1])[:2000]
        out_rows.append(row)

    tot = len(rows)
    pct = lambda a: f"{a}/{tot} ({a / tot:.0%})" if tot else "0/0"
    print(f"\n=== arm {args.arm}  n={tot}")
    print(f"  produced an explanation      {pct(n['parsed'])}")
    print(f"  names the real exception     {pct(n['exception'])}")
    print(f"  quotes the real message      {pct(n['signature'])}")
    print(f"  names a changed identifier   {pct(n['symbol'])}")
    print(f"  INVENTS a different failure  {pct(n['invented'])}   <- the one that hurts")
    print(f"    ...of those, taken from the commit message: {n['from_message']}")
    print(f"  grounded (right, not invented) {pct(n['grounded'])}")
    if args.out:
        args.out.write_text(json.dumps({"arm": args.arm, "counts": n,
                                        "n": tot, "rows": out_rows}, indent=1))
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
