"""Label fetched commits with a teacher model, then verify what it said.

The teacher sets the student's ceiling, so this is the one step worth paying
for. It is also the one step you should not have to repeat: every raw response
is written to disk, so a schema change means re-parsing, not re-paying.

    export DEEPSEEK_API_KEY=sk-...
    python -m corpus.label --provider deepseek --limit 2000

    python -m corpus.label --provider ollama --model qwen3-coder:latest   # local

Verification matters as much as the teacher. Three filters run on every label:

  grounded      every finding must name a category and a real explanation
  agreement     teacher silent on a buggy=True commit (or vocal on a clean one)
                is quarantined, not trained on
  consistent    with --samples 3, only findings that appear in a majority of
                samples survive

Expect to discard 30-40%. Verified examples are worth several unverified ones.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import MAX_DIFF_CHARS, ROOT
from dataset_builder.schema import SYSTEM_PROMPT, Analysis, build_user_message
from llm_explainer.client import extract_json

IN_PATH = ROOT / "data" / "apachejit_commits.jsonl"
OUT_PATH = ROOT / "data" / "labelled.jsonl"
RAW_PATH = ROOT / "data" / "labelled_raw.jsonl"


@dataclass
class Provider:
    name: str
    base_url: str
    model: str
    key_env: str

    @property
    def keys(self) -> list[str]:
        # Comma-separated env names = fallback keys. A free-tier Groq account
        # caps tokens per day (200k TPD per org, measured 18 Aug 2026), so six
        # accounts multiplying the daily budget is cheaper than waiting one out.
        envs = [e.strip() for e in self.key_env.split(",")]
        # dict.fromkeys dedupes by value and keeps order: the unnumbered and
        # the numbered name for key 1 both appear below, and whichever pair of
        # shell and env file is in play, one of them is the same key twice.
        keys = list(dict.fromkeys(
            v for e in envs if (v := os.getenv(e, "").strip())))
        if not keys:
            raise SystemExit(
                f"none of {envs} is set.\n"
                f"  export GROQ_API_KEY1=... (through GROQ_API_KEY6)"
            )
        return keys


PROVIDERS = {
    # All OpenAI-compatible /chat/completions, so one code path serves them all.
    # Model ids come from the live account, not from documentation: this API
    # serves deepseek-v4-pro / deepseek-v4-flash. Check /v1/models if a call
    # 404s on the model name.
    "deepseek": Provider("deepseek", "https://api.deepseek.com/v1",
                         "deepseek-v4-pro", "DEEPSEEK_API_KEY"),
    "openai": Provider("openai", "https://api.openai.com/v1",
                       "gpt-4o-mini", "OPENAI_API_KEY"),
    # Free tier, very fast, OpenAI-compatible. Rate limits are per-minute rather
    # than per-request, and per-day on top of that, so ask() paces on the
    # rate-limit headers and rotates keys rather than sleeping a limit out.
    "groq": Provider("groq", "https://api.groq.com/openai/v1",
                     "openai/gpt-oss-120b",
                     "GROQ_API_KEY,GROQ_API_KEY1,GROQ_API_KEY2,"
                     "GROQ_API_KEY3,GROQ_API_KEY4,GROQ_API_KEY5,"
                     "GROQ_API_KEY6"),
    "together": Provider("together", "https://api.together.xyz/v1",
                         "Qwen/Qwen2.5-Coder-32B-Instruct", "TOGETHER_API_KEY"),
    "ollama": Provider("ollama", "http://192.168.1.170:11434/v1",
                       "qwen3-coder:latest", ""),
}


# Groq rations tokens per minute and reports the bucket on every response, so
# the wait before the next call is arithmetic, not guesswork. The previous
# blind ladder (10s, 20s, 30s...) slept ~5 minutes per commit against a budget
# that allows ~4 per minute; pacing on the header measured 16x faster.
_RATE: dict[str, dict] = {}          # api key -> last seen token bucket
_BLOCKED: dict[str, float] = {}      # api key -> unix time it is usable again
_COST = [2000.0]                     # largest total_tokens a commit has cost


def _duration(v: str | None) -> float | None:
    """Seconds from '3', '9.202s' or '1m26.4s'. None if unparseable."""
    if not v:
        return None
    m = re.fullmatch(r"(?:(\d+(?:\.\d+)?)m)?(\d+(?:\.\d+)?)s?", v.strip())
    return None if not m else float(m.group(1) or 0) * 60 + float(m.group(2))


def _observe(key: str, resp, used: float | None = None) -> None:
    """Record the token bucket a response reported for this key."""
    try:
        bucket = {"limit": float(resp.headers["x-ratelimit-limit-tokens"]),
                  "remaining": float(resp.headers["x-ratelimit-remaining-tokens"]),
                  "at": time.time()}
    except (KeyError, ValueError):
        return
    _RATE[key] = bucket
    if used:
        # Bias to the largest commit seen: under-estimating the cost buys a
        # 429, over-estimating only costs a few idle seconds.
        _COST[0] = max(_COST[0], used)


def _pace(key: str) -> None:
    """Sleep exactly long enough for this key's next call to fit the bucket."""
    b = _RATE.get(key)
    if not b:
        return
    refill = b["limit"] / 60.0                        # tokens per second
    have = min(b["remaining"] + (time.time() - b["at"]) * refill, b["limit"])
    short = min(_COST[0], b["limit"]) - have
    if short > 0:
        time.sleep(short / refill)


def _pick_key(keys: list[str]) -> str:
    """The first key not rate-limited right now.

    Groq's free tier caps tokens per *day* as well as per minute (200k TPD per
    organisation, measured 2026-08-18), and it answers an exhausted key with a
    `retry-after` of several hundred seconds. Sleeping that out is the whole
    reason a pass averaged five minutes a commit: attempt 0 always reached for
    the same spent key. Rotating past it costs nothing.
    """
    now = time.time()
    for k in keys:
        if _BLOCKED.get(k, 0.0) <= now:
            return k
    soonest = min(keys, key=lambda k: _BLOCKED[k])
    wait = _BLOCKED[soonest] - now
    print(f"  all {len(keys)} keys rate-limited, waiting {wait:.0f}s",
          file=sys.stderr, flush=True)
    time.sleep(max(wait, 1.0))
    return soonest


def ask(provider: Provider, model: str, system: str, user: str,
        temperature: float, timeout: int, retries: int = 12) -> str:
    """One chat completion. Returns raw content; parsing happens later.

    12 retries, not 3. A free tier rations tokens per minute *and* per day, so a
    429 is the normal case and not an error, and an attempt spent rotating past
    a key that is out of daily budget is not an attempt spent on this request.
    Three retries turned a queue into a failure and lost the commit permanently.
    """
    keys = provider.keys
    headers = {"Content-Type": "application/json"}

    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    for attempt in range(retries):
        # A 429 says "this account is out of budget", and another account may
        # not be - so rotate to a live key rather than waiting this one out.
        key = _pick_key(keys)
        headers["Authorization"] = f"Bearer {key}"
        _pace(key)
        try:
            resp = requests.post(f"{provider.base_url}/chat/completions",
                                 headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise RuntimeError(f"{provider.name}: {e}") from e
            print(f"  retry {attempt}: {type(e).__name__}", file=sys.stderr,
                  flush=True)
            time.sleep(min(2 ** attempt, 30))
            continue

        _observe(key, resp)
        if resp.status_code == 429:
            wait = _duration(resp.headers.get("retry-after")) or 5.0
            if wait > 60:
                # Minutes of penalty means the per-day budget, not the
                # per-minute one. Park the key and reach for the next.
                _BLOCKED[key] = time.time() + wait
                print(f"  key ...{key[-4:]} spent for {wait / 60:.0f}m: "
                      f"{resp.text[:120]}", file=sys.stderr, flush=True)
                continue
            time.sleep(wait)
            continue
        if not resp.ok:
            if attempt == retries - 1:
                raise RuntimeError(f"{provider.name} {resp.status_code}: "
                                   f"{resp.text[:200]}")
            print(f"  retry {attempt}: {resp.status_code} {resp.text[:80]}",
                  file=sys.stderr, flush=True)
            time.sleep(min(2 ** attempt, 30))
            continue
        body = resp.json()
        _observe(key, resp, (body.get("usage") or {}).get("total_tokens"))
        content = body["choices"][0]["message"]["content"]
        if not content or not content.strip():
            # A 200 with an empty body is a transient server hiccup, not an
            # answer. Counting it as a failure loses the commit permanently.
            print(f"  retry {attempt}: empty body", file=sys.stderr, flush=True)
            time.sleep(min(2 ** attempt, 30))
            continue
        return content
    raise RuntimeError(f"{provider.name}: exhausted retries")


def majority_findings(analyses: list[Analysis], votes_needed: int) -> Analysis:
    """Keep findings a majority of samples agree on.

    A defect the teacher names once out of three is usually a hallucination; one
    it names every time usually is not.
    """
    if len(analyses) == 1:
        return analyses[0]

    counts = Counter(f.category for a in analyses for f in a.findings)
    keep = {c for c, n in counts.items() if n >= votes_needed}
    merged, seen = [], set()
    for a in analyses:
        for f in a.findings:
            if f.category in keep and f.category not in seen:
                seen.add(f.category)
                merged.append(f)
    # Take the summary from a sample whose verdict matches the merged one.
    summary = next((a.summary for a in analyses
                    if bool(a.findings) == bool(merged)), analyses[0].summary)
    return Analysis(summary=summary, findings=merged)


def verify(analysis: Analysis, buggy: bool, hinted: bool = True) -> tuple[bool, str]:
    """Should this label be trained on? Returns (keep, reason).

    `hinted` says whether the teacher was told a defect exists. It changes what
    silence means, and therefore what may be filtered.

    When the teacher was hinted, silence on a buggy commit contradicts an
    instruction it was given, so it is a malfunction and is quarantined.

    When it was not, silence is the teacher's actual verdict: it read the diff
    and saw nothing. Dropping those is what made the corpus report a recall of
    1.00 with zero misses across 844 commits - not because the teacher never
    missed a defect, but because a miss could not survive to be counted. The
    filter manufactured its own ceiling. Unhinted, the disagreement is the most
    informative record in the set and is kept.
    """
    for f in analysis.findings:
        if len(f.explanation.strip()) < 30:
            return False, "explanation too thin to learn from"
    if not analysis.summary.strip():
        return False, "no summary"

    if hinted and buggy and not analysis.findings:
        return False, "SZZ says buggy, teacher found nothing"
    # Kept in both modes: a teacher naming three defects on a commit no later
    # fix touched is over-reporting, and training on it teaches exactly that.
    if not buggy and len(analysis.findings) > 2:
        return False, "SZZ says clean, teacher found several defects"
    return True, "ok"



def cap_per_language(pool, per_language, already):
    """Take up to per_language records of each language, counting what is
    already labelled towards the quota.

    Seeding the counter with `already` is the whole point: a restart re-samples
    from the unlabelled remainder, so a fresh counter grows the corpus by
    per_language * languages on every relaunch.
    """
    seen: Counter = Counter(already)
    capped = []
    for r in pool:
        lang = r.get("language", "")
        if seen[lang] >= per_language:
            continue
        seen[lang] += 1
        capped.append(r)
    return capped, seen


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", type=Path, default=IN_PATH)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--raw", type=Path, default=RAW_PATH)
    ap.add_argument("--provider", choices=sorted(PROVIDERS), default="deepseek")
    ap.add_argument("--model", help="override the provider's default model")
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--samples", type=int, default=1,
                    help="responses per commit; >1 enables majority voting")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="extra seconds between requests, on top of the "
                         "rate-limit pacing ask() already does")
    ap.add_argument("--workers", type=int, default=8,
                    help="parallel requests; labelling is IO-bound, and a "
                         "reasoning teacher spends minutes per commit")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--hint", action="store_true",
                    help="tell the teacher a defect exists on SZZ-buggy "
                         "commits. Leaks the label into the training target — "
                         "see label_one(). Off by default.")
    ap.add_argument("--per-language", type=int, default=0,
                    help="cap how many commits of each language enter the "
                         "sample, so one large repository cannot decide the "
                         "corpus. 0 disables the cap.")
    ap.add_argument("--no-balance", dest="balance", action="store_false",
                    help="take records in file order instead of balancing "
                         "buggy/clean")
    ap.set_defaults(balance=True)
    args = ap.parse_args(argv)

    if not args.inp.exists():
        raise SystemExit(f"{args.inp} not found — fetch commits first:\n"
                         f"  python -m corpus.fetch --limit 2500")

    provider = PROVIDERS[args.provider]
    model = args.model or provider.model
    provider.keys  # fail now, not after 500 requests

    records = [json.loads(l) for l in open(args.inp) if l.strip()]
    done = set()
    done_langs: Counter = Counter()
    if args.out.exists():
        for line in open(args.out):
            if line.strip():
                rec = json.loads(line)
                done.add(rec["commit_id"])
                done_langs[rec.get("language", "")] += 1
        print(f"{len(done)} already labelled, skipping those")

    # Balanced by the SZZ label. Taking the first N gave 3 buggy to 17 clean,
    # and a corpus that lopsided teaches the model that "no defects found" is
    # right 85% of the time - which it then says to everything.
    pool = [r for r in records if r["commit_id"] not in done]

    # Mining is free and labelling costs days, so corpus composition is decided
    # here rather than in the miner. Without a cap the guard corpus arrives as
    # 228 php and 15 rust, because a repository's yield tracks its size and its
    # commit-message habits, not the language's share of the goal.
    if args.per_language:
        import random as _random

        _random.Random(args.seed).shuffle(pool)
        capped, seen = cap_per_language(pool, args.per_language, done_langs)
        print(f"capped at {args.per_language}/language: {len(pool)} -> "
              f"{len(capped)}  {dict(seen.most_common())}")
        pool = capped

    if args.balance:
        import random as _random

        rng = _random.Random(args.seed)
        buggy = [r for r in pool if r.get("buggy")]
        clean = [r for r in pool if not r.get("buggy")]
        rng.shuffle(buggy)
        rng.shuffle(clean)
        half = args.limit // 2
        todo = buggy[:half] + clean[: args.limit - min(half, len(buggy))]
        rng.shuffle(todo)
        print(f"sampling {sum(1 for r in todo if r.get('buggy'))} buggy / "
              f"{sum(1 for r in todo if not r.get('buggy'))} clean")
    else:
        todo = pool[: args.limit]
    votes = max(1, args.samples // 2 + 1) if args.samples > 1 else 1
    print(f"{len(todo)} commits to label with {provider.name}/{model}"
          + (f", {args.samples} samples each (need {votes} votes)"
             if args.samples > 1 else ""))

    kept = dropped = failed = 0
    seen: list[tuple[bool, bool]] = []   # (teacher found a defect, SZZ label)
    started = time.time()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    def label_one(rec: dict):
        """One commit -> (record, analyses, raw texts). Runs in a worker."""
        user = build_user_message(
            rec["diff"], rec.get("subject", ""),
            ", ".join(rec.get("files", [])),
            max_diff_chars=MAX_DIFF_CHARS, include_schema=True)
        # Off by default. The hint tells the teacher the answer on exactly the
        # half of the corpus where the answer is the thing being learnt, and the
        # student never sees it at inference - so it trains the model to assert
        # what it cannot infer. Measured cost: teacher recall 1.00 / fn 0 on 844
        # commits, and a student that scored F1 0.56 against a free baseline of
        # 0.63. Use --hint only to write explanations for defects whose presence
        # was established by an unhinted pass.
        if args.hint and rec.get("buggy"):
            hint = ("\n\nGround truth: a later commit in this repository "
                    "fixed a defect in the lines this change introduced. "
                    "Identify what is wrong here and report it. If the "
                    "defect genuinely is not visible in this diff, say so "
                    "and return no findings rather than inventing one.")
            if rec.get("fix_subject"):
                hint += f"\nThe fix was described as: {rec['fix_subject']!r}"
            user += hint

        analyses, raws = [], []
        for s in range(args.samples):
            content = ask(provider, model, SYSTEM_PROMPT, user,
                          args.temperature if s == 0 else 0.7, args.timeout)
            raws.append(content)
            analyses.append(Analysis.model_validate(extract_json(content)))
            if args.sleep:
                time.sleep(args.sleep)
        return rec, analyses, raws

    with open(args.out, "a") as out, open(args.raw, "a") as raw:
        with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(label_one, rec): rec for rec in todo}
            for i, fut in enumerate(cf.as_completed(futures), 1):
                rec = futures[fut]
                try:
                    rec, analyses, raws = fut.result()
                except Exception as e:
                    failed += 1
                    print(f"  [{i}] {rec['commit_id'][:8]} failed: "
                          f"{type(e).__name__}: {str(e)[:90]}", flush=True)
                    continue
                for s, content in enumerate(raws):
                    raw.write(json.dumps({"commit_id": rec["commit_id"],
                                          "sample": s, "raw": content}) + "\n")
                raw.flush()

                analysis = majority_findings(analyses, votes)
                keep, reason = verify(analysis, bool(rec.get("buggy")),
                                      hinted=args.hint)
                if not keep:
                    dropped += 1
                else:
                    kept += 1
                    out.write(json.dumps({
                        "commit_id": rec["commit_id"],
                        "project": rec.get("project", ""),
                        "language": rec.get("language", ""),
                        "buggy": rec.get("buggy"),
                        "subject": rec.get("subject", ""),
                        "files": rec.get("files", []),
                        "diff": rec["diff"],
                        "analysis": analysis.model_dump(),
                        "teacher": f"{provider.name}/{model}",
                        # Stamped per record: a corpus labelled with the hint and
                        # one labelled without are not the same dataset, and
                        # nothing else on the record tells them apart.
                        "hinted": bool(args.hint),
                    }) + "\n")
                    out.flush()
                    seen.append((bool(analysis.findings), bool(rec.get("buggy"))))

                if i % 10 == 0 or i == 1:
                    rate = i / max(time.time() - started, 1e-9)
                    eta = (len(todo) - i) / max(rate, 1e-9) / 60
                    print(f"  {i}/{len(todo)}  kept {kept}  dropped {dropped}  "
                          f"failed {failed}  ({rate:.2f}/s, ETA {eta:.0f}m)",
                          flush=True)

    total = kept + dropped
    print(f"\n{kept} verified labels -> {args.out}")
    print(f"{dropped} dropped by verification"
          + (f" ({100 * dropped // total}%)" if total else "")
          + f", {failed} failed outright")
    print(f"raw responses kept in {args.raw} — re-parse instead of re-paying")

    # The teacher's own agreement with SZZ, on the kept records. This is the
    # student's ceiling, so it is worth seeing the moment it is knowable rather
    # than a training run later. Unhinted it is a measurement; hinted it is the
    # teacher repeating what it was told, and `fn` gives that away by sitting
    # at zero.
    if seen:
        from evaluate import confusion

        c = confusion(seen)
        print(f"\nteacher vs SZZ ({'hinted' if args.hint else 'unhinted'}): "
              f"P={c['precision']:.2f} R={c['recall']:.2f} F1={c['f1']:.2f} "
              f"acc={c['accuracy']:.2f}")
        print(f"  tp={c['tp']} fp={c['fp']} fn={c['fn']} tn={c['tn']}")
        base = sum(a for _, a in seen) / len(seen)
        print(f"  always-buggy would score F1={2 * base / (1 + base):.2f} "
              f"acc={base:.2f} — beat that or the label carries no signal")
        if not args.hint and c["fn"] == 0:
            print("  fn=0 unhinted is suspicious — check the filter, not the teacher")
    if kept:
        print(f"next:\n  python main.py build-sft --jsonl {args.out}")
    return 0


if __name__ == "__main__":
    from dataset_builder.schema import Finding

    # Majority voting must drop the one-off and keep the repeated.
    a = [Analysis(summary="s", findings=[Finding(category="off-by-one",
                                                 explanation="x" * 40)]),
         Analysis(summary="s", findings=[Finding(category="off-by-one",
                                                 explanation="x" * 40),
                                         Finding(category="security",
                                                 explanation="y" * 40)]),
         Analysis(summary="s", findings=[Finding(category="off-by-one",
                                                 explanation="x" * 40)])]
    merged = majority_findings(a, votes_needed=2)
    assert [f.category for f in merged.findings] == ["off-by-one"], merged

    assert verify(Analysis(summary="s"), buggy=False)[0]
    assert not verify(Analysis(summary="s"), buggy=True)[0], \
        "hinted: silent on a buggy commit contradicts the instruction given"
    # Unhinted, that same silence is the teacher's verdict and must survive, or
    # the corpus can never contain a false negative and its recall is a fiction.
    assert verify(Analysis(summary="s"), buggy=True, hinted=False)[0], \
        "unhinted disagreement is data, not noise"
    assert not verify(Analysis(summary="s", findings=[
        Finding(category="other", explanation="short")]), buggy=True)[0]
    # Over-reporting on a clean commit is filtered either way.
    three = [Finding(category="other", explanation="x" * 40) for _ in range(3)]
    assert not verify(Analysis(summary="s", findings=three), buggy=False,
                      hinted=False)[0]
    # The per-language cap must count what is already labelled, or a restart
    # samples a fresh quota and the corpus overshoots by 480 every relaunch.
    pool = [{"language": "go"}] * 5 + [{"language": "rust"}] * 5
    capped, _ = cap_per_language(pool, 3, Counter())
    assert len(capped) == 6, capped
    capped, _ = cap_per_language(pool, 3, Counter({"go": 3, "rust": 1}))
    assert [r["language"] for r in capped] == ["rust", "rust"], capped
    assert cap_per_language(pool, 3, Counter({"go": 9, "rust": 9}))[0] == []

    # Rate-limit pacing: the header parser and the refill arithmetic.
    assert _duration("3") == 3.0
    assert _duration("9.202s") == 9.202
    assert abs(_duration("1m26.4s") - 86.4) < 1e-9
    assert _duration("") is None and _duration("soon") is None
    _RATE["k1"] = {"limit": 8000.0, "remaining": 8000.0, "at": time.time()}
    t = time.time(); _pace("k1")
    assert time.time() - t < 0.1, "a full bucket must not sleep"
    t = time.time(); _pace("never-seen")
    assert time.time() - t < 0.1, "an unseen key must not sleep"
    # 214 tokens left, 2000 needed, refilling at 8000/60 = 133/s -> ~13.4s.
    _RATE["k1"] = {"limit": 8000.0, "remaining": 214.0, "at": time.time()}
    t = time.time(); _pace("k1")
    assert 12.0 < time.time() - t < 15.0, "pace should wait for the shortfall"
    # A key parked for the day must be skipped, not waited out.
    _BLOCKED["k1"] = time.time() + 700
    t = time.time()
    assert _pick_key(["k1", "k2"]) == "k2", "must rotate past a spent key"
    assert time.time() - t < 0.1, "rotating must not sleep"
    # Everything parked: wait for the one that frees up first, not for keys[0].
    _BLOCKED["k2"] = time.time() + 1
    assert _pick_key(["k1", "k2"]) == "k2", "must wait out the soonest key"
    _BLOCKED.clear()
    print("voting + verification + pacing ok")
    raise SystemExit(main())
