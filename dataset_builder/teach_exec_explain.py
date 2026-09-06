"""Have a teacher PHRASE the explanation; execution supplies the facts.

    MODEL=artifacts/base-3b ./serve.sh start
    python -m dataset_builder.teach_exec_explain --in data/exec_v2.jsonl \
        --out data/exec_explain_v2.jsonl --model-name base-3b

The teacher is never asked what the code does -- `bench/exec_diff` already ran it
and the real before/after are handed over in the prompt. Its only job is to write
them as a sentence a developer would read. That is why a 3B teacher is adequate
here and would not be if it had to compute: a wrong value cannot enter the corpus,
because `_grounded` drops any explanation that does not carry the measured values
or that invents a number the facts never mentioned.

This replaces the f-string in build_exec_explain.py. One string per family is the
recitation failure this project has hit repeatedly -- the model learns
diff-shape -> phrase and stops reading the code.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import os
import random
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

TEACHER = """You are writing the review note for one commit.

These facts were MEASURED by running the code. They are correct. Do not question
them, do not recompute them, do not add facts of your own:

  what changed              : {changed}
  the program printed BEFORE: {before}
  the program printed AFTER : {after}
  did behaviour change      : {differs}

Write ONE OR TWO sentences a developer would want to read. Name the construct
that changed and say what it does to the program's output, quoting the exact
values above. Plain prose, no JSON, no bullet points, no preamble.

Do not mention any number that does not appear in the facts or the diff.
{extra}

```diff
{diff}
```"""

SAME = ("Behaviour did NOT change: say so plainly and state that the output is "
        "still {before}.")
DIFF = ("Behaviour DID change: say what the output was and what it became.")

# The pytest-shaped corpus reports a FIX: the project's own test was failing and
# now passes, so `before` is a diagnostic rather than a printed value and `after`
# carries no information. Telling the teacher to "say what the output became"
# invites "the test now passes", which is contentless -- the developer already
# knows the outcome. What they cannot see is the failure that was repaired, so
# that is what has to be quoted, and quoted exactly: the grounding filter takes
# the signature verbatim or not at all.
FIXDIR = ("The project's own test was FAILING before this commit and PASSES "
          "after it. Quote the failure text CHARACTER FOR CHARACTER exactly as "
          "it appears above -- do not paraphrase it, shorten it, or re-word it "
          "-- and name the construct in the diff that repaired it. Do not write "
          "that the test now passes: that is the outcome you were given, and it "
          "tells the developer nothing.")

# What the deployed reviewer must say when the command printed the same thing
# both times. `core.review_commit` case 5 sends EVERY byte-identical result
# here, and its outcome string is explicit that the two possibilities cannot be
# told apart. `SAME` was written for a corpus whose values were printed scalars,
# where "the output is still 27" is informative; in the pytest corpus both sides
# are the sentinel "the test passes", so SAME degenerates to "the output is
# still the test passes" and the teacher writes "behaviour did not change"
# instead. That sentence is true of a generated pair -- both sides really were
# run -- and false of the deployed case, and it is the sentence the guard chain
# withholds on real commits.
NOTCOVERED = (
    "The command printed the SAME thing before and after, so it established "
    "NOTHING about this change: it may never have reached the changed code, or "
    "reached it and made no difference to what this command prints, and which "
    "of the two happened is not known. Do NOT write that the change is safe, "
    "harmless, cosmetic, minor, or that behaviour is unchanged -- none of that "
    "was measured. Name the construct the diff edits and say what a developer "
    "should check to settle it: callers of it, other code reading the value, or "
    "a test that would reach it. Do not quote the words 'the test passes'; that "
    "is the outcome, not a finding.")

# Sentences that assert safety. The teacher reaches for these when it has
# nothing to report, and a corpus that keeps them trains the exact claim the
# deployed guard exists to suppress.
SAFETY = re.compile(
    r"\b(no (observable |visible |functional )?(change|effect|impact)"
    r"|does not (affect|change|alter|impact)"
    r"|behaviou?r (is |remains )?(the same|unchanged)"
    r"|remains? unchanged|no behaviou?ral change"
    r"|is (safe|harmless|cosmetic)|purely cosmetic|only cosmetic)\b", re.I)

SYSTEM = ("You are ORACLE. You explain commits to developers in plain prose, "
          "using only facts you are given.")


# Groq sits behind Cloudflare, which answers POST from `Python-urllib/x.y` with
# 403 error 1010 while letting GET /models through -- so this looked like an auth
# failure across all six keys until the UA was changed.
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/125.0 Safari/537.36")
_GROQ = "https://api.groq.com/openai/v1/chat/completions"


def groq_keys() -> list[str]:
    """Every GROQ_API_KEY<n> in the environment, then in ~/.zshrc."""
    ks = [v for k, v in sorted(os.environ.items())
          if re.fullmatch(r"GROQ_API_KEY\d*", k) and v.strip()]
    if not ks:
        rc = pathlib.Path.home() / ".zshrc"
        if rc.exists():
            ks = [m.group(1) for m in
                  re.finditer(r'GROQ_API_KEY\d*=["\']?([^"\'\s]+)', rc.read_text())]
    return ks


class Keyring:
    """Round-robin over the keys, parking one that is rate-limited."""

    def __init__(self, keys: list[str]):
        self.keys, self.i, self.lock = keys, 0, threading.Lock()
        self.until: dict[str, float] = {}

    def take(self) -> str:
        with self.lock:
            for _ in range(len(self.keys)):
                k = self.keys[self.i % len(self.keys)]
                self.i += 1
                if self.until.get(k, 0) < time.time():
                    return k
            return self.keys[self.i % len(self.keys)]

    def park(self, k: str, secs: float = 20.0) -> None:
        with self.lock:
            self.until[k] = time.time() + secs


def ask_groq(ring: Keyring, model: str, prompt: str, timeout: int = 90) -> str:
    body = json.dumps({
        "model": model, "temperature": 0.9, "top_p": 0.95, "max_tokens": 700,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
    }).encode()
    last = None
    for attempt in range(5):
        k = ring.take()
        req = urllib.request.Request(_GROQ, data=body, headers={
            "Content-Type": "application/json", "User-Agent": _UA,
            "Authorization": f"Bearer {k}"})
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
            return (r["choices"][0]["message"].get("content") or "").strip()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 503):
                ring.park(k, 15 + 10 * attempt)
                time.sleep(0.5 + random.random())
                continue
            raise
        except Exception as e:
            last = e
            time.sleep(0.5 + random.random())
    raise RuntimeError(f"groq failed after retries: {last}")


def ask(host: str, model: str, prompt: str, timeout: int = 120) -> str:
    body = json.dumps({
        "model": model, "stream": False,
        "options": {"temperature": 0.8, "top_p": 0.95, "num_predict": 160},
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(f"{host}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"].strip()


def clean(text: str) -> str:
    """One or two sentences of prose, with the model's scaffolding stripped."""
    # gpt-oss emits U+202F narrow no-break space between words and numbers;
    # left in, the corpus would teach a character no human types.
    text = unicodedata.normalize("NFKC", text).replace("\u202f", " ")
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"^\s*(sure|certainly|here'?s?|explanation|note)\b[^.\n]*[:.]",
                  "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip().strip('"').strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(parts[:2]).strip()


def _nums(s: str) -> set[str]:
    return set(re.findall(r"-?\d+", s))


# A side whose value is a fixed STATUS rather than a measured value. The
# pytest-shaped corpus reports `after` as "the test passes" on every fix, so
# demanding it verbatim rejects the teacher for writing "the test now passes" --
# a phrasing difference, not a grounding failure. Measured on the v3 train
# split, that check alone dropped 412 rows and left a corpus that was 93%
# no-change: training on it would have taught the model to assert that nothing
# happened, which is the exact deployed failure v3 exists to fix.
SENTINELS = {"the test passes", "the tests pass", "(no output)"}


def grounded(expl: str, row: dict, sentinels: set[str] | None = None) -> str | None:
    """Reason the explanation is unusable, or None if it is fine."""
    sent = SENTINELS if sentinels is None else sentinels
    if len(expl) < 25:
        return "too short"
    if len(expl) > 400:
        return "too long"
    b, a = str(row["before"]).strip(), str(row["after"]).strip()
    if row["differs"]:
        if b and b.lower() not in sent and b not in expl:
            return "missing the before value"
        if a and a.lower() not in sent and a not in expl:
            return "missing the after value"
    else:
        # The row established nothing, so a sentence asserting safety is not a
        # phrasing problem -- it is the wrong claim, and the deployed guard
        # would withhold it. Dropping it here is cheaper than teaching it and
        # suppressing it later.
        if SAFETY.search(expl):
            return "claims safety on a row that established nothing"
        if b and b.lower() not in sent and b not in expl:
            return "missing the unchanged value"
    # a number that is in neither the facts nor the diff is invented
    allowed = _nums(b) | _nums(a) | _nums(row["diff"]) | {"1", "2"}
    invented = _nums(expl) - allowed
    if invented:
        return f"invented number(s) {sorted(invented)[:3]}"
    return None


def frame(s: str) -> str:
    s = re.sub(r"-?\d+", "N", s)
    s = re.sub(r"\b[a-z_][a-z0-9_]*\b", "ID", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", type=pathlib.Path, required=True)
    ap.add_argument("--out", dest="dst", type=pathlib.Path, required=True)
    ap.add_argument("--backend", choices=("groq", "ollama"), default="groq")
    ap.add_argument("--host", default="http://localhost:8111")
    ap.add_argument("--model-name", default="qwen/qwen3.8-27b")
    ap.add_argument("--workers", type=int, default=6,
                    help="parallel teacher calls (groq only)")
    ap.add_argument("--retries", type=int, default=2,
                    help="regenerate this many times when grounding fails")
    ap.add_argument("--min-distinct", type=float, default=0.55, metavar="F",
                    help="fail if distinct explanation FRAMES fall below this")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.src)]
    if args.limit:
        rows = rows[:args.limit]

    ring = None
    if args.backend == "groq":
        ks = groq_keys()
        if not ks:
            sys.exit("no GROQ_API_KEY<n> in the environment or ~/.zshrc")
        ring = Keyring(ks)
        print(f"groq: {len(ks)} key(s), model {args.model_name}, "
              f"{args.workers} workers")

    why, lock, done = Counter(), threading.Lock(), [0]

    def one(row):
        prompt = TEACHER.format(
            changed=row["changed"], before=row["before"], after=row["after"],
            differs="yes" if row["differs"] else "no", diff=row["diff"],
            extra=(
                # A fix -- `after` is a status, not a value -- needs different
                # instructions from a value-to-value change. See FIXDIR.
                (FIXDIR if str(row["after"]).strip().lower() in SENTINELS
                 else DIFF) if row["differs"]
                # Both identical-output kinds -- ran-and-identical and
                # never-reached -- get NOTCOVERED. They are one outcome to the
                # deployed reviewer and must be one lesson here. SAME survives
                # only for the older printed-scalar corpora, where the
                # unchanged value is a real thing to quote.
                else NOTCOVERED
                if str(row["before"]).strip().lower() in SENTINELS
                else SAME.format(before=row["before"])))
        keep = None
        for _ in range(args.retries + 1):
            try:
                raw = (ask_groq(ring, args.model_name, prompt) if ring
                       else ask(args.host, args.model_name, prompt))
                expl = clean(raw)
            except Exception as e:
                with lock:
                    why[f"http:{type(e).__name__}"] += 1
                continue
            bad = grounded(expl, row)
            if bad is None:
                keep = expl
                break
            with lock:
                why[bad] += 1
        with lock:
            done[0] += 1
            if not keep:
                why["DROPPED"] += 1
            if done[0] % 100 == 0:
                print(f"  {done[0]}/{len(rows)}", flush=True)
        return {**row, "explanation": keep} if keep else None

    if ring and args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            out = [r for r in ex.map(one, rows) if r]
    else:
        out = [r for r in map(one, rows) if r]

    frames = Counter(frame(o["explanation"]) for o in out)
    distinct = len(frames) / max(1, len(out))
    print(f"\n{len(out)}/{len(rows)} kept ({len(out) / max(1,len(rows)):.0%})")
    print(f"  distinct explanation frames: {len(frames)}/{len(out)} = {distinct:.2f}")
    print(f"  most common frame x{frames.most_common(1)[0][1] if frames else 0}")
    for k, v in why.most_common(8):
        print(f"    {k}: {v}")
    if distinct < args.min_distinct:
        sys.exit(f"FAILED: {distinct:.2f} distinct frames < {args.min_distinct} "
                 f"-- the teacher is reciting, which is what this replaces")
    with open(args.dst, "w") as fh:
        for o in out:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    print(f"-> {args.dst} ({len(out)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
