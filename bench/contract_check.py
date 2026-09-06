"""Does the model emit the fields the guards read, and does the base model?

`oracle_reviewer/core.explain` asks for ONE key, "explanation", then checks the
answer with `swapped` and `contradiction`. Both of those read `differs`,
`before` and `after` -- fields the prompt never requests. core.py:517 asserts
they arrive anyway, because the checkpoint was trained on the four-field exec
contract (`data/exec_sft_v2.jsonl`: 1103 of 1103 targets carry all four).

That assertion had never been tested, and it matters more than it looks:

  * `contradiction` returns None the moment the three keys are absent --
    "not the v2 contract; nothing to check"
  * `swapped` compares obj.get("before") to the measurement, and a missing key
    can never match, so it returns False

So on a model that emits only `explanation`, BOTH GUARDS FAIL OPEN. No error,
no warning, nothing withheld -- the safety layer is simply not running. The
458-row deployed run fired them 0 times, which is equally consistent with "the
model is always right about direction" and "the guards were dead the whole
time". This tells them apart.

    python bench/contract_check.py --limit 40              # the tuned model
    python bench/contract_check.py --limit 40 --no-adapter # the base model

Reports, per model: how often all four fields arrive, how often only the one
that was asked for arrives, and therefore how often the guards had anything to
check at all.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bench.eval_bugsinpy_arms import diff_of, first_json  # noqa: E402
from exec_contract import contradiction, swapped  # noqa: E402
from oracle_reviewer import core  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=pathlib.Path,
                    default=ROOT / "data/bugsinpy_rows_v2.jsonl")
    ap.add_argument("--adapter", type=pathlib.Path,
                    default=ROOT / "artifacts/oracle-reviewer-3b")
    ap.add_argument("--no-adapter", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--max-new-tokens", type=int, default=200)
    ap.add_argument("--out", type=pathlib.Path)
    args = ap.parse_args()

    import torch
    from peft import PeftModel
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              BitsAndBytesConfig)
    from config import BASE_MODEL

    rows = [json.loads(l) for l in open(args.dataset)][:args.limit]
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, device_map={"": 0},
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True))
    if not args.no_adapter:
        model = PeftModel.from_pretrained(model, str(args.adapter))
    model.eval()
    which = "BASE (no adapter)" if args.no_adapter else "oracle-reviewer-3b"
    print(f"  {which}", flush=True)

    n = collections.Counter()
    shapes = collections.Counter()
    out_rows = []
    for i, r in enumerate(rows, 1):
        # core's own prompt, exactly as the TUI sends it.
        user = core.USER.format(
            path=(r["patch_files"] or ["?"])[0], message=r.get("subject", ""),
            diff=diff_of(r["messages"][1]["content"])[:9000],
            cmd=(r["run_test"] or ["the project's test"])[0],
            before=r["before"], after=r["after"],
            outcome=("the run started PASSING after this change"
                     if r["differs"] else
                     "the run behaved the same before and after"))
        prompt = tok.apply_chat_template(
            [{"role": "system", "content": core.SYSTEM},
             {"role": "user", "content": user}],
            tokenize=False, add_generation_prompt=True)
        ids = tok(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            gen = model.generate(**ids, max_new_tokens=args.max_new_tokens,
                                 do_sample=False, pad_token_id=tok.pad_token_id)
        text = tok.decode(gen[0][ids["input_ids"].shape[1]:],
                          skip_special_tokens=True)
        got = first_json(text) or {}
        keys = tuple(sorted(k for k in got if k in
                            ("differs", "before", "after", "explanation")))
        shapes[keys] += 1
        full = {"differs", "before", "after"} <= set(got)
        n["parsed"] += bool(got)
        n["four_field"] += full
        n["explanation_only"] += bool(got) and not full
        # Could the guards have checked anything on this answer?
        n["contradiction_live"] += contradiction(got) is not None or full
        n["swapped_checkable"] += full and r["before"] != r["after"]
        n["swapped_fired"] += bool(swapped(got, r["before"], r["after"]))
        out_rows.append({"id": r["id"], "keys": list(keys), "four_field": full})
        if i % 10 == 0:
            print(f"  {i}/{len(rows)}", flush=True)

    tot = len(rows)
    pct = lambda a: f"{a}/{tot} ({a / tot:.0%})"
    print(f"\n=== contract check: {which}  n={tot}")
    print(f"  parsed a JSON object          {pct(n['parsed'])}")
    print(f"  emitted all of differs/before/after  {pct(n['four_field'])}")
    print(f"  emitted only what was asked for      {pct(n['explanation_only'])}")
    print(f"  guards had something to check        {pct(n['swapped_checkable'])}")
    print(f"  `swapped` actually fired             {pct(n['swapped_fired'])}")
    print("\n  key-sets emitted, most common first:")
    for k, v in shapes.most_common(6):
        print(f"    {v:4d}  {list(k) or '(none)'}")
    if args.out:
        args.out.write_text(json.dumps(
            {"model": which, "n": tot, "counts": dict(n),
             "shapes": {",".join(k): v for k, v in shapes.items()},
             "rows": out_rows}, indent=1))
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
