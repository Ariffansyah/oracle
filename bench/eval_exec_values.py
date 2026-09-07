"""Score the VALUE tier of an exec-corpus checkpoint by generating, not forcing.

`verdict_eval` in train_sft is teacher-forced at one token: it answers "does the
model say `differs` correctly", which the corpus makes learnable from family
identity for 92% of rows. It cannot answer the question the direction exists for
-- can the model COMPUTE the before/after values -- because that needs decoding.

    python bench/eval_exec_values.py --adapter artifacts/sft-exec \
        --dataset data/exec_sft_ctx_holdout_cross.jsonl --limit 60

Run with --base-only for the untrained control. The two numbers together are the
ablation for the value tier; the verdict number alone is not.

Scored separately for differs=true and differs=false rows, because they fail
differently: on a `false` row the two values are equal and a model that learned
to copy one field into the other scores while computing nothing. A `false` row
still requires computing the value -- it is not free -- but it is the easier half,
so a single pooled number hides which half is working.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import BASE_MODEL  # noqa: E402
from exec_contract import contradiction, repair  # noqa: E402

_OBJ = re.compile(r"\{.*?\}", re.S)


# Shared so the brace-counting bug that blanked 18 BugsInPy rows -- and
# any review whose failure message contained a lone brace -- is fixed in
# exactly one place. See oracle_reviewer/jsonio.py.
from oracle_reviewer.jsonio import first_json  # noqa: E402


def norm(v) -> str:
    """Compare values as strings, whitespace-collapsed.

    The target stores them as strings already; a model that emits 105 instead of
    "105" is right about the computation and wrong about the type, which is a
    formatting fault, not a reasoning one.
    """
    return re.sub(r"\s+", " ", str(v)).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--adapter", type=Path,
                    help="LoRA dir; omit (or --base-only) for the untrained control")
    ap.add_argument("--base-only", action="store_true")
    ap.add_argument("--base-model", default=BASE_MODEL)
    ap.add_argument("--four-bit", action="store_true",
                    help="load in nf4 — fits this card and matches serve.sh")
    ap.add_argument("--limit", type=int, default=60)
    # The v1 target was ~68 chars of JSON; adding `explanation` took it to
    # ~248, and 96 tokens cut the JSON off mid-sentence -- which scores as
    # a wrong answer rather than as a truncated one. 320 clears the p99.
    ap.add_argument("--max-new-tokens", type=int, default=320)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.dataset)][:args.limit]
    if not rows:
        sys.exit(f"{args.dataset} is empty")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(args.base_model)
    # A 3B in fp16 is ~6.2GB and this card has 6.0, so `device_map="auto"`
    # silently offloads layers to CPU and generation drops to ~24s/row. 4-bit
    # fits with room to spare AND is what serve.sh actually deploys, so the
    # measurement matches the precision the app will run.
    kw = {"device_map": "auto"}
    if args.four_bit:
        from transformers import BitsAndBytesConfig
        kw["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
    else:
        kw["torch_dtype"] = torch.float16
    model = AutoModelForCausalLM.from_pretrained(args.base_model, **kw)
    tag = "base"
    if args.adapter and not args.base_only:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, str(args.adapter))
        tag = str(args.adapter)
    model.eval()

    n = Counter()
    out_rows = []
    for r in rows:
        msgs = r["messages"][:-1]
        gold = json.loads(r["messages"][-1]["content"])
        prompt = tok.apply_chat_template(msgs, tokenize=False,
                                         add_generation_prompt=True)
        ids = tok(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            gen = model.generate(**ids, max_new_tokens=args.max_new_tokens,
                                 do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        text = tok.decode(gen[0][ids["input_ids"].shape[1]:],
                          skip_special_tokens=True)
        got = first_json(text)
        d = bool(gold["differs"])
        bucket = "T" if d else "F"
        n[f"n_{bucket}"] += 1
        rec = {"family": r.get("family"), "differs": d, "raw": text[:400]}
        if got is None:
            n[f"unparsed_{bucket}"] += 1
        else:
            n["parsed"] += 1
            if bool(got.get("differs")) == d:
                n[f"verdict_{bucket}"] += 1
            b_ok = norm(got.get("before")) == norm(gold["before"])
            a_ok = norm(got.get("after")) == norm(gold["after"])
            n[f"before_{bucket}"] += b_ok
            n[f"after_{bucket}"] += a_ok
            n[f"both_{bucket}"] += (b_ok and a_ok)
            # `differs` and `before != after` are the same claim. When they
            # disagree the emission is invalid on its face, with no gold needed
            # -- which is what makes this usable at inference and not only here.
            why = contradiction(got)
            n["contradictory"] += bool(why)
            # The repaired score is NOT the model's score: it is what a caller
            # that ran the code recovers by pinning the pre-state to its own
            # measurement and keeping the model's value as the post-state.
            fixed, _ = repair(got, gold["before"], gold["after"])
            n[f"rep_both_{bucket}"] += (norm(fixed.get("before")) == norm(gold["before"])
                                        and norm(fixed.get("after")) == norm(gold["after"]))
            rec.update(got_before=got.get("before"), got_after=got.get("after"),
                       gold_before=gold["before"], gold_after=gold["after"],
                       contradictory=why,
                       both=bool(b_ok and a_ok))
        out_rows.append(rec)

    tot = n["n_T"] + n["n_F"]
    pct = lambda a, b: f"{a}/{b} ({a / b:.0%})" if b else "0/0 (n/a)"
    print(f"\n=== {tag}  on {args.dataset.name}  n={tot}")
    print(f"  parsed JSON        {pct(n['parsed'], tot)}")
    print(f"  verdict correct    {pct(n['verdict_T'] + n['verdict_F'], tot)}")
    print(f"  VALUES both right  {pct(n['both_T'] + n['both_F'], tot)}   <- the tier that matters")
    print(f"  self-contradictory {pct(n['contradictory'], tot)}   verdict disagrees with its own values")
    print(f"  + measured before  {pct(n['rep_both_T'] + n['rep_both_F'], tot)}   "
          f"model's after, pre-state pinned to the measurement (NOT a model score)")
    for b, lab in (("T", "differs=true "), ("F", "differs=false")):
        print(f"    {lab}  before {pct(n[f'before_{b}'], n[f'n_{b}'])}"
              f"   after {pct(n[f'after_{b}'], n[f'n_{b}'])}"
              f"   both {pct(n[f'both_{b}'], n[f'n_{b}'])}"
              f"   unparsed {n[f'unparsed_{b}']}")
    if args.out:
        args.out.write_text(json.dumps({"tag": tag, "counts": dict(n),
                                        "rows": out_rows}, indent=1))
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
