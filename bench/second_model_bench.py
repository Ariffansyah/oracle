"""Run the 46-case basic-algorithm benchmark against a second model over the
Groq API (openai/gpt-oss-120b), reusing the exact scoring path bench/basic_bench.py
uses so the numbers are directly comparable to oracle-merged's. Read-only:
writes only to the given --out path, touches nothing else in the repo.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dataset_builder.schema import SYSTEM_PROMPT, Analysis, build_user_message
from llm_explainer.client import extract_json
from corpus.label import PROVIDERS, ask
import bench.basic_bench as bb
from config import MAX_DIFF_CHARS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="groq")
    ap.add_argument("--model", default=None, help="override provider's default model")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--word-diff", action="store_true")
    args = ap.parse_args()

    provider = PROVIDERS[args.provider]
    model = args.model or provider.model

    cases = bb.load_cases()
    bad = bb.verify(cases)
    if bad:
        raise SystemExit(f"{bad} case(s) do not behave as labelled")

    rows = []
    w = bb._idw(cases)
    print(f"\n{'case':<{w}}{'label':<8}{'said':<8}{'findings':>9}  outcome")
    for c in cases:
        diff = bb.diff_of(c, word=args.word_diff)
        user = build_user_message(
            diff, subject=f"({c['id']})", files=f"{c['id']}.{c['ext']}",
            max_diff_chars=MAX_DIFF_CHARS, context="", include_schema=True)
        err = None
        said = {"summary": "", "findings": []}
        try:
            raw = ask(provider, model, SYSTEM_PROMPT, user, temperature=0.0, timeout=60)
            try:
                said = Analysis.model_validate(extract_json(raw)).model_dump()
            except Exception:
                # one repair turn, same shape as OracleClient.analyze
                raw2 = ask(provider, model, SYSTEM_PROMPT,
                           user + f"\n\nThat was rejected. Reply with ONLY a JSON "
                                  f"object matching the schema.",
                           temperature=0.0, timeout=60)
                said = Analysis.model_validate(extract_json(raw2)).model_dump()
        except Exception as e:
            err = f"{type(e).__name__}: {e}"

        fs = said.get("findings") or []
        g = bb.grade(c, said)
        flagged, verdict_ok, ident, halluc = (
            g["flagged"], g["verdict_ok"], g["identified"], g["hallucinated"])
        rows.append({**{k: c[k] for k in ("id", "language", "buggy", "category")},
                     "false_alarm": g["false_alarm"], "unconfirmed": g["unconfirmed"],
                     "predicted": said, "error": err, "verdict_ok": verdict_ok,
                     "identified": ident, "hallucinated": halluc})
        mark = ("correct" if (verdict_ok and (ident or not c["buggy"]))
                else "HALLUCINATION" if halluc else "miss")
        print(f"{c['id']:<{w}}{'buggy' if c['buggy'] else 'clean':<8}"
              f"{'buggy' if flagged else 'clean':<8}{len(fs):>9}  {mark}"
              + (f"   [{err}]" if err else ""))

    bb.summarise(rows)
    args.out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    print(f"\nrows -> {args.out}")


if __name__ == "__main__":
    main()
