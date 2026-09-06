"""What the explanation is conditioned on: execution, a risk score, or nothing.

    python bench/eval_explain_arms.py --arm exec  --out data/arm_exec.json
    python bench/eval_explain_arms.py --arm score --out data/arm_score.json
    python bench/eval_explain_arms.py --arm diff  --out data/arm_diff.json

The claim this exists to test is the one POSITIONING.md makes: the explanation is
conditioned on MEASURED execution and never on the predictor's probability, so it
cannot inherit the predictor's errors. That comparison had never been run.

Three arms, same 519 cross-family held-out rows, same model, same decode:

    exec    the diff, plus the measured before/after
    score   the diff, plus a JIT defect probability
    diff    the diff alone

Scored identically, against gold:

    quotes both   the true before AND after appear in the explanation
    reversed      it states the change in the wrong direction
    phantom       it claims a removal the diff does not contain

`exec` is GIVEN the values, so quoting them is not a feat -- that is precisely
the architectural advantage being claimed, and the number to read is how far
`score` and `diff`, which must derive them, fall short.

CAVEAT for the `score` arm: these rows are synthetic, so the gate has no git
history and its 14 Kamei metrics are zero-filled -- only the GraphCodeBERT
channel is live. On this corpus that scorer reaches AUC 0.557, barely above
chance. `score` is therefore narrating a near-uninformative number, which is a
fact about what a predictor can say here, not a handicap chosen for it.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from exec_contract import direction_reversed, norm, phantom_removal  # noqa: E402

SYSTEM = """You are ORACLE, a code reviewer. You are given one commit.

Answer with one JSON object and one key:

  "explanation"   one or two sentences telling a developer what this change does
                  to what the program prints. Quote the exact values involved."""

EXTRA = {
    "exec": "\n\n## Measured by running the program\nbefore: {before}\nafter:  {after}",
    "score": "\n\n## Defect predictor\nA just-in-time defect model scores this "
             "commit at {score:.1%} risk of introducing a defect.",
    "diff": "",
}


def first_json(text: str) -> dict | None:
    for m in re.finditer(r"\{", text):
        depth = 0
        for j in range(m.start(), len(text)):
            depth += (text[j] == "{") - (text[j] == "}")
            if depth == 0:
                try:
                    v = json.loads(text[m.start():j + 1])
                except Exception:
                    break
                return v if isinstance(v, dict) else None
    return None


def diff_of(user: str) -> str:
    m = re.search(r"```diff\n(.*?)```", user, re.S)
    return m.group(1) if m else user


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=list(EXTRA), required=True)
    ap.add_argument("--dataset", type=pathlib.Path,
                    default=ROOT / "data/exec_sft_v2_holdout_cross.jsonl")
    ap.add_argument("--scores", type=pathlib.Path,
                    default=ROOT / "data/gate_scores.json")
    ap.add_argument("--adapter", type=pathlib.Path,
                    default=ROOT / "artifacts/oracle-reviewer-3b")
    ap.add_argument("--base-model", default=None)
    ap.add_argument("--limit", type=int, default=519)
    ap.add_argument("--max-new-tokens", type=int, default=320)
    ap.add_argument("--out", type=pathlib.Path)
    args = ap.parse_args()

    import torch
    from peft import PeftModel
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              BitsAndBytesConfig)
    from config import BASE_MODEL

    rows = [json.loads(l) for l in open(args.dataset)][:args.limit]
    scores = (json.load(open(args.scores)) if args.arm == "score"
              else [0.0] * len(rows))

    tok = AutoTokenizer.from_pretrained(args.base_model or BASE_MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model or BASE_MODEL, device_map={"": 0},
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True))
    model = PeftModel.from_pretrained(model, str(args.adapter))
    model.eval()

    n = {"parsed": 0, "before": 0, "after": 0, "both": 0,
         "reversed": 0, "phantom": 0}
    out_rows = []
    for i, r in enumerate(rows):
        gold = json.loads(r["messages"][-1]["content"])
        user = r["messages"][1]["content"] + EXTRA[args.arm].format(
            before=gold["before"], after=gold["after"], score=scores[i])
        prompt = tok.apply_chat_template(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            tokenize=False, add_generation_prompt=True)
        ids = tok(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            gen = model.generate(**ids, max_new_tokens=args.max_new_tokens,
                                 do_sample=False, pad_token_id=tok.eos_token_id)
        text = tok.decode(gen[0][ids["input_ids"].shape[1]:],
                          skip_special_tokens=True)
        got = first_json(text) or {}
        expl = str(got.get("explanation") or "")
        n["parsed"] += bool(expl)
        b_ok = bool(expl) and norm(gold["before"]) in norm(expl)
        a_ok = bool(expl) and norm(gold["after"]) in norm(expl)
        n["before"] += b_ok
        n["after"] += a_ok
        n["both"] += (b_ok and a_ok)
        rev = direction_reversed(expl, gold["before"], gold["after"])
        pha = phantom_removal(expl, diff_of(r["messages"][1]["content"]))
        n["reversed"] += bool(rev)
        n["phantom"] += bool(pha)
        out_rows.append({"family": r.get("family"), "differs": r["differs"],
                         "explanation": expl[:600], "quotes_before": b_ok,
                         "quotes_after": a_ok, "reversed": rev,
                         "phantom": pha, "score": scores[i]})

    tot = len(rows)
    pct = lambda a: f"{a}/{tot} ({a / tot:.0%})"
    print(f"\n=== arm {args.arm}  n={tot}")
    print(f"  produced an explanation   {pct(n['parsed'])}")
    print(f"  quotes the true BEFORE    {pct(n['before'])}")
    print(f"  quotes the true AFTER     {pct(n['after'])}")
    print(f"  quotes BOTH               {pct(n['both'])}   <- the tier that matters")
    print(f"  states it BACKWARDS       {pct(n['reversed'])}")
    print(f"  invents a removal         {pct(n['phantom'])}")
    if args.out:
        args.out.write_text(json.dumps({"arm": args.arm, "counts": n,
                                        "rows": out_rows}, indent=1))
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
