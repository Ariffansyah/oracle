# Results

Every measurement taken, with the command that reproduces it. Numbers only —
interpretation lives in `ROADMAP.md`, corpus provenance in `DATASETS.md`.

Status as of 2026-08-18.

---

## 0. Trivial baselines

No detection number in this project means anything without the matching trivial
baseline beside it. Two are in play.

| baseline | where it applies | value |
|---|---|---|
| always-buggy | F1 at a 50/50 base rate | **F1 0.665** |
| always-clean | accuracy at a 50/50 base rate | **acc 0.500** |
| counting (10 features on `+`/`-` lines) | any diff-direction task | see §4 |

Separation (TPR − FPR) is the measure that survives all three: it is zero for
any constant answer and independent of base rate.

```
python count_control.py data/cve_gate.jsonl 0.6667      # paired corpus
python count_control.py data/apachejit_commits.jsonl 0.8 # ApacheJIT
```

---

## 1. ApacheJIT detection — `data/detect_eval.jsonl`

1000 commits, balanced 500/500, SZZ labels only, no teacher involved. Sampled
from the 6030 commits the teacher never touched.

```
python evaluate.py --paired data/detect_sft220.jsonl data/detect_stock.jsonl
```

| metric | checkpoint-220 | stock 3B | trivial |
|---|---|---|---|
| valid JSON | 99.8% | 99.9% | — |
| precision | 0.59 | 0.55 | 0.50 |
| recall | 0.71 | 0.63 | 1.00 |
| F1 | 0.64 | 0.59 | **0.665** |
| accuracy | 0.61 | 0.56 | 0.500 |
| **separation (TPR−FPR)** | **+21.0pp** | +11.6pp | 0.0pp |
| grounded | 99.8% | 98.4% | — |
| category match vs teacher | 27.1% | 26.9% | — |
| median latency | 21.7s | 19.8s | — |
| confusion | tp=355 fp=251 fn=143 tn=249 | tp=314 fp=256 fn=185 tn=244 | — |

**Paired bootstrap, n=997, 10000 resamples:**

```
separation diff   +9.5pp   95% CI [+2.0, +17.0]   p=0.007
McNemar           220-only-correct 209, stock-only-correct 162, p=0.017
```

Acceptance criterion 3 (beats the base model significantly) **passes**.
Criterion 2 fails on F1 (0.64 < 0.665), passes on accuracy (0.61 > 0.500).

Both checkpoints were trained on the leaked corpus, so this is the pre-fix
baseline, not a publishable result.

---

## 2. CVEfixes paired detection — `data/cvefixes_eval.jsonl`

500 fix commits, each emitted forward (clean) and reversed (buggy). Human-written
CVE descriptions, no teacher. **See §4 — this corpus cannot carry a detection
claim.**

```
python evaluate.py --paired data/cve_sft220.jsonl data/cve_stock.jsonl
python evaluate.py --paired data/cve_trained.jsonl data/cve_stock.jsonl
```

| metric | checkpoint-220 | stock 3B | sft-cve (CVE-trained) |
|---|---|---|---|
| valid JSON | 98.6% | 99.6% | 100% |
| precision / recall | 0.49 / 0.70 | 0.49 / 0.76 | — / 0.00 |
| F1 | 0.57 | 0.60 | 0.00 |
| accuracy | 0.48 | 0.49 | 0.500 |
| **separation** | **−4.2pp** | **−1.8pp** | **0.0pp** |
| positive rate | 0.72 | 0.77 | 0.00 |
| grounded | 99.1% | 80.7% | — |
| category match vs CVE | 12.9% | 32.1% | — |
| median latency | 19.9s | 17.5s | 9.9s |
| confusion | tp=345 fp=363 fn=150 tn=128 | tp=378 fp=387 fn=120 tn=111 | tp=0 fp=0 fn=500 tn=500 |

**Paired bootstrap (resampled on `pair`):**

```
220 vs stock        −2.6pp   95% CI [−9.1, +4.0]   p=0.78   n=982, 497 blocks
sft-cve vs stock    +1.8pp   95% CI [−2.3, +5.8]   p=0.20   n=996, 499 blocks
```

The `sft-cve` figure is an artifact: stock's separation is negative, so scoring
exactly zero beats it arithmetically.

### 2.1 Within-pair behaviour

The same commit, forward and reversed. This is the measurement the paired
construction exists for.

| | checkpoint-220 | stock 3B |
|---|---|---|
| complete pairs | 488 | 497 |
| flags both directions | 269 (55%) | 328 (66%) |
| flags neither | 57 (12%) | 61 (12%) |
| correct (flags intro, clears fix) | 70 | 50 |
| backwards | 92 | 58 |
| forced-choice accuracy | 0.432 (sign test p=0.099) | 0.463 (p=0.501) |

Neither model reads direction. Both fire on "this diff looks risky."

### 2.2 Per-language separation (checkpoint-220)

| language | n | TPR | FPR | separation |
|---|---|---|---|---|
| PHP | 124 | 0.76 | 0.76 | +0.0pp |
| C | 109 | 0.72 | 0.76 | −3.7pp |
| C++ | 62 | 0.68 | 0.66 | +1.6pp |
| JavaScript | 42 | 0.67 | 0.74 | −7.1pp |
| Python | 30 | 0.60 | 0.66 | −5.5pp |
| Ruby | 29 | 0.69 | 0.71 | −2.5pp |
| Java | 19 | 0.84 | 0.74 | +10.5pp |
| TypeScript | 18 | 0.67 | 0.83 | −16.7pp |

Java's +10.5pp is n=19. Noise.

### 2.3 The `sft-cve` collapse

Trained on 1000 CVEfixes pairs, the model emits **one distinct output** across
all 1000 records:

```
1000×  "This change removes a vulnerable code path. No defect is introduced."
```

Cause: half the SFT targets were that identical string, and `assistant_only_loss`
puts the whole loss on the target text, so memorising it drove loss near zero on
50% of examples. Training loss 0.925 and token accuracy 0.862 looked healthy for
exactly that reason.

**Check before any future training run:** count distinct assistant turns in the
SFT file. Ten hours of GPU went into a null result that was visible in the data.

### 2.4 Explanation quality against the human CVE text

Acceptance criterion 4, measured on human ground truth — the CVE description
beside each finding. Word overlap is content-word F1 between the finding's
explanation and the CVE summary; identifier Jaccard is the shared-mechanism
measure (both name the same function/symbol or not). Inference already paid.

```
python cve_quality.py data/cve_sft220.jsonl data/cve_stock.jsonl
```

| measure | checkpoint-220 | stock 3B |
|---|---|---|
| word overlap F1 | 0.033 (median 0.000) | 0.028 (median 0.000) |
| nonzero word overlap | 37.1% | 23.6% |
| identifier Jaccard | 0.009 (5.4% nonzero) | 0.004 (2.2% nonzero) |

**Paired bootstrap (567 commits, 10000 resamples):**

```
word overlap      +0.005   95% CI [+0.000, +0.009]   p=0.017
identifier Jacc   +0.004   95% CI [+0.001, +0.008]   p=0.011
```

Fine-tuning moves the model toward the human text, and the CI just excludes
zero — but the absolute levels are the result: explanations share almost no
vocabulary with the CVE. Read alongside §2's category match (12.9% vs 32.1%):
the models describe the same defect at the diff level (names the changed
symbols, e.g. `blk_mq_tag_to_rq`, `calendar displayname`) while the human text
states the mechanism (use-after-free, XSS). The gap is a level mismatch, and
the paper should say so — it is the honest ceiling of the "reviewable
findings" claim, not a fixable token problem.

---

## 3. Stage 1 — the gate

GraphCodeBERT embeddings (768) + 14 Kamei process metrics → LightGBM.
Threshold tuned to 95% recall; "saved" is the share of commits that never reach
the LLM.

```
python -m ml_model.train_gate --jsonl data/apachejit_commits.jsonl --ablate
```

**ApacheJIT, 7989 commits, 27.5% buggy, chronological 80/20, test n=1598:**

| variant | AUC | PR-AUC | threshold | recall | LLM calls | saved |
|---|---|---|---|---|---|---|
| counting baseline | 0.638 | 0.363 | — | — | — | — |
| metrics only (2013 baseline) | 0.777 | 0.660 | 0.093 | 95.1% | 79.6% | 20.4% |
| embeddings only | 0.761 | 0.498 | 0.067 | 95.1% | 72.9% | 27.1% |
| **embeddings + metrics** | **0.822** | **0.699** | 0.037 | 95.1% | 71.8% | 28.2% |
| fine-tuned encoder + metrics | 0.828 | 0.709 | 0.017 | 95.0% | 70.4% | 29.6% |
| frozen emb+metrics, head re-swept | 0.829 | 0.702 | — | 95% | 69.9% | 30.1% |

Reading the code adds **+0.045 AUC / +0.039 PR-AUC** over process metrics alone,
and the stack clears the counting baseline by **+0.184**. AUC 0.822 is inside the
range DeepJIT and CC2Vec report on QT/OPENSTACK.

**Fine-tuning the encoder (4 epochs, 6391 train commits, 512 tokens, ~14h on
the 1660 SUPER) buys +0.006 AUC — inside noise.** Epoch 3 is the best checkpoint
(0.8283 / 0.7088); a head re-sweep on frozen embeddings scores the same
(0.8293 / 0.702, `python -m ml_model.sweep_gate`). The frozen gate stays Stage
1; the encoder run settles the question the paper needed asked. Full table:

```
epoch 1  loss=0.833  AUC=0.8162  PR-AUC=0.6874  saved=26.6%
epoch 2  loss=0.742  AUC=0.8179  PR-AUC=0.6977  saved=26.8%
epoch 3  loss=0.664  AUC=0.8283  PR-AUC=0.7088  saved=29.6%
epoch 4  loss=0.547  AUC=0.8266  PR-AUC=0.7065  saved=30.4%
```

The head sweep also tested unixcoder-base (0.824) and codebert-base (0.822)
against graphcodebert (0.829) — graphcodebert stays the encoder.

**CVEfixes paired, 3000 records, 50% buggy, repo-disjoint split, test n=1000:**

| variant | AUC | PR-AUC | recall | saved |
|---|---|---|---|---|
| counting baseline | **0.934** | 0.935 | — | — |
| gate (embeddings only — corpus has no process metrics) | 0.792 | 0.792 | 95.0% | 19.2% |

The gate scores *below* the counting baseline here, so it is recovering a noisy
version of `wc`. See §4.

An earlier run reported 0.832 on a stale 1164-commit copy of the corpus; the
7989 figure above supersedes it.

---

## 4. The paired-corpus confound

Equal total length is not equal composition. A fix adds a guard, so it carries
more `+` lines than `-` lines; its reverse carries the mirror image.

```
mean(plus-minus lines):   reversed −9.71    fix +9.72
```

| features | AUC | PR-AUC |
|---|---|---|
| counting only (all 10) | **0.934** | 0.935 |
| plus-minus lines alone | 0.908 | 0.879 |
| plus-minus chars alone | 0.925 | 0.910 |

For contrast, the same control on ApacheJIT, where the labels are real SZZ and
nothing is reversed:

| features | AUC | PR-AUC |
|---|---|---|
| counting only (all 10) | 0.638 | 0.363 |
| plus-minus lines alone | 0.634 | 0.344 |
| plus-minus chars alone | 0.629 | 0.339 |

`wc` solves the paired corpus and does not solve ApacheJIT. Consequences:

- **`cvefixes_eval.jsonl` cannot carry a detection claim.** It remains valid as
  an explanation benchmark with human ground truth.
- The gate's 0.792 there is an artifact.
- Both LLMs sat at chance on a task a line-counter solves at 0.934 — they did not
  even find the cue. This sharpens the negative result about the LLMs and weakens
  any claim that the task measures defect understanding.

The construction closed a smaller leak (git prints `-` before `+`; a naive sign
flip inverts that, and both directions are re-sorted) while missing this one.

---

## 5. Teacher ceiling — why ApacheJIT distillation was abandoned

Same 200 held-out commits, hinted versus unhinted.

| teacher | P | R | F1 | acc | fn |
|---|---|---|---|---|---|
| hinted, deepseek-v4-flash | 0.77 | **1.00** | 0.87 | 0.86 | **0** |
| unhinted, gpt-oss-120b (120B) | 0.56 | 0.43 | **0.49** | 0.58 | 52 |
| always-buggy | 0.46 | 1.00 | 0.63 | 0.46 | 0 |

A 120B model reading diffs unaided scores below the majority-class baseline.
SZZ-buggy is largely not inferable from the diff alone.

---

## 6. Training runs

| run | data | examples | steps | epochs | wall | loss | token acc |
|---|---|---|---|---|---|---|---|
| `sft-adapter/checkpoint-110`, `-220` | ApacheJIT (leaked corpus) | 1759 | 220 | 2 | 13h46m | — | — |
| `sft-cve/checkpoint-172` | CVEfixes pairs | 2000 → 1376 used | 172 | 1 | 9h49m | 0.925 | 0.862 |

`sft-cve` lost ~600 examples to `MAX_SEQ_LENGTH=1024`: prompts over the limit
lose their assistant turn entirely and TRL drops them as fully masked. Pairs are
within 2 characters of each other, so the drops are symmetric and balance holds.

Hyperparameters were held identical between the two runs so that the difference
is attributable to the data.

---

## 7. Corpora

| file | rows | status |
|---|---|---|
| `apachejit_commits.jsonl` | 7989 | ✅ sound |
| `detect_eval.jsonl` | 1000 (500/500) | ✅ sound, SZZ only |
| `heldout_unhinted.jsonl` | 200 | ✅ sound |
| `cvefixes_eval.jsonl` | 1000 (500 pairs) | ⚠️ explanation only, see §4 |
| `cvefixes_train.jsonl` | 2000 (1000 pairs) | ⚠️ same, repo/CVE-disjoint from eval |
| `cvefixes_all.jsonl` | 13850 (6925 pairs) | full scan, 3074 repositories |
| `cve_gate.jsonl` | 3000 | train+eval concatenated, positional split at 0.6667 |
| `labelled.jsonl` and everything derived | 1959 | ⚠️ label leakage, not reportable |
| `mined.jsonl` | 0 | empty |

`CVEfixes.db` — 52 GB, 11873 CVEs, 12923 fixes, 12107 commits, 51342 file
changes. Full corpus language spread: PHP 3392, C 3162, JavaScript 1108,
Python 1098, C++ 1032, Ruby 662, TypeScript 616, Go 588.

---

## 8. What the numbers support

| claim | evidence | verdict |
|---|---|---|
| the gate detects | AUC 0.822 vs counting 0.638, ApacheJIT n=1598 | ✅ holds |
| reading code beats counting lines | +0.045 AUC over metrics-only, with control | ✅ holds |
| fine-tuning improves format | grounded 99.1% vs 80.7%, both corpora | ✅ holds |
| fine-tuning improves detection | +9.5pp on ApacheJIT, p=0.007 | ⚠️ in-distribution only |
| the LLM detects out of distribution | separation −4.2pp on CVEfixes | ❌ fails |
| the LLM beats the trivial baseline | F1 0.64 vs 0.665 | ❌ fails |
| distillation preserves the taxonomy | `security` 12.9% vs stock's 32.1% | ❌ fails |
| CVEfixes is a clean detection benchmark | counting scores 0.934 | ❌ fails |

---

## 9. Next

Ordered by cost. Everything in the first group is free and answers an
acceptance criterion.

### No GPU, do first

1. **Explanation quality against the human text.** Never actually measured.
   `cve_sft220.jsonl` and `cve_stock.jsonl` already hold 754 and 851 findings
   beside the CVE descriptions that are the ground truth. This is the core of
   acceptance criterion 4 and the strongest evidence available for the reviewable
   findings claim, and it costs nothing — the inference is already done.
2. **Gate/LLM disagreement rate.** Two independent verdicts on the same commits;
   no prior JIT work has had a second one to compare. Score the gate over
   `detect_eval.jsonl` and cross-tabulate with `detect_sft220.jsonl`.
3. **Commit the repository.** 33 untracked source files against a single
   `initial commit`. `corpus/cvefixes.py`, `count_control.py`,
   `evaluate.py --paired`, three docs.

### Cheap, decides the paper's shape

4. **Repair the paired construction, or retire the detection claim.** Two
   options: match pairs on `+`/`-` balance (correct, costs most of the corpus —
   6925 pairs is enough to absorb it), or recover real vulnerability-introducing
   commits by running SZZ over each fix, which needs full clones. Re-run
   `count_control.py` on whatever comes out; if it is not near 0.5, it is not
   fixed.
5. **Rebuild the CVE training set with a non-degenerate clean target.** The clean
   half needs a target that cannot be produced without reading the diff. Either
   drop it from training and sample negatives elsewhere, or derive it from the
   diff. Verify with a distinct-assistant-turn count before spending GPU.

### GPU, only after 4 and 5

6. **Retrain on the repaired corpus.** ~10h. This is the experiment that decides
   whether a small model can learn direction when trained on it directly.
7. **Phase 2 comparability** — `corpus/deepjit.py` for QT (C++) and OPENSTACK
   (Python), authors' splits unchanged. Enables a table against published
   DeepJIT / CC2Vec / JITLine numbers.

### Reconsidered

8. **The unhinted ApacheJIT relabel** (~34 GPU hours) stays deferred. A 120B
   teacher scores F1 0.49 there, below the 0.63 baseline — the signal is not in
   the diff, and distilling it would spend the budget to reproduce noise.

### Prompt rules cannot move the SFT'd 3B (17 Aug)

Divide-by-zero in new Go code (`calculator.go`): summary says "risky, no zero
check", findings stay empty. Tried, in order, on the served checkpoint-220:

- `INFERENCE_SAMPLES=3` consensus: no change (majority of structured heads
  says "no finding"; consensus amplifies the bias, does not fix it).
- `SYSTEM_PROMPT` rule "missing validation in new code IS a finding", then
  promoted to rule 3 with an inline divide example: no change, single-sample
  or consensus.

Cause: SFT targets (Java bug-fix commits) contain findings only for changed-
line wrongness (flips, null derefs); "absent guard in new code" is outside the
target distribution, and prompt text cannot override the imprint at 3B.

Fix is data, not prompt: mined Go/JS commits whose fixes ADD guards (e.g.
dovecot `return -1` on error) put missing-validation into the SFT target
distribution. Until then, measure the gap: summaries flagging risk with empty
findings = unreported-risk rate, report it as a known limitation.

### Labelling throughput was a retry bug, not a token budget (18 Aug)

Pass 1 over `data/multilang_commits.jsonl` had been averaging ~5 minutes per
commit — 14 records in 75 minutes on 18 Aug, against a per-minute budget that
allows roughly four. The worker thread spent that time in `time.sleep`, not in
the network, so the ceiling was self-inflicted.

Measured cause, in three steps:

1. One labelling call costs `1863` total tokens (1226 prompt, 637 completion,
   of which 502 are reasoning) and returns in ~1.8s. Reproduce by posting
   `SYSTEM_PROMPT` + `build_user_message(...)` for one record and reading
   `usage` off the response.
2. Groq's free tier caps **tokens per day**, not only per minute:
   `Rate limit reached ... on tokens per day (TPD): Limit 200000, Used 199955`.
   The three keys sit in three *different* organisations, so the daily budget
   is 3 × 200,000 = **600,000 tokens/day ≈ 320 commits/day**, and the 8000 TPM
   limit is never the binding constraint over a long run.
3. An exhausted key answers with `retry-after` in the hundreds of seconds (716s
   and 960s observed). `ask()` rotated keys by `attempt % len(keys)`, so every
   commit began on the same spent key, slept out its full daily penalty, and
   only then tried a live one. That sleep *is* the five minutes.

Fixed in `corpus/label.py`: a 429 whose penalty exceeds 60s parks that key in
`_BLOCKED` and the call retries immediately on the next live key; only when
every key is parked does it wait, and then only until the earliest unblocks.
Short (per-minute) 429s still sleep their `retry-after`. Alongside it,
`_pace()` reads `x-ratelimit-remaining-tokens` off each response and sleeps
exactly the shortfall before the next call, so the per-minute bucket is spent
smoothly instead of by collision.

Two smaller defects fell out of the same read: `--sleep` was declared and never
applied (the `--sleep 18` in `label_watch.sh` did nothing, and is now dropped),
and `Provider.keys` returned `""` for unset key variables, which would send an
empty bearer token as though it were a fallback.

Measured after the fix by counting records written to
`data/labelled_multilang.jsonl` over a 300-second window (492 -> 507):
**3.0 commits/min**, against **0.19/min** before (14 records in 75 minutes) —
a **16x** speedup, with no change to the teacher, the prompt, or `--samples`.
`--samples` was already 1: it is the argparse default and the launch command
never overrode it, so the "3x faster with `--samples 1`" note in the old handoff
was offering a speedup that did not exist.

That burst rate holds only while daily budget remains. The daily cap is the real
limit and it does not go away: at ~1,863 tokens a commit against 600,000
tokens/day the sustained ceiling is ~320 commits/day, so the remaining ~1,250
commits of passes 1 and 2 need roughly **four days** of free-tier budget. The
levers, in order, are more Groq organisations, a paid tier, or
`reasoning_effort: "low"` on the teacher call — 502 of the 637 completion tokens
are reasoning tokens.

### Targeted mining for guard-adding fixes (18 Aug)

The general mined corpus does not carry the defect class the paper needs. Across
the 512 labelled records available on 18 Aug, the teacher produced 141 findings,
of which 14 were `input-validation`, 10 `null-dereference`, and only 7 used
guard or validation language at all — about 5%. Extrapolated to the full 1,734
that is ~85 examples, which is not enough to move the behaviour that "Prompt
rules cannot move the SFT'd 3B" identified as a data problem.

`corpus/mine.py --guards` mines that class directly. A fix whose diff *adds* a
check is the mirror image of the gap: the defect is the line that was not there,
so the commit it blames back to is exactly the missing training example.

**The SZZ step had to change.** `blame_origins()` blames the lines a fix
*deleted*, which is the correct rule and useless here — a commit that only
inserts a guard deletes nothing, so it returns the empty set for precisely the
commits this mode looks for. `blame_insertion_context()` blames a ±3-line window
around each insertion point in the fix's parent instead, on the reasoning that
the line which should have been guarded is the one the guard was inserted next
to. Replaced lines still go through the original deletion-blame path.

**What counts as a guard.** An added line only qualifies if it opens a
conditional or bails out early (`COND_RE`, `EXIT_RE`), which stops `len(` from
matching every second line of ordinary code, and comments and test paths are
excluded outright. Qualifying lines are then classified into `zero-check`,
`nil-check`, `error-check`, `bounds-check`, `empty-check`, `falsy-check` and
`validation-raise`. Ruby and Rust needed the postfix form (`return if x.nil?`)
or the whole Ruby slice mined empty — the self-check in `mine.py` carries one
real hunk per language for exactly this reason.

Yield over 21 repositories, 151,476 commits of history scanned:

| | |
|---|---|
| fix commits found | 21,239 |
| of those, adding a guard | 1,839 (8.7%) |
| introducing commits mined | **1,458** |

By language — all eight, which the general corpus reached only for the four
largest: go 324, java 280, javascript 230, php 228, rust 175, python 79,
typescript 77, ruby 65.

By guard class: `nil-check` 727, `falsy-check` 536, `empty-check` 285,
`error-check` 186, **`zero-check` 146**, `bounds-check` 47,
`validation-raise` 38. The 146 zero-checks are the divide-by-zero class that
`calculator.go` exposed — against 7 guard-flavoured findings in the entire
general corpus, a 20x increase in the training signal for the exact behaviour
the prompt could not buy.

Two defects surfaced while running it. `git()` decoded subprocess output as
strict UTF-8, so one latin-1 source file raised `UnicodeDecodeError` out of the
helper and cost an entire repository's slice — `apache/commons-lang` and
`gohugoio/hugo` both died that way, the latter throwing away 207 already-detected
guard fixes (recovered: +162 records after the fix). And repository yield tracks
repository size, not the goal: the first pass returned 228 php and 15 rust.

**Composition is capped at labelling time, not mining time**, because mining is
free and labelling costs days: `label.py --per-language N`. At `--per-language
60` the guard corpus samples to ~480 balanced commits, roughly 1.5 days of
free-tier budget, against ~3 days for the uncapped 969.

Reproduce:

    python -m corpus.mine --guards --repos <slugs> \
      --langs "go typescript javascript java php rust python ruby"
    python -m corpus.label --in data/guard_commits.jsonl \
      --out data/labelled_guards.jsonl --raw data/labelled_guards_raw.jsonl \
      --provider groq --workers 1 --per-language 60 --no-balance --limit 2000

`--no-balance` matters: the guard corpus is buggy by construction, and the
balancer would otherwise fill half the sample with a clean class that does not
exist and label only half the requested limit.

### Labelling pass 1 complete (18 Aug, evening)

Pass 1 over the general mined corpus finished: **1,013 commits attempted, 1,011
kept**, 0 dropped by `verify()` in the final fragment. It overshot the 959
target because `--limit` applies to the commits *not yet done* at each
relaunch, not to the cumulative total — a resumed run therefore attempts up to
`limit` more. Harmless here (more corpus), but it means the limit is not a
budget cap across restarts.

Composition of the 1,011:

| | |
|---|---|
| buggy / clean | 415 / 596 |
| languages | go 302, javascript 222, php 107, java 88, rust 79, python 78, typescript 70, ruby 59 (+6 stragglers: c 4, kotlin 1, unlabelled 1) |
| findings | 275 total — logic-error 103, error-handling 47, api-misuse 34, input-validation 33, null-dereference 24, resource-leak 10, other 9, security 8, concurrency 7 |

The SFT build passes its gate on this corpus:

    .venv/bin/python -m dataset_builder.build_sft_data \
      --jsonl data/labelled_multilang.jsonl \
      --langs go typescript javascript java php rust python ruby --out /tmp/dry.jsonl

gives **1,005 examples, 0% repeated assistant turns**, 251 with findings, 754
clean.

A keyword sweep for guard/validation language over those 275 findings hits **78
(28.4%)**, against the ~5% recorded above. **The two numbers are not
comparable** — the earlier 7-of-141 was a hand count, this is a broad regex. It
is not evidence the guard problem solved itself, and the targeted corpus is
still the plan.

That sweep now lives in `guard_share.py` rather than in a shell history, so
every corpus is measured the same way:

    .venv/bin/python guard_share.py data/labelled_multilang.jsonl

An earlier ad-hoc version of the same regex reported 20.7% (57 findings). It was
wrong: it matched `null (pointer|deref)` with a literal space, so it missed the
hyphenated `null-dereference` category entirely — 24 findings, every one of them
a missing-check defect. The corrected pattern matches `(nil|null)[ -]?(pointer|
deref)` and takes the count to 78. **28.4% is the pass-1 baseline the guard
corpus has to beat**; treat any earlier 20.7% in notes or handoffs as superseded.

Guard share by category on pass 1 — the breakdown is what makes the number
readable, since two categories are guard-flavoured by definition and the rest
are not:

| category | findings | guard-flavoured |
|---|---|---|
| logic-error | 103 | 10 |
| error-handling | 47 | 8 |
| api-misuse | 34 | 1 |
| input-validation | 33 | 33 |
| null-dereference | 24 | 24 |
| resource-leak | 10 | 1 |
| other | 9 | 0 |
| security | 8 | 1 |
| concurrency | 7 | 0 |

So 57 of the 78 are the two categories that are guard-flavoured by construction,
and only 21 of the other 197 findings describe a missing check. That is the gap
the targeted corpus exists to close.

**Six Groq organisations now**, not three: `GROQ_API_KEY1..6`, so the ceiling is
6 × 200,000 = 1.2M tokens/day ÷ ~1,863 tokens per commit ≈ **640 commits/day**.
The 480-commit guard phase is therefore under a day of budget, not the ~1.5 days
estimated at three keys.

### Guard-corpus labelling resumed (18 Aug, 20:48)

The phase was stopped at 6 of 480 on the evening of 18 Aug with all six Groq
keys returning 429, and both the labeller and the watchdog were killed. It was
restarted the same evening after probing the keys directly:

    curl -s -D - -o /dev/null -X POST https://api.groq.com/openai/v1/chat/completions \
      -H "Authorization: Bearer $GROQ_API_KEY1" -H "Content-Type: application/json" \
      -d '{"model":"openai/gpt-oss-120b","messages":[{"role":"user","content":"hi"}],"max_tokens":1}'

All six answered `HTTP/2 200` with `x-ratelimit-remaining-tokens: 7927` of an
8,000 limit. **The evening's 429s were the per-minute ceiling, not the daily
one** — the retry-after values in `label_guards.log` were 2–17 minutes, which is
TPM churn; a spent daily budget returns a retry-after measured in hours. Worth
remembering, because the run was stopped on the assumption that the day's budget
was gone. Probe before waiting a day: Groq does not expose a daily-remaining
header, so a single 1-token request is the only cheap way to tell the two limits
apart.

Restarted with the documented one-liner and it went straight to the guard phase,
as designed (pass 1's raw count is past its 959 limit):

    setsid nohup ./label_watch.sh >> label_watch.log 2>&1 < /dev/null &

The evening's run was stopped again at 21:0x, at **37 kept / 37 attempted of
480, 0 dropped, 0 failed** — the per-minute ceiling makes throughput about
5 commits per minute at `--workers 1`, so the remaining 443 are a next-day job
against a fresh daily budget rather than an overnight one. Composition of the
37, too small to conclude from but worth watching:

| | |
|---|---|
| records with a finding | 22 of 37 (59%) |
| guard-flavoured findings | 8 of 22 (36.4%) |

The guard share is above pass 1's 28.4%, which is the intended direction. The
finding rate is the number to watch: the corpus is buggy by construction, so a
finding rate that settles near 59% rather than near 100% means the teacher is
not seeing the guard class, and that is a prompt problem to fix *before* ten
hours of GPU time. Re-measure with `guard_share.py` at ~100 records — early
enough to change the prompt without burning the phase — and again at 480.
