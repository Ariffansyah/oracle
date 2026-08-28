<!-- ============================================================
     PROMPT FOR THE NEXT SESSION — paste everything between the
     markers as the opening message.
     ============================================================ -->

<!-- BEGIN NEXT-SESSION PROMPT

Continue ORACLE at ~/Documents/oracle.

Read `next-session.md` first — its head is current as of 28 Aug 08:45 WIB and
states what is running and what is open, in order. Then `docs/RESULTS.md`; its
top section is 28 Aug and is the one that matters. The four 27 Aug sections
below it are still true but are superseded on two points, which the 28 Aug
section names.

State: a retrain `sft-v2-pilot2` was on the GPU when the last session ended —
80 steps, 2 epochs, started 08:32:34 WIB, 257.94 s/it, ETA ~14:15 WIB. It is
the same 318 executable records as `sft-v2-pilot` with one thing changed: the
per-execution temp dir is stripped out of the targets. Check whether it finished
before anything else. The working tree is clean at 4805cbf and no server is
running.

Start here, in this order:

1. Check the training run. If it finished, score it on all three eval sets.
   Set ORACLE_OUTPUT_CONTRACT=v2 AND ORACLE_INCLUDE_SCHEMA=false on BOTH the
   serving and the scoring side — the exact commands are in next-session.md.
   Use --word-diff-module, never --word-diff. Getting this wrong reintroduces
   the confound that cost six cases in forty-six.

2. Read the result under one question only: does `fabricated` fall from 10/101
   toward zero. That is what this run was built to answer. Locus,
   `direction_ok` and `observable_ok` are secondary — the corpus is the same 318
   records, so a large move in those needs explaining, not celebrating. This run
   does NOT answer whether 318 records is enough; that was held fixed on
   purpose.

3. Then the two open items: whether to give `effect.trigger` something real to
   say (it is 100% filename echo today), and the Groq fork, whose terms changed
   on 28 Aug — see "Still to do, in order".

Traps that have already cost this project a result are at the bottom of
next-session.md. The ones that bite hardest: fix prompt shape and diff rendering
across every arm of a comparison; check step arithmetic AND the clock before
quoting any run; never mix benchmark denominators; never search `effect.trigger`
in a scorer; no prompt-rule fixes and no DPO.

END NEXT-SESSION PROMPT -->

Continue ORACLE at ~/Documents/oracle. Read `docs/RESULTS.md` first — the top
section is 28 Aug and the four below it are 27 Aug, newest first. Then
`docs/ROADMAP.md`.

# Status at handoff (28 Aug, 08:45 WIB)

**A retrain is on the GPU.** `sft-v2-pilot2`, the same 318 executable records
with the temp-dir defect fixed, 80 steps, 2 epochs. **Started 08:32:34 WIB**
(verified against the process start and the log's creation time, not guessed),
measured at **257.94 s/it** on step 1, so **ETA ~14:15 WIB**. Check it before
anything else:

    ssh oracle-gpu bash -s <<'EOF'
    pgrep -af fine_tuning.train_sft
    tail -c 600 ~/oracle/sft_v2_pilot2.log | tr "\r" "\n" | tail -3
    ls ~/oracle/artifacts/sft-v2-pilot2
    EOF

Confirmed at launch: `318 SFT examples from data/sft_v2_pilot2.jsonl`, all 318
survived the fully-masked drop, 80 steps (318 x 2 / 8 = 79.5 -> 80).

`sft-v2-pilot`, the first v2 checkpoint, is trained and fully scored. Adapter at
`~/oracle/artifacts/sft-v2-pilot` on the box. Runs are committed:
`data/basic_bench_v2_pilot.jsonl`, `data/heldout_mech_v2_pilot.jsonl`,
`data/heldout_clean_v2_pilot.jsonl`.

**When it lands, score it exactly as the pilot was**, contract pinned on BOTH
sides, and compare against the pilot's numbers in `docs/RESULTS.md` 28 Aug:

    ssh oracle-gpu bash -s <<'EOF'
    cd ~/oracle
    export ORACLE_OUTPUT_CONTRACT=v2 ORACLE_INCLUDE_SCHEMA=false
    setsid nohup .venv/bin/python -m llm_explainer.serve \
        --model artifacts/sft-v2-pilot2 --port 8111 \
        > ~/oracle/serve.log 2>&1 < /dev/null &
    EOF
    setsid ssh -f -N -L 8111:localhost:8111 -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=30 -o ServerAliveCountMax=1000 oracle-gpu

    ORACLE_OUTPUT_CONTRACT=v2 ORACLE_INCLUDE_SCHEMA=false ORACLE_INFERENCE_SAMPLES=1 \
      .venv/bin/python bench/basic_bench.py --backend ollama \
      --model-name sft-v2-pilot2 --host http://localhost:8111 --word-diff-module \
      --out data/basic_bench_v2_pilot2.jsonl
    # --root bench/mechanism_heldout --out data/heldout_mech_v2_pilot2.jsonl
    # --root bench/clean_heldout     --out data/heldout_clean_v2_pilot2.jsonl

**The one question this retrain answers:** does `fabricated` fall from 10/101
toward zero once the corpus stops carrying unlearnable tokens. Everything else
(locus, `direction_ok`, `observable_ok`) is a secondary read — the corpus is the
same 318 records, so a large move in those would need explaining, not
celebrating.

**What it does NOT answer:** whether 318 records is enough. That was the other
half of the ambiguity and this run holds it fixed on purpose.

# Progress, 28 Aug, in one screen

| | before | after |
|---|---|---|
| checkpoints trained | `sft-v2-pilot` (was training) | trained, **fully scored**; `sft-v2-pilot2` training |
| checkable behavioural claims, ever | **0** | **101/101** well-formed |
| `direction_ok` | no prior | **84/101** |
| `observable_ok` | no prior | 35/101, now **reproducible** (was 35/36 flapping) |
| `fabricated` | not gradeable — no claims to grade | **10/101**, cause found and fixed at the source |
| corpus records carrying an unlearnable token | 66/318 (21%) | **0/318** |
| apparatus bugs fixed | — | 3 (2 in the reporter, 1 in the scorer) |

**On the one number that invites a bad comparison:** 27 Aug counted 6 fabricated
absolute paths in `mechanism-v2`'s 101 answers, and this session counts 9 (plus
one identical-output claim) in the pilot's 101. Same three sets, same rendering,
same schema setting, so the denominators are honestly comparable — but the
checkpoints and the contracts are not the same, so **do not report this as "the
v2 contract increased fabrication."** What changed alongside it is that the
corpus began carrying real unlearnable paths, which is the effect that was
actually isolated and fixed. `sft-v2-pilot2` is the run that separates them.

Commits: `8be80df` the pilot result, `4805cbf` the corpus + scorer fix.
Run files committed: `data/basic_bench_v2_pilot.jsonl`,
`data/heldout_mech_v2_pilot.jsonl`, `data/heldout_clean_v2_pilot.jsonl`.

**The one-line version:** the v2 contract works as a *format* — every answer now
states a behavioural claim, and 84/101 get the direction right, a question that
could not previously be asked. The claims' *content* is mostly wrong (35/101
observable), and the single biggest driver of the fabricated ones was a token
the corpus could never have taught: a random temp directory, baked into 21% of
targets by the builder that existed to stop exactly this. That is fixed and
retraining now.

**What did NOT move, and should not be claimed:** locus. 36/46 against 37/46 on
`bench/basic`, 34/34 on `clean_heldout`, 14/21 against 19/21 on
`mechanism_heldout`. False alarms did improve, 5 -> 1. The 67% locus+mechanism
ceiling this project keeps hitting is untouched — consistent with the standing
read that **the checkpoint chase is not where the contribution is.**

# What 28 Aug established

**1. The v2 contract is learned, completely.** 101/101 answers carry a
well-formed `effect` with all four keys and a legal `direction`; 0 errored
calls; `unclear` never fired. **The baseline was 0 claims on all seven stored
runs**, re-verified. This is the first checkable behavioural claim any
checkpoint in this project has made. The format question is closed.

**2. `direction_ok` is 84/101 and it catches what locus cannot.** 35/46, 19/21,
30/34. On `bench/basic`, **4 of 5 inverted and 3 of 5 fabricated answers were
graded CORRECT by the locus scorer** — `identified()` structurally cannot see an
inverted claim.

**3. The stated acceptance criterion is half met.** It was written in advance as
`direction_ok` materially above v1's implied rate **and** `fabricated` at zero.
Direction: met. **Fabricated: 10/101, not zero.**

**4. The fabricated evidence is caused by the corpus, and the fix is one line.**
`executed_effect`'s `obs()` (`build_mechanism_corpus.py:94`) writes raw executed
bytes into the target, so **66 of 318 records (21%) carry a per-execution random
temp dir** from only 16 distinct values. One of them, `/tmp/tmpd6rhx_a0/`, is in
6 records and the model re-emits it as execution evidence on **five different
cases in four languages**; another is emitted as a one-character truncation of a
corpus token. 7 of 9 fabricated paths trace to the training set. Collapsing
`/tmp/tmp\w+/` takes 66 records to 0 and keeps every claim true — verified
read-only, not yet applied.

**5. `observable_ok` is not reproducible and is slightly inflated.** Three
identical `--score` runs on the same stored file gave **14, 15, 14**. Cause: the
same temp dir. `rb-loop-bound-loosen-fix` claims `before="3"` against a Ruby
`TypeError` — wrong — but `_obs_match`'s numeric rule matches the `3` inside the
random directory name. **The tier is decided by a coin flip on a random string.**
Stripping the dir: 36/101 -> 35/101. One case today; unbounded for any
single-digit claim.

**6. `effect.trigger` is degenerate — it echoes the case filename in 101/101.**
The builder fills it with `running {id}.{ext} as written` while the schema
specifies "One input or condition that exposes the difference, e.g.
`xs = [1,2,3]`". **No scorer may ever search `trigger`**: it contains the case
name, so matching `must_mention` against it would ground an answer on its own
filename. Tested — it would flip three `mechanism_heldout` cases on the case name
alone.

**7. Locus, measured identically.** `bench/basic` 36/46 against the previous
checkpoint's 37/46, with **false alarms 5 -> 1**. `clean_heldout` 34/34,
unchanged. `mechanism_heldout` 19/21 -> **14/21**, which decomposes into one
verdict flip and four `unconfirmed` — the model still detects 18/21 but stops
citing the `must_mention` token, and some of those read as correct paraphrase.
14/21 is a floor. **The matching rule was NOT touched**; changing it requires the
random-pairing control first.

# Two apparatus bugs fixed on 28 Aug

- **`basic_bench.py` dropped every `effect_*` key when building a row**, so
  `summarise()` could never report a nonzero effect tier from a live run. The
  pilot's first run printed `effect claimed 0/46` while all 46 answers carried a
  well-formed effect. Rows now spread `grade()` whole.
- **The zero-claims line hardcoded `v1 contract`**, asserting a cause it had not
  checked. It now reads `OUTPUT_CONTRACT` and, under v2, says the zero is a
  finding to investigate.

Both are in the class this project keeps hitting: **a status line that reports
intent rather than observed state.** That list is now five entries long.

# Done on 28 Aug after the pilot was read

**The two temp-dir defects are fixed**, both sides, and the corpus is rebuilt.

- `build_mechanism_corpus.py::obs()` strips `/tmp/tmp\w+/` **before** truncating
  to 200 chars. Order matters: truncating first can cut a path mid-token and
  leave `/tmp/tmp8bzrai1` from `/tmp/tmp8bzrai1x`, which is exactly the
  one-character-truncated form the pilot emitted on two cases.
- `bench/basic_bench.py::outputs()` strips the same token before `_obs_match`.
  **Measured against random pairings first**, as this repo requires of any
  matching-rule change: own-case 35/101 against random-case 3/101, unchanged by
  the strip. Discrimination is identical; what it buys is determinism —
  `observable_ok` went from 35/36 fluctuating over six executions to a stable 35.
  (`_obs_match` grounding only 3/101 against a random case is itself worth
  keeping: this rule is genuinely discriminating, unlike the `identifiers()` bug
  that grounded 18-36%.)
- `data/sft_v2_pilot2.jsonl` — same builder invocation as the pilot plus the
  fix. 318 records, **0 carrying a temp dir** (was 66), 80 distinct assistant
  turns, 51% clean. Budget improved as a side effect: 117 fit as written against
  108, because the targets got shorter.

`data/sft_v2_pilot.jsonl` (the pilot's own corpus, 66 temp dirs) is preserved
unmodified. Note `data/*.jsonl` is gitignored, so corpora are not in the repo —
provenance lives in commit messages and the builder being deterministic, which
**the temp dir broke**: rebuilding the pilot corpus would have produced different
random paths. That is one more reason the strip belongs in the builder.

# Still to do, in order

**1. Score `sft-v2-pilot2` when it lands** — commands in the status section
above. The question is `fabricated`, 10/101 -> ?

**2. Give `trigger` something to say, or drop it.** It is 100% filename echo
today: the builder fills it with `running {id}.{ext} as written` while the
schema asks for "One input or condition that exposes the difference, e.g.
`xs = [1,2,3]`". The executable cases have real entry points with literal
arguments, so the builder could fill it honestly. Until then the field is dead
weight and **no scorer may search it**.

**3. The Groq fork stays open, and its terms have changed.** The user chose on
28 Aug to fix the corpus and retrain the executable set FIRST, rather than run
the `gpt-oss-120b` pass over the 1673 teacher-labelled commits. Those records
have no pre/post to execute, so their `before`/`after` would be teacher-guessed
— the exact mechanism behind the 10 fabrications, at 83% of a 2000-record
corpus. If the fork is reopened, the middle option is the defensible one: fill
only `trigger` and `direction` for the bulk records, which are derivable without
execution, and leave `before`/`after` to executable cases. **That needs a schema
change** — all four `Effect` fields are required `str` today, so a partial
effect cannot be expressed. `to_json()` already uses `exclude_none`.

# Still open, unchanged by 27 Aug

**4. The 40 real commits — still the strongest evidence available and still not
run.** `data/real_commits.jsonl`, seed 20260826, five held-out projects. Run on
two checkpoints or the numbers cannot be attributed.

    .venv/bin/python bench/real_commits.py --run data/real_commits.jsonl

**5. Inter-rater agreement.** `data/rater_packet.md` is ready and blinded. Needs
a person, not a GPU. Closes "every mechanism number here has one rater".

**6. Hand-grade v2's 46 for mechanism.** 37/46 is a locus floor, not comparable
to the 31/46 that `oracle-merged` and `mechanism-v1` scored on locus+mechanism.
Predictions are in `data/basic_bench_mechanism_v2.jsonl`. If `grade_effect`
works on the pilot, this may be mechanisable instead of hand-graded.

**7. Cost and latency, 3B vs 120B.** Untouched. The teacher scores 93% against
the student's 67%, so a reviewer will ask what the small model buys.

**8. A case worth building: hunk re-anchoring.** A real commit (Go `Counter`)
added `Reset()` around an existing `mu.Lock()`, so `Value()` silently lost its
lock. The lock lines are unchanged CONTEXT, anchored under the added function —
nothing in the diff signals the loss, you must notice an absence. The model
called it a deadlock in `Reset`. **Word-diff does not fix this** (verified); it
is a third artifact class, distinct from in-place-edit and block-rewrite. Label
is provable with `go run -race`, but `_run()` has no `-race` flag yet and a race
is not deterministic the way the off-by-one cases are.

# Traps that have already cost this project a result

- **Fix prompt shape and diff rendering across every arm of a comparison**, and
  record both in the run file. This cost six cases in forty-six.
- **Score word-diff-trained checkpoints with `--word-diff-module`**, never
  `--word-diff` (git) — they disagree on 24% of cases.
- **Check step arithmetic before quoting any run:** records x epochs /
  (batch x grad_accum). Half of two earlier corpora trained on a subset unnoticed.
  The pilot: 318 x 2 / 8 = 79.5 -> 80 steps, and all 318 survived the
  fully-masked drop.
- **Never mix benchmark denominators.** 12-, 14-, 27-, 44-, 46-, 21- and 34-case
  runs are not comparable.
- **Never report a score on `bench/mechanism_pilot` or `bench/clean_direction`** —
  those are training data.
- **No more prompt-rule fixes** (five attempts, all lost) and **no DPO**
  (null, and the pairs do not fit 6GB).
- Locus is a floor, not a verdict. `identified()` cannot see an inverted claim.
- **A summary line that hardcodes its own explanation is not evidence.**
  `basic_bench.py` printed `effect claimed 0/46 <- v1 contract` for a run whose
  46 answers all carried a well-formed effect: the row writer had dropped the
  keys and the label asserted a cause nobody checked. Before believing a zero,
  check that the thing which counts it can see the thing it counts.
- **`--score` needs `--root` for any non-default set.** Without it the case ids
  do not resolve and it prints `no gradable rows` — fails safe, fails silently.
- **Never search `effect.trigger` in a scorer.** It is `running {id}.{ext} as
  written`, so it contains the case name; matching `must_mention` against it
  grounds an answer on its own filename. Verified: it would flip three
  `mechanism_heldout` cases on the case name alone.
- **The executed output embeds a fresh random temp dir on every call**, so any
  rule that matches a claim against it is nondeterministic. `observable_ok`
  scored 14, 15, 14 on three identical rescores of one file, because a claimed
  `"3"` matched the `3` inside `tmpoc3wg92t`. Normalise `/tmp/tmp\w+/` out
  before matching, and before writing a training target.
- **Check the clock, not your memory, before quoting when a run started.**
  This session wrote "started ~07:05 WIB, ETA ~12:50" into the handoff from a
  guess; the process had actually started at 08:32:34 and the real ETA was
  ~14:15. Verify with the process start time and the log's creation time
  (`ps -o lstart`, `stat -c %w`), and take s/it from the run's own first step.
- **The `pgrep` self-match trap fires in new costumes.** A background waiter
  using `until ! pgrep -f "basic[_]bench.py --backend ollama"` deadlocked: the
  bracket hid the pattern literal, but the wrapper shell's command line also
  contained the real command text from the script body, so pgrep matched the
  waiting shell itself. Exit 144, again. **Do not poll for a sibling process by
  name** — run the steps sequentially in one job instead.

# The honest read, for the paper

Four moons, three checkpoints, and locus+mechanism has not moved off 67%. Each
intervention closes the failure it targets and opens another: v1 bought recall
and sold precision, v2 bought back precision and sold boundary reading. **The
checkpoint chase is not where this project's contribution is.**

The contribution is the measurement work, and it got stronger today. Locus-only
scoring overstates explanation correctness by 22 points and only execution
catches it. Targeted training data moves explanation where prompting cannot —
five times. Training data can install a **surface rule that the held-out set
cannot see**, which is a general result about evaluation design, not a fact
about this model. Add the run-level findings — half of every corpus silently
dropped, prompt shape never matching between training and inference, a
published model (CC2Vec) trained on its own test set, a gate whose advantage
over one churn feature is 0.03 AUC — and the paper is a measurement
contribution with an existence proof attached. That paper survives review. A
"we beat JITLine" paper does not.

# Apparatus fixed on 27 Aug

- `bench/basic_bench.py --word-diff-module` — renders with
  `dataset_builder/worddiff`, the module that built the v2 corpus. **Use this
  for any word-diff-trained checkpoint**; `--word-diff` (git) disagrees on 24%
  of cases and measures a train/inference mismatch.
- `bench/basic_bench.py` now refuses to print a score when >20% of calls
  errored. It had reported a total backend outage as "13/46, 0 false alarms" —
  every clean case passing by default, formatted like a real result.
- `dashboard.sh`: the benchmark panel's hallucination column had been empty
  since `summarise()` renamed it to "false alarms"; the progress bar scored
  held-out runs against `bench/basic` and printed "160%, ~74/46"; 12- and
  44-case runs sat flush against 46-case runs unmarked; the artifacts panel had
  never listed `sft-mechanism-v1` or `-v2`; the error panel showed a 67-hour-old
  traceback with no name or age. All six fixed.

# Case inventory — read before quoting any benchmark number

| directory | n | role |
|---|---|---|
| `bench/basic` | 46 | eval, the headline set |
| `bench/mechanism_pilot` | 28 | **TRAINING** — never report a score |
| `bench/clean_direction` | 54 | **TRAINING** — never report a score |
| `bench/mechanism_heldout` | 21 | eval, held-out families (was 14 before 27 Aug) |
| `bench/clean_heldout` | 34 | eval, held-out families (was 27 before 27 Aug) |

`basic_bench.py` prints a block warning if you point `--root` at the two
training directories.

# The project

Two-stage JIT defect prediction. Title settled: "Predict, Then Explain:
Just-In-Time Defect Prediction with Natural-Language Findings". Stage 1 is a
gate classifier that detects buggy commits; Stage 2 is a fine-tuned 3B LLM that
verifies and explains. Base model Qwen2.5-Coder-3B-Instruct, QLoRA SFT on
teacher-labelled data (gpt-oss-120b on Groq is the teacher, the 3B is the
student). Do NOT use "Explainable JIT" — taken by PyExplainer / JITLine.

**The user's stated goal (24 Aug), which supersedes the old framing:** get
basic algorithmic code (loops, functions, boundaries) in the 8 corpus
languages to **8/10 correct with no hallucination**. That is a narrower and
much more achievable target than beating a baseline on Apache Java, and
`bench/basic_bench.py` is the instrument for it.

# Where this landed

`sft-ml8-grounded` trained cleanly and is **worse than the checkpoint it was
meant to replace.** 154/154 steps in 9h27m, finished 25 Aug 10:10 WIB, loss
1.714 -> 0.418, token accuracy 0.597 -> 0.883, no divergence. The adapter is at
`artifacts/sft-ml8-grounded` on the box (239 MB, plus checkpoint-77 and -154).

All three models on the 44-case benchmark, greedy, one sample, fixed scorer:

| | base 3B | `oracle-merged` | `sft-ml8-grounded` |
|---|---|---|---|
| fully correct (locus) | 33/44 (75%) | **40/44 (91%)** | 38/44 (86%) |
| false alarms (proved) | 2 | **1** | 3 |

Two cases were added afterwards from a live TUI session on a real repo, so the
set is now 46. **Only `oracle-merged` has been run on all 46: 41/46 (89%), 2
false alarms.** Do not mix the denominators — base and `sft-ml8-grounded` have
never seen the two new cases.

**`oracle-merged`, the older checkpoint, is the best model this project has.**
The retrain loses 2 cases and triples the false alarms. Do not ship it.

On the full 46 (only `oracle-merged` has been run on all of them):
41/46 (89%) correct locus, 2 false alarms (4%), 0 unconfirmed — but the
hand-grade (done later on 25 Aug, see step 1 below) found the locus number
overstates it. **31/46 (67%) is correct on locus AND mechanism.** Every label
is proved by executing the code, so this is not a detection F1, but it does
**not** clear the 8/10 bar once mechanism is checked, and it does not clear "no
hallucination" either (2 proved false alarms, plus 10 cases where a wrong or
inverted causal claim is a hallucination the locus scorer cannot see).

**Training is not the lever.** Five approaches were measured and lost on 25 Aug:
retraining on the same corpus, prompt rules for summary factuality, context
injection, word-diff rendering at inference, and DPO before that. The one live
idea with a mechanism behind it is retraining on word-diffs (step 6).

The one signal worth acting on: **all three of the retrain's false alarms are
refactor-only clean cases** — `js-extract-helper`, `js-rename-param`,
`php-extract-helper` — against one for `oracle-merged`. The new checkpoint
invents defects in code that provably does not change behaviour, which is the
same failure the 0.088 rendering-variance result points at, moved the wrong
way. The 12 clean cases are where the "no hallucination" half of the goal is
decided, and the retrain went backwards on them while going forwards on
detection.

Do **not** read this as "the grounding filter hurts". `sft-ml8-grounded`
differs from `oracle-merged` in three ways at once — grounding filter, project
split, smaller corpus — which is exactly what the control run in step 3 below
exists to separate.

Serving a checkpoint (one at a time; a second 3B does not fit the 6GB card,
and an OOM would take a training run with it):

    ssh oracle-gpu bash -s <<'EOF'
    cd ~/oracle && setsid nohup .venv/bin/python -m llm_explainer.serve \
        --model artifacts/oracle-merged --port 8111 > ~/oracle/serve.log 2>&1 < /dev/null &
    EOF

`serve.py` loads a LoRA adapter directly, so a training checkpoint can be
scored without merging first.

# What this session established

**1. Fine-tuning beats the base model on this slice.** 33/44 -> 40/44, +7
cases. The base model's failures are not subtle: on six buggy cases it
describes the change correctly and then concludes "This change does not
introduce any defects", and on `ts-nullish-default` it emitted unescaped quotes
inside a JSON string and failed schema validation twice.

**2. The retrain is a small regression, not a collapse** — see "Where this
landed". A first reading said php fell 5/5 -> 1/5; it is 3/5. The difference
was the scorer, not the model (finding 4).

**3. The benchmark is 46 cases across 9 languages, all proved by execution.**

    python bench/basic_bench.py --verify     # 46/46 verified, ~3 min, no GPU

| language | buggy | clean | total |
|---|---|---|---|
| c | 3 | 1 | 4 |
| go | 3 | 2 | 5 |
| java | 4 | 1 | 5 |
| javascript | 3 | 2 | 5 |
| php | 4 | 1 | 5 |
| python | 4 | 3 | 7 |
| ruby | 4 | 1 | 5 |
| rust | 4 | 1 | 5 |
| typescript | 4 | 1 | 5 |
| **all** | **33** | **13** | **46** |

`ruby` 3.4.10 and `php` 8.5.9 were installed on the laptop for this; java 21,
deno 2.9, rustc, go, node and gcc were already present.

**4. The scorer was counting correct paraphrases as hallucinations.**
`identified()` demanded every `must_mention` token as a literal substring, and
`grade()` turned a failed match on a buggy case into a hallucination — the one
metric the goal says must be zero. Four of the retrain's seven reported
hallucinations were correct answers that paraphrased (said "removes a
null-check for an empty array" without ever writing `count`). Fixed three ways:
alternatives in `must_mention`, proved false alarms reported apart from
unconfirmed locus, and every dash-like character folded (the 3B wrote U+2011).
Three entries were also too *loose* and would have passed wrong answers:
`"int"` matched "print", `"var"` matched "variable", `"acc"` matched "across".

**5. The refactor false alarm is a rendering artifact.** A unified diff renders
an edited line as remove+add, so the model reporting a "removed" docstring was
describing its input, not inventing. `--word-diff` fixes that case and its twin
(`rs-rename-local`) — and loses 5 cases overall at inference. See step 6; this
is the clearest lead the session produced.

**6. Grounding was under-counting, and the obvious fix was worse than the bug.**
`evaluate.py`'s `identifiers()` kept only `_` / `.` / camelCase tokens, so a C
or Makefile diff had an *empty* vocabulary and no finding about it could ever
ground. Admitting plain names naively moves grounding 82.5% -> 98.9% and is a
trap: scored against **randomly paired commits**, that rule grounds 18–36% of
findings on a diff they have nothing to do with. The shipped rule — one
decorated name, or three plain, or one plain when the changed code has no
decorated names at all — beats the old rule on separation on all three corpora
while finding more real groundings. Grounding is now **92.7%** on
`labelled_multilang`; **82.5%, 78.3% and 81.9% are all superseded.**

**7. Two bugs made every earlier basic-bench number un-reproducible.**
`INFERENCE_SAMPLES=1` set nothing — `config.py:18` reads
`ORACLE_INFERENCE_SAMPLES` — so every earlier run was 3-sample consensus while
its write-up said greedy. And the three samples were byte-identical anyway,
because `serve.py` ignores the request's temperature. **`_analyze_consensus`
has therefore never done anything through `serve.py`**: the "sample several
times, keep what a majority agrees on" defence is a no-op on the backend where
every measurement is taken. `_env()` now warns when a bare name is set and the
prefixed one is not. Full write-up in `docs/RESULTS.md`.

# The path from here (26 Aug — SUPERSEDED by "What to do, in order" at the top)

**Kept for the reasoning, not the ordering.** v2 has since trained and been
benchmarked; item A below is done. Read the head of this file for what is open.

The thing that was in doubt is no longer in doubt: **a 3B task-specific model
can be taught mechanism.** 27 examples fixed three of four inverted-direction
failures where four prompt-rule attempts fixed none. That is the premise of
the whole thesis — a small model that explains, not a wrapper around a large
one — and it now has evidence behind it. The 25 Aug pivot recommendation was
written before this and should not be acted on without re-reading it.

What to do, in order of how much it changes the outcome:

**A. The combined retrain. DONE — trained 27 Aug, benchmarked 27 Aug: 37/46,
and it taught the model a boundary surface rule. See the head of this file and
`docs/RESULTS.md`.**
Regenerate the SFT corpus as word-diffs, keep the
27 mechanism cases, and **add clean-direction examples** (the same constructs
where they are not defects, and commits that *fix* these bugs). This addresses
both halves at once and nothing about it is speculative: word-diff is the
measured fix for the six "removed" fabrications, mechanism cases are the
measured fix for direction, and clean-direction examples are the missing
counterweight to a 100%-buggy corpus. ~14h on the card.

**B. The head-to-head with DeepJIT / CC2Vec / JITLine. DONE 26 Aug — see the
night-session block below.** `corpus/deepjit.py` did NOT exist when this was
written; `docs/RESULTS.md:431` lists it under *Phase 2 comparability*, i.e.
future work, and this paragraph misread that as present tense. It exists now,
and the gate lands inside the published range. The
project claims to close a gap with these systems and has never measured
against them. Either the gate lands inside their published range (AUC 0.829 on
ApacheJIT suggests it can) and the framing becomes real, or it does not and a
claim that would not have survived review is caught early.

**C. Grade real commits, not just the 46. SAMPLED 26 Aug night, model run still
owed** — `data/real_commits.jsonl`, 40 commits, seed 20260826.
The TUI session above showed the
locus/mechanism split on real code but produced no number. Record the repo and
revisions, grade each finding locus / mechanism / wrong, verify every mechanism
claim by execution. This is the cheapest fix for the two biggest weaknesses in
the evaluation — n=46, and all-synthetic — and the repos are already cloned.
Use only the five held-out projects.

**D. A second grader.** Every mechanism number in this project has one rater.
For a claim that is entirely about explanation quality, that is the weakest
evidence for the strongest claim. Inter-rater agreement on even 20 cases would
fix it.

**E. Cost and latency, 3B vs 120B.** The teacher scores 93% against the
student's 67%, so a reviewer will ask what the small model buys. "Not a chat
wrapper" is a design principle, not a result. Measure tokens/sec, memory, and
per-commit cost on both and the argument becomes a number.

**Paper framing, honestly.** The detection half loses to a trivial baseline
(F1 0.64 vs always-buggy 0.665, and on a leaked corpus at that), so a
"we beat JITLine on detection" paper is not supported. What *is* supported is
a measurement contribution: locus-only scoring overstates explanation
correctness by 22 points, only execution catches it, the gap is 4x wider on a
3B than a 120B, and targeted training data moves it where prompting cannot —
plus execution-proved labels instead of SZZ, the random-pairing control, and
the rendering-variance result. That paper survives a reviewer who notices the
F1. The other one does not.

# Next steps, in order

**1. DONE (25 Aug, later in the day).** Hand-graded the 46 for mechanism, not
just locus. Result: **31/46 (67%), not 41/46 (89%)** — 10 cases where the model
names the right construct but the causal claim is wrong or inverted, on top of
the 5 already-known locus misses. Full list with claimed-vs-verified in
`docs/RESULTS.md` ("The hand-grade (25 Aug): 31/46, not 41/46"). Four of the
ten are a specific pattern — inverted direction of effect
(`c-int-division`, `go-accum-reset`, `rb-string-mutate`, `rs-int-division`):
right line, right category, backwards direction. This is a third species of
failure, distinct from the two already on record: cites the right tokens,
states the right category, gets the mechanism backwards. Neither grounding nor
the locus scorer can see it; only execution does. **67% is now the number that
gates the 8/10 goal, and it is not close.**

**1b. DONE and lost, same day.** Tested a "trace-through" `SYSTEM_PROMPT`
addendum aimed squarely at the inverted-direction pattern above (trace a
concrete example through old/new code before naming a direction). Full 46-case
rerun, monkeypatched in-process, nothing in the repo touched. **Fixed zero of
the ten mechanism failures.** Six were unchanged in substance, two got *worse*
(`c-int-division` fabricated a new false claim — "overflow" and "division by
zero" that do not happen; `go-accum-reset` stopped flagging the bug at all).
At the automated locus level it net regressed too: 41/46 -> 40/46, 2 -> 3 false
alarms, with two new invented defects on clean refactors
(`go-extract-helper`, `py-comprehension`). Write-up in `docs/RESULTS.md`
("The trace-through prompt addendum: tested, lost"). **Do not retry
prompt-level fixes for mechanism** — this is the fourth prompt-rule attempt to
fail in this project, each disproved by actually rerunning the benchmark. The
inverted-direction failures look like a property of the model's reasoning, not
something reachable by telling it to reason more carefully.

**2. Decide whether `_analyze_consensus` should be made real.** It is a no-op
through `serve.py` (finding 5), so a designed safeguard does not exist where it
is measured. Two options, and this is a judgement call rather than a bug fix:
make `serve.py` honour the request's temperature — which makes every run
non-deterministic and breaks comparability with everything measured so far — or
delete the consensus path and say so in the paper. **Do not change it silently
between benchmark runs.**

**3. The isolating control run**, now clearly worth the GPU time.
`data/sft_ml8_base.jsonl` is built — same split, same 1332 records, grounding
filter OFF. `sft-ml8-grounded` differs from `oracle-merged` in three ways at
once, so this is the only way to attribute the regression to the filter rather
than to the project split or the smaller corpus. ~9.5h.

**4. Evaluate `oracle-merged` — not the retrain — on the clean slice.**

    data/ml8_heldout.jsonl   341 records, 5 projects
                             gin, fastapi, axios, clap, spring-boot

Those projects are in neither training set nor the gate's, so this is the first
slice clean for **both** stages, and the first honest cascade measurement
available. Use `ORACLE_INFERENCE_SAMPLES=1`.

**5. Measure the context path. It is what the TUI ships and it scores worst.**
`analyze_commit` defaults to `with_context=True` (`client.py:290`), sending
`git show -U50` plus whole post-commit file bodies. On the two `pystruct`
commits that flips **both** verdicts against the bare-diff path: it suppresses
the true finding on the buggy commit and invents one on the clean commit, 2/2
-> 0/2. Second reproduction of the 24 Aug result, first time the opposite error
is visible too. Two commits in one repo is not a rate — the point is that the
interactive tool runs the configuration nobody has measured. `bench/basic` has
no repo, so it cannot test this today; `evaluate.py --context` can.

**6. Retrain on word-diffs. This is the only live idea not already disproved.**
The refactor false alarm is a **rendering artifact, not a reasoning failure**: a
unified diff shows an edited line as remove+add, so when the model said a
docstring was "removed" it was describing the representation, not inventing.
`--word-diff=plain` removes the ambiguity and the false alarm with it. Swapping
the rendering at inference **loses** — 41/46 -> 36/46, 9 regressions against 4
improvements, because the model was fine-tuned on unified diffs and reads
boundaries badly in a notation it has never seen (`c-array-bound` and
`rs-index-bound` both become misses). The experiment that follows from the
mechanism is to regenerate the SFT corpus with word-diffs and train on them.
Measured both ways in `docs/RESULTS.md`; `bench/basic_bench.py --word-diff`
reproduces it.

**7. Chase the refactor false alarms — still the strongest live signal.**
Every clean case is a behaviour-preserving refactor (that is what makes it
clean), and refactors are where every model tested invents defects. Four
independent reproductions on 25 Aug: three in the benchmark, plus
`py-annotate-only` hit by hand in a TUI session against a real repo. Both
checkpoints fail that one, for *different* fabricated reasons — the base model
invents a removed docstring, `oracle-merged` invents a runtime `TypeError` from
type annotations, which Python does not enforce and which `python` disproves in
one line. 13 clean cases out of 46 is probably still too few to carry a rate.

**8. Retune the gate threshold on a slice separate from the eval set**, then
report an honest Stage 1 number and the cascade disagreement rate.

**9. Re-read the ruby and php grounding findings.** Per-language grounding is
now measured (see below), and ruby 80.0% / php 84.2% are the low pair — but on
20 and 19 findings, too few to act on. Read them before any per-language claim
goes in a table.

**Not on the list, deliberately:** more DPO (closed as a null), more prompt
rules (disproved 17 Aug, and again 25 Aug for summary factuality — the rule
fixed no inverted summary and cost a case), switching the inference rendering
to word-diff (measured, loses 5 cases), retraining on the same corpus
(`sft-ml8-grounded` came out worse), and more class mining (guard mining moved its class
28.4% -> 33.9% for a 0.04 F1 gap, under the noise floor).

# 26 Aug: first look at `mechanism-v1` in the TUI, on real commits

Ran the TUI against a real repo through the tunnel
(`ORACLE_BACKEND=ollama ORACLE_OLLAMA_HOST=http://localhost:8111`,
`mechanism-v1-merged` served on the box). **Unquantified — no counts, no
execution checks, an impression from reading the output.** Recorded because of
*what* the impression was, not how strong it is.

The user's own summary of what came back, unprompted: some findings correct;
some **name the right thing but the explanation misses**; some wrong. Overall
"pretty good".

That is the locus/mechanism split, observed directly, on real code, by
someone reading output rather than running a scorer. It is the **third
independent reproduction** of the taxonomy the 25 Aug hand-grade named:

1. the hand-grade on the 46 (89% locus vs 67% locus+mechanism — a 22-point gap)
2. `gpt-oss-120b` on the same 46 (98% vs 93% — a 5-point gap, so the size of
   the gap is a property of the model, not of the task)
3. this session, in the TUI, on real repository commits

**Why 3 matters more than it looks.** The strongest objection to the whole
explanation result is that the 46 cases are hand-written toy programs, so the
locus/mechanism gap might be an artifact of synthetic code. It is not — the
same three-way split shows up on real commits the model has never seen, and it
was noticed without anyone looking for it.

**What it is not:** a number. "Some / some / some" cannot go in a paper, and
"pretty good" is consistent with anything from 60% to 85%. To turn this into
evidence it needs: the repo and revisions recorded, each finding graded
locus/mechanism/wrong, and every mechanism claim checked by running the code —
the same discipline the 46 got. That is the cheapest remaining path to the
"n=46 is thin, and synthetic" problem, because real commits are free and
already cloned in `data/repos/` (use the five held-out projects — `axios`,
`clap`, `gin`, `fastapi`, `spring-boot` — the `apache__*` repos are leaked
into the gate's training set).

**Also worth noting:** the model is now biased toward reporting (33/33 recall,
7 false alarms on the benchmark), so on real commits expect over-firing. Watch
specifically for it claiming a call or line was *removed* when the diff shows
it edited in place — that single fabrication is behind 6 of the 7 benchmark
false alarms, and real commits contain far more in-place edits than the
benchmark's 13 clean refactors do. If that is what the "incorrect" ones look
like, it is the rendering artifact again and the word-diff retrain is the fix.

# 26 Aug: the mechanism retrain finished, and it is the first real movement

`sft-mechanism-v1` trained overnight (14h, 224 steps, 2 epochs, exit 0),
merged to `artifacts/mechanism-v1-merged`, served, and benchmarked. Both runs
re-scored with the current scorer so they compare:

| | `oracle-merged` | `mechanism-v1-merged` |
|---|---|---|
| fully correct (locus) | **41/46 (89%)** | 39/46 (85%) |
| buggy cases located | 30/33 | **33/33 — a project first** |
| clean cases passed | **11/13** | 6/13 |
| false alarms | **2** | 7 |

**What it bought.** Three of the four *inverted-direction* mechanism failures
are fixed — `go-accum-reset`, `rb-string-mutate`, `rs-int-division` — plus
`py-dict-mutate` and `py-pop-guard`. Hand-graded and verified by execution.
5 fixed, 1 borderline (`c-strcpy-bound`), 1 partial (`ts-reduce-empty`, now
correctly says it throws but names `RangeError`; it is `TypeError`), 3 still
wrong (`c-int-division`, `php-concat-operator`, `rs-overflow` — the last one
identical to both the baseline and gpt-oss-120b). **This is the first
intervention in this project that moved explanation correctness at all.**
Prompting moved none, four times.

**What it cost, and why it is not the same problem.** Five clean refactors
became false alarms. Six of the seven make one identical false claim: that a
call or print was *removed*, when it was edited in place. Verified: `go run
post.go` and `python3 post.py` both print `6`. That is the remove+add unified-
diff rendering artifact already on record, firing more often because the model
is now more assertive — not a new failure mode.

**The dose was small.** `sft_mechanism_v1.jsonl` is 1748 records / 1692
unique: ~1665 from the existing `sft_base`/`sft_ml8` corpora plus the 27
`bench/mechanism_pilot` cases upsampled 3x (81 records, 4.6%). Each pilot case
was seen six times. All 27 are `buggy: true` — nothing teaches the clean
direction, which is exactly what "recall to 100%, precision to 6/13" predicts.

**Next run, and it is now well-motivated rather than hopeful:** regenerate the
SFT corpus as word-diffs *and* keep the mechanism cases, then retrain. Word-
diff rendering is the measured fix for the six fabrications; the mechanism
cases are the measured fix for the direction failures. They address different
halves and neither has been tried against the other. Add clean-direction
examples to the corpus while rebuilding it.

**Not yet done:** a full 46-case mechanism hand-grade on this checkpoint. Only
the 10 known failures were re-read. 39/46 is a locus floor, exactly as 41/46
was — the comparable "67%" figure cannot be restated for `mechanism-v1` until
the rest are graded.

**Harness limitation found while trying to build the clean-direction control.**
`bench/basic_bench.py:114` defines a clean case as one where pre and post
produce *identical* output. A commit that *fixes* a bug changes behaviour, so
it cannot be labelled clean — `verify()` would call it `BAD LABEL`. The
benchmark conflates "behaviour-preserving" with "introduces no defect". True
for the 13 refactors it has, false for fixes. Testing "does the model
over-report on a commit that removes a defect" needs a third label, not a
`buggy` flag. **That is a design decision, so it was left alone.**

Artifacts on the GPU box: `artifacts/sft-mechanism-v1` (+ checkpoint-112,
checkpoint-224), `artifacts/mechanism-v1-merged` (6.2G). Logs
`sft_mechanism_v1.log`, `merge_mechanism.log`, `serve_mechanism.log`.
Rows in `data/basic_bench_mechanism_v1.jsonl`.

# Where the 26 Aug night session landed

Three things were asked for: build the combined corpus and launch, run the
head-to-head, grade real commits. Two are done, one is half-blocked. **Nothing
was committed** — the whole session is in the working tree.

## 1. The corpus finding, which outranks everything else here

**Half of every SFT corpus this project has ever trained on was silently
discarded before training.** `MAX_SEQ_LENGTH` is 1024, TRL truncates
`keep_start`, so a record whose *prompt* alone reaches 1024 tokens loses its
entire assistant turn — and TRL then drops it, printing "Dropping fully masked
examples from train dataset" while it does.

    sft_mechanism_v1   1748 records -> 890 trained   (858 dropped, 49%)
    sft_ml8_grounded   1286 records -> 616 trained   (670 dropped, 52%)

The step counts prove it without any tokenizer work and were in the logs the
whole time: 224 steps x 8 grad-accum / 2 epochs = **896**, not 1748. Any run
whose step count does not match `records x epochs / (batch x grad_accum)` is
training on a subset of its corpus. **Check that arithmetic before quoting any
training run in this project.**

Consequences, all in `docs/RESULTS.md`:

- The mechanism dose was never 4.6%. Every pilot record fit (max 1055 tokens)
  while half the bulk did not, so the real share was **9%**. The 26 Aug
  write-up's "the dose was small" paragraph is wrong by a factor of two.
- It does **not** explain the precision collapse. Truncation drops slightly
  more buggy records than clean (34.6% nominal -> 30.1% effective), far too
  small to produce recall 33/33 with precision 6/13. The one-directional
  mechanism corpus remains the explanation. *Hypothesis tested and rejected,
  not assumed.*
- `config.py:73` is stale — "414 tokens median, 476 p90, 795 max" was the DPO
  set. The real corpus is 1121 median, 1916 p90, 3996 max.

## 2. The prompt-shape mismatch, which is a confound in the v1 result

`basic_bench.py` never sets `include_schema`, and `client.py:170` resolves it to
**True** for the `ollama` backend. So every benchmark number in this project was
taken with the full JSON Schema in the prompt, while `sft_base`,
`sft_multilang8` and `sft_ml8_grounded` are **100% short-hint**.
`config.py:160` already prescribes `ORACLE_INCLUDE_SCHEMA=false` when serving
from `serve.py`, and no run has ever set it.

The 81 mechanism-pilot records are the *only* training data ever built with the
schema — 82 of 1748 in `sft_mechanism_v1`. They matched the inference shape and
the other 95% did not, which is a confound in the 26 Aug mechanism result that
nobody has controlled for. **Re-baselining `oracle-merged` and
`mechanism-v1-merged` under `ORACLE_INCLUDE_SCHEMA=false` is cheap, needs no
training, and should happen as soon as the GPU frees up.**

`sft_mechanism_v2` is built short-hint, deliberately: it keeps the corpus change
isolated to word-diff + mechanism + clean-direction + budgeting, rather than
stacking a prompt-shape change on top — which is the mistake `sft-ml8-grounded`
made when it changed three things at once.

## 3. `sft-mechanism-v2` — FINISHED 27 Aug 09:36, benchmarked. See the head.

    data/sft_mechanism_v2.jsonl   1995 records, 0 dropped, 65% clean
                                  1745 distinct assistant turns, top repeat 6x
    artifacts/sft-mechanism-v2    250 steps, 1 epoch, ~14h

Built by **`dataset_builder/build_mechanism_corpus.py`** — the builder the
26 Aug handoff said was owed. It reproduces the old bulk corpus byte-for-byte
(`--unified --mechanism-times 0 --clean-times 0` gives 1667/1667 records
identical to `data/sft_multilang8.jsonl`), so `sft_mechanism_v1` is now
retroactively explicable and v2 is reproducible from committed code.

Composition: 1667 bulk + 168 mechanism (28 cases x6) + 162 clean-direction
(54 cases x3).

**1 epoch, not 2, and that was a judgement call.** Matching v1's compute is
~1.5M tokens. v2 at 2 epochs is ~3.4M (~31h); at 1 epoch it is ~1.68M (~14.5h).
The mechanism cases are upsampled 6x so each is still seen exactly 6 times,
identical to v1's 3x over 2 epochs — the dose is preserved and the trade is more
unique data for fewer repeats.

New pieces it depends on:

- **`dataset_builder/worddiff.py`** — converts unified-diff text to word-diff.
  Needed because the corpus records carry only diff text; the original blobs are
  gone, so re-rendering with git is not an option. Self-tests against real
  `git --word-diff=plain` over every case under `bench/*/*/`: **128 of 169 match
  exactly** (76%), the rest differ only in difflib-vs-git alignment. The count
  grows as cases are added — the rate is what to watch, not the numerator. Since the same renderer can be
  used at inference, exact git parity is a nice-to-have, not a requirement —
  but **if you render word-diffs at inference, use this module, not git**, or
  training and inference disagree again.
- **`bench/clean_direction/`** — 54 cases, **every one verified by execution**,
  generated by `bench/make_clean_direction.py`. 28 *fix* (each pilot case run
  backwards, so the commit removes the defect) and 26 *refactor*
  (behaviour-preserving renames, aimed straight at the "a call was removed"
  fabrication). They carry a three-value `label` instead of a `buggy` flag,
  which is the third label the 26 Aug harness note said was needed. Execution
  caught and dropped 6 bad generations (`#include` -> `#include_x`,
  `put` -> `put_x`).
- **`bench/mechanism_pilot/*/analysis.json`** — the 27 hand-written assistant
  turns now live beside their cases instead of only inside an unreproducible
  JSONL. A 28th case, **`php-compound-assign-coerce`, had never made it into
  training at all** — it has a `meta.json` and pre/post files but was missing
  from `sft_mechanism_pilot.jsonl`. Verified by execution (`php post.php` ->
  fatal TypeError, exit 255) and its analysis written.

## 4. The head-to-head: the gate lands inside the published range

`corpus/deepjit.py` now exists. QT and OPENSTACK on the **authors' splits
unchanged** — 23133/2571 and 11973/1331 — matched 100% on commit hash.

    python -m corpus.deepjit --eval

| project | ORACLE gate AUC | JITLine AUC | ORACLE F1 | JITLine F1 |
|---|---|---|---|---|
| qt | 0.805 | 0.82 | 0.333 | 0.24 |
| openstack | 0.837 | 0.83 | 0.442 | 0.33 |

On **process metrics alone**, where JITLine adds code-token features and SMOTE.
JITLine's numbers are read out of the stored cell outputs of its own replication
notebook (Zenodo 4596503, cells 11-12), not transcribed from the paper.

**This is Stage 1 against Stage 1, and it cannot be anything else.** The code
channel in the released DeepJIT pickles is the placeholder string
`"added _ code removed _ code"` in every entry of all four splits — checked
exhaustively. Running Stage 2 on QT/OPENSTACK means re-mining both repositories
by commit hash, which is a real job and not started.

Also carry the caveat that the gate's *own* operating point (95% recall) gives
F1 0.177 / 0.354. Buying recall at a 7% base rate costs precision; that is the
right trade for a cascade and a bad leaderboard number. **AUC is the honest
comparison** — F1 here is at 0.5 against JITLine's own operating point.

**A seventh apparatus finding, and this one is external.** The JITLine abstract
(arXiv 2103.07068v2) records that **CC2Vec trained on the test set**, and that
excluding it drops CC2Vec's F-measure by **38.5% on OpenStack and 45.7% on Qt**.
That is precisely this project's own gate-leak finding — 0.495 F1, 0.21 AUC —
occurring in a published, peer-reviewed JIT defect prediction model, caught only
because someone ran a replication. It is corroboration that the apparatus
findings are the field's normal failure mode rather than a local accident, and
it belongs in the paper's opening.

Data lives in `data/deepjit/` (38MB, gitignored, re-fetchable — the module
prints the URLs).

## 5. Real commits: sampled and scaffolded, model run blocked

Blocked for a hard reason: serving a 3B while the card holds a training run
risks an OOM that kills the run. Everything that does not need the GPU is done.

    python bench/real_commits.py --sample 40      # DONE, seed 20260826
    python bench/real_commits.py --run  data/real_commits.jsonl   # NEEDS a server
    python bench/real_commits.py --sheet data/real_commits.jsonl  # worksheet

`data/real_commits.jsonl` holds **40 commits, 8 from each held-out project**
(axios, clap, fastapi, gin, spring-boot), revisions recorded, seed fixed. Filter:
non-merge, touches code, <=5 files, 343-5238 chars — a grader who cannot hold
the diff in their head cannot verify a mechanism claim about it. Range
2014-12-15 to 2026-07-29, median 1686 chars.

`--sheet` emits one section per finding with `grade` (locus | mechanism | wrong)
and `verified_by` fields. **Leave `grade` blank rather than guess when a
mechanism claim was not actually executed** — an unverified grade is what the
locus scorer already does, and reproducing it by hand adds nothing.

Run this against **v2 and `mechanism-v1-merged` both**, or the numbers cannot be
attributed to the retrain.

## 6. What this session did NOT do

- **Nothing was committed.** Deliberate — the user asked for the work, not the
  history. See the file list below.
- No full 46-case mechanism hand-grade on `mechanism-v1` (still outstanding from
  26 Aug morning; 39/46 remains a locus floor).
- No runner for `bench/mechanism_pilot` — `basic_bench.py`'s `ROOT` still points
  at `bench/basic`, so those 28 cases have still never been scored as a
  benchmark, only used as training data. `bench/clean_direction`'s 54 cases have
  the same problem and the same fix.
- The `_analyze_consensus` decision (step 2 below) is still open.

# Improvements made after the first handoff pass (26 Aug, later)

Asked "is it good for the paper?", the answer was no — one limitation would
sink it. These four items are the response. **Still nothing committed.**

## The limitation, named

**The mechanism training families were chosen by looking at test failures.**
`bench/mechanism_pilot` was built from the hand-grade's 10 mechanism failures,
one case per failure family, and checked mechanically the correspondence is
**10 of 10 — there is no held-out family.** Different programs and different
languages, so not literal test-set training, but the *selection* of what to
teach came from which tests failed.

This licenses an **existence proof** — a 3B can be taught mechanism where four
prompt-rule attempts moved nothing — and it does **not** license the rate.
"5 of 10 fixed" must not appear beside a baseline. Full write-up with the
correspondence table in `docs/RESULTS.md`, first section.

## The repairs

**1. Held-out families that no training corpus has seen.**

    bench/mechanism_heldout   14 buggy cases
    bench/clean_heldout       27 cases (14 fix + 13 refactor)

Six mechanisms absent from the pilot: operator precedence, boundary-comparison
direction, fallback/default order, unit scale, shadowed-variable update,
rounding direction, swallowed errors. All 41 proved by execution. **Score v2 and
`mechanism-v1` on these** — it is the generalisation test the project has never
had.

    python bench/basic_bench.py --root bench/mechanism_heldout --verify
    python bench/basic_bench.py --root bench/clean_heldout --verify

**2. A runner that can score any case root, and a guard on the ones it must
not.** `basic_bench.py` grew `--root`, so the 82 cases in `mechanism_pilot` and
`clean_direction` are finally scoreable — they had *never* been scored, only
used as training data. It also grew the three-value label the 26 Aug harness
note said was needed (`buggy` / `clean` / `refactor` / `fix`, via `MUST_DIFFER`),
because "behaviour-preserving" and "introduces no defect" are different claims
and a fix satisfies the second but not the first.

**The guard matters as much as the flag.** `mechanism_pilot` and
`clean_direction` are training data sitting one `--root` away from a headline
number, so the runner now prints a block warning when you score them. That is
the same class of mistake this project keeps finding in its own apparatus;
this time something warns.

    python bench/basic_bench.py --verify                              # 46/46
    python bench/basic_bench.py --root bench/mechanism_pilot --verify # 28/28
    python bench/basic_bench.py --root bench/clean_direction --verify # 54/54
    python bench/basic_bench.py --root bench/mechanism_heldout --verify # 21/21 (14/14 when written)
    python bench/basic_bench.py --root bench/clean_heldout --verify   # 34/34 (27/27 when written)

**Case inventory — read this before quoting any benchmark number:**

| directory | n | role |
|---|---|---|
| `bench/basic` | 46 | eval, the headline set |
| `bench/mechanism_pilot` | 28 | **TRAINING** — never report a score |
| `bench/clean_direction` | 54 | **TRAINING** — never report a score |
| `bench/mechanism_heldout` | 21 | eval, held-out families (was 14 before 27 Aug) |
| `bench/clean_heldout` | 34 | eval, held-out families (was 27 before 27 Aug) |

**3. The second-rater packet.** `bench/rater_packet.py --emit` writes
`data/rater_packet.md`: 20 cases, seed 20260826, **blinded** — it withholds
`meta.json`'s `note` (which states the true mechanism) and rater one's grade, so
the second rater checks the model against the program rather than an answer key.
`--score rater2.csv` reports raw agreement, Cohen's kappa and the confusion
matrix. Rater one's grades for all 46 are encoded in the module, transcribed
from the `RESULTS.md` hand-grade table.

This needs a human and is the cheapest open item: an afternoon of someone
else's time closes "every mechanism number in this project has one rater".

**4. Still the top priority when the GPU frees: the 40 real commits.** They were
sampled at random from held-out projects — no family selection, no relationship
to training data. That makes them the *cleanest* evidence for the central claim,
not merely more n. Run them on **v2 and `mechanism-v1` both**.

## What is still missing for the paper

- ~~**v2's result.** Unknown until the run ends.~~ **DONE 27 Aug: 37/46 on the
  46, 12/14 and 27/27 held-out — and the held-out boundary numbers are
  inflated by a surface rule. See the head of this file.**
- **Inter-rater agreement.** Packet ready, needs a person.
- **Real-commit grades.** Sampled, needs the GPU.
- **Cost and latency, 3B vs 120B** (item E). Untouched. Needs the GPU for the
  3B side; the Groq teacher side can be measured any time.
- ~~The full 46-case mechanism hand-grade on `mechanism-v1`.~~ **DONE — 31/46,
  tied with `oracle-merged`. See the section below.**

## One operational note learned the hard way tonight

**Launch long runs with `python -u`.** `sft_mechanism_v2.log` shows step
progress but no loss lines, because tqdm writes to stderr (unbuffered) while the
loss dicts go to stdout, which Python block-buffers at 8KB when it is not a tty.
`sft_mechanism_v1.log` has exactly 45 loss lines — about one 8KB buffer — all of
which appeared only when the process exited. The run is fine; you just cannot
watch the loss. Add `-u` next time.

# Two more things done while the GPU was busy (26 Aug, late)

Both were listed as blocked and neither actually was.

## The count control on the head-to-head — it changes what that result means

The repo's own rule is "run `count_control.py` beside every detection number",
and the DeepJIT table went in without one. Corrected:

| project | la only | la+ld | la+ld+nf | full gate | JITLine |
|---|---|---|---|---|---|
| qt | 0.741 | 0.735 | 0.744 | 0.805 | 0.82 |
| openstack | **0.797** | 0.809 | 0.807 | 0.837 | 0.83 |

**One feature — lines added — is 0.033 AUC from JITLine's published number on
OPENSTACK.** QT and OPENSTACK have very little headroom above commit size, and
DeepJIT, CC2Vec, JITLine and this gate are all competing inside it.

This settles what the head-to-head licenses: **"the gate is a credible Stage 1"
is supported; "we closed the gap with DeepJIT" is not**, because the gap is
mostly churn. It is also the eighth apparatus finding, and the second from
outside this project. The control now runs inside `corpus/deepjit.py --eval`
so the AUC cannot be quoted without it.

## The full 46-case mechanism hand-grade of `mechanism-v1` — 31/46, a tie

Outstanding since the retrain landed and it never needed the GPU: the
predictions were already in `data/basic_bench_mechanism_v1.jsonl`. Every
mechanism verdict was settled by executing pre and post. Grades are data, in
`data/handgrade_mechanism_v1.csv`.

| | `oracle-merged` | `mechanism-v1` |
|---|---|---|
| buggy located | 30/33 | **33/33** |
| of those, mechanism correct | 20 | **25** |
| clean passed | **11/13** | 6/13 |
| **locus + mechanism** | **31/46 (67%)** | **31/46 (67%)** |

**Exactly tied.** +5 correct explanations on buggy cases, −5 on clean ones. The
26 Aug "first real movement" claim stands as a description of what moved and is
wrong as a claim about net correctness; that session re-read only the 10 known
failures, so it could not see the wash.

**The finding that matters most:** `java-string-equals` is a **new
inverted-direction failure** — the model says `==` returns true for two
equal-content strings, the program prints false. The retrain did not remove
inverted direction as a class; it fixed the four instances it was trained on
and grew a fresh one elsewhere. **That is exactly what the family-selection
limitation predicts, and it is the strongest in-house evidence for it.**
`go-offbyone` is a second regression on a case `oracle-merged` got right.

Two sub-species separated for the first time, both of which the automated
scorer is blind to:

1. **Summary contradicts its own finding** — `java-array-bound` (NPE vs
   ArrayIndexOutOfBounds), `php-divzero-guard` (non-empty vs empty),
   `ts-reduce-empty` (TypeError vs RangeError). A grader reading one field
   scores these differently from one reading the other. Scorer-design problem.
2. **Right mechanism, fabricated illustration** — `rb-int-division` claims
   `mean([1,2])` is 0 (it is 1), `rb-range-bound` claims zero (it is 10),
   `py-range-bound` claims "one less" (short by 5), `rs-int-division` claims
   2.5→2 (it is 1.50→1.00). Graded **locus** here because the causal claim is
   true, but **4 of the 25 "correct" explanations carry a false number** and a
   stricter rater would grade them down. Expect the inter-rater disagreement to
   concentrate here — it is why the packet exists.

**Open question for the next session, and it is a real one:** should a
fabricated worked example inside an otherwise-correct explanation count as a
hallucination? The project's goal says "no hallucination". Under a strict
reading `mechanism-v1` is 21/46, not 31/46. **Decide it once, write it down,
and apply it to both checkpoints** — do not let it drift between runs.

# Uncommitted at handoff (night of 26 Aug)

Modified: `.gitignore` (adds `data/deepjit/`), `docs/RESULTS.md` (five new
sections), `bench/basic_bench.py` (`--root`, three-value labels, training-data
guard), `bench/make_clean_direction.py` (`--from`/`--out`), `next-session.md`.

New, untracked:

    bench/mechanism_heldout/          14 held-out cases
    bench/clean_heldout/              27 held-out cases
    bench/rater_packet.py
    data/rater_packet.md              20-case blinded packet
    data/handgrade_mechanism_v1.csv   all 46 grades, execution-verified
    dataset_builder/worddiff.py
    dataset_builder/build_mechanism_corpus.py
    corpus/deepjit.py
    bench/make_clean_direction.py
    bench/real_commits.py
    bench/clean_direction/            54 cases, 162 files
    bench/mechanism_pilot/*/analysis.json      28 files
    data/real_commits.jsonl           40 sampled commits
    data/deepjit/                     38MB, gitignored

On the box: `data/sft_mechanism_v2.jsonl`, `artifacts/sft-mechanism-v2`
(training), `sft_mechanism_v2.log`, plus `data/labelled_all.jsonl` which was
copied over because the builder needs it.

# Historical: what was uncommitted on the night of 25 Aug

**Superseded — kept for provenance.** These were committed in 0eb90b9, and the two
debts they named (a builder script, and the assistant turns living only in
an unreproducible JSONL) are both paid off by the 26 Aug night session
above. Read it for the reasoning behind the mechanism cases. Two pieces:

**`bench/mechanism_pilot/`** — 27 new hand-authored cases, `meta.json` schema
identical to `bench/basic_bench.py`'s (`buggy`, `category`, `must_mention`,
`note`), all `buggy: true`. Built directly from the hand-grade's 10 mechanism
failures rather than mined from a real repo, one case per failure family in
multiple languages: ratio-trunc / integer-division direction (c, go, java,
php), accumulator/counter reset (java, js, py, rb), alias-mutate (js, php, py,
rb), mutate-while-iterate (java, js, py, rb), empty-collection guard (go, js,
py, rb), type-coercion (js, php, py, rb), overflow (c, rs). This is the "n=200,
46 is thin" gap the pivot commit named, aimed specifically at the
inverted-direction mechanism failure rather than at locus. **Not wired into
any runner** — `bench/basic_bench.py`'s `ROOT` points at `bench/basic`, so
these 27 sit outside its reach and nothing has scored them yet.

**`data/sft_mechanism_pilot.jsonl`** (81 records = 27 cases x3) and
**`data/sft_mechanism_v1.jsonl`** (1748 records) — the pilot cases turned into
SFT examples with hand-written correct-mechanism assistant turns, then merged
into a full retrain corpus. **No builder script for either is in the repo, so
neither is reproducible from what's committed** — that is the main thing this
work still owes, because the 26 Aug result above now rests on these two files.

This was the sixth approach, and a different one from the five that lost: not
a prompt rule and not a repeat of the same corpus, but retraining on
hand-verified correct examples of the exact bug families the hand-grade showed
the model gets backwards. **It ran, and it worked on what it targeted** — see
the 26 Aug section at the top. Still outstanding: (a) a builder script so the
corpus is reproducible, (b) a runner for `mechanism_pilot` — `basic_bench.py`'s
`ROOT` points at `bench/basic`, so the 27 cases have still never been scored
as a benchmark, only used as training data, (c) the full 46-case mechanism
hand-grade on `mechanism-v1`, since only the 10 known failures were re-read.

Also untracked: **`bench/second_model_bench.py`**, the actual script behind
the "second model: gpt-oss-120b" result already written up in
`docs/RESULTS.md` — meaning that result is currently not reproducible from
committed code. (Its own repro command in the doc was also missing the
`bench/` prefix; fixed this pass.)

# Findings from 24 Aug that still stand

All reproducible, full write-ups in `docs/RESULTS.md`.

1. **Rendering variance at n=200.** 800 calls, zero dropped. Verdict agreement
   89.2%, commits unanimous 77.5%, per-rendering **F1 spread 0.088**. The n=40
   figure of 0.233 was mostly small-sample noise and must not be quoted again,
   but 0.088 is still 2.2x the 0.04 guard-corpus gap, so the variance column
   stays mandatory. This is the strongest result the project has.

2. **DPO is closed as a null.** Three runs agree it moves nothing. Greedy output
   from `sft-merged`, `oracle-merged` and `oracle-merged-v2` is byte-identical.
   Real pairs do not fit the card: 0 of 525 grounded `from_labelled` pairs are
   under `DPO_MAX_LENGTH=512` (shortest 615 tokens), 61% would need 1536, and
   the card OOMs at 768. All 525 also share one hardcoded rejected string, so
   the objective is degenerate even if it fit. **Do not spend more GPU on DPO.**

3. **The gate was trained on its own evaluation set.** `apachejit_commits.jsonl`
   contains all 200 heldout commits. Worth **0.495 F1 and 0.21 AUC**
   (0.781 -> 0.286, 0.9638 -> 0.7530). Fixed by `train_gate.py --exclude`;
   clean model at `artifacts/gate_noleak.joblib`, `gate.joblib` left in place so
   old numbers stay reproducible.

4. **`GATE_THRESHOLD` does not transfer.** Tuned to 0.047 for 95.1% recall on
   27.5%-buggy ApacheJIT, it gives 17.4% recall on the 46%-buggy heldout.
   Retuned it hits F1 0.699, but that threshold is picked on the eval set, so
   treat it as an upper bound.

5. **Stage 2 is the weakest detector in the system.** On the same 200 commits:
   always-buggy 0.630, clean gate retuned 0.699, teacher 0.491, student 0.375.
   Distillation cannot pass 0.491. Stage 1 detects; Stage 2 should be measured
   on explanation, not detection.

6. **The evaluation was out of domain.** Training is 21 non-Apache web/infra
   projects, 11.5% Java; the heldout is 100% Apache, ~85% Java, zero project
   overlap. F1 0.375 is an out-of-domain number. Student-vs-teacher is still
   clean; the variance result is unaffected.

7. **`grounded()` never rejected anything.** A finding naming a touched file
   short-circuited the check, so on single-file commits everything passed:
   69/69 live findings, 597/597 corpus. Every "grounded: N%" before 24 Aug was
   100% by construction. The 78.3% / 81.9% that replaced it are **also
   superseded** — `identifiers()` was under-counting; grounding is 92.7% on
   `labelled_multilang` under the rule shipped 25 Aug. Do not quote the old
   numbers.

8. **`fix_agreement()` has never executed.** It reads a `fix_diff` field no
   dataset provides, returned NaN, and the report's NaN guard printed nothing.
   It now says "unavailable". Making it real is blocked: ApacheJIT's `fix`
   column is a boolean not a hash, and all 500 CVEfixes pairs are exact
   reverses, which would make the metric tautological.

9. **Two species of hallucination.** Species one cites nothing — grounding
   catches it, 21.7% of live findings. Species two cites real tokens and states
   a falsehood (a heap.js finding predicting a `RangeError` that JS cannot
   raise) — **grounding is blind to it.** `bench/basic_bench.py` is the only
   instrument in the repo that can see species two, because it executes the
   code.

# Paper status

Measured against the acceptance criteria in `ROADMAP.md:86`: criteria 2 and 4
fail outright, 3 is unverified, 5 is compromised by the line-composition leak,
1 passes as written though a new leak class appeared. **Not submittable as a
detect-and-explain system.**

There is a strong paper in the negatives: rendering variance (0.088 from edits
that change no code), the gate trained on its own eval set (0.495 F1), and the
line-composition leak in paired corpora (AUC 0.934 with no model). That is a
coherent methods contribution — *how LLM-based JIT defect prediction gets
measured wrong, and by how much* — and every number in it is reproducible
today. This session added two more of the same species, both from the
measurement apparatus rather than the model: a scorer that reported correct
paraphrases as hallucinations (4 of 7 on one checkpoint), and a sampling
safeguard that has never executed on the backend where every number is taken.
A third is the grounding rule, where the *obvious* repair would have inflated
the headline number while grounding a third of findings against unrelated
commits — the random-pairing control that caught it is itself a contribution,
since no paper reporting a grounding rate appears to run one.

**Recommendation, 25 Aug: stop treating the pivot as a fallback and put it to
the professor.** The detection framing is dead — F1 0.64 against a 0.665
always-buggy baseline, ten days of work that has not moved it, five approaches
measured and lost in one day. The methods paper is not a consolation prize; it
is the stronger paper, and it is a reframing of work already done rather than
new work. Six apparatus findings now support it, each reproducible today:

| finding | magnitude |
|---|---|
| gate trained on its own eval set | 0.495 F1, 0.21 AUC |
| line-composition leak in paired corpora | AUC 0.934 with no model |
| rendering variance from edits that change no code | F1 spread 0.088 |
| `grounded()` never rejected anything | 100% by construction |
| scorer graded correct paraphrases as hallucinations | 4 of 7 on one checkpoint |
| consensus safeguard never ran on the served backend | silently absent |

The through-line is sharper than the list: **every one was caught by a control,
and the obvious repair was often worse than the bug.** The grounding fix
grounded 36% of findings against randomly paired commits until the
random-pairing control caught it. Papers reporting grounding rates do not run
that control.

Second contribution: the executable benchmark. Labels proved by running the
code, so locus separates from mechanism and a false alarm is *proved* rather
than assumed — which is what showed the refactor failure to be a rendering
artifact rather than a reasoning failure. An SZZ-labelled corpus cannot produce
that diagnosis.

**26 Aug night, and it moves the framing:** the detection half now has a real
comparison. On QT and OPENSTACK, authors' splits, the gate scores AUC 0.805 and
0.837 against JITLine's own 0.82 and 0.83 — **inside the published range, on
process metrics alone.** That does not resurrect "we beat JITLine on detection"
(it is a tie on AUC, at Stage 1, and F1 is not comparable across operating
points), but it does retire the worry that the gate is not a credible Stage 1.
The paper can now say the cascade's front half is competitive with the
literature and spend its argument on the explanation half, which is where the
contribution actually is.

It also adds a seventh apparatus finding, and the first one from outside this
project: **CC2Vec's published numbers were inflated by training on the test
set** — F-measure drops 38.5% / 45.7% once it is excluded (JITLine abstract,
arXiv 2103.07068v2). Same failure as this project's own gate leak, in a
peer-reviewed model. Lead with that pairing.

**Three gaps, in order — two now closed, one remains:**

1. **The hand-grade — DONE 25 Aug.** No longer a gap, it's a result: 31/46
   (67%), not 41/46 (89%), and it surfaces a third failure species (right
   locus, inverted mechanism) that neither grounding nor the automated scorer
   can see. This is now the strongest evidence for the methods-paper framing,
   not a loose end in it — it is a concrete demonstration that a locus-only
   metric overstates correctness by 22 points on this model.
2. **A second model — DONE 25 Aug.** Ran and hand-graded `gpt-oss-120b` (this
   project's own teacher, zero-shot, over Groq) on the same 46 cases, same
   prompt, same procedure. **45/46 locus, 43/46 locus+mechanism (93%)** — 8 of
   oracle-merged's 10 mechanism failures are fully fixed, 1 partial, 1 (
   `rs-overflow`) fails identically on both models for the same rustc-specific
   reason. Full table in `docs/RESULTS.md` ("The second model:
   `openai/gpt-oss-120b`"). Reusable script: `bench/second_model_bench.py`.
   **Reframes the project's own "training is not the lever" finding**: the
   teacher clears the mechanism bar the distilled 3B student misses, on the
   exact same cases, so the ceiling looks like it's in the distillation recipe
   (five tried, all failed) rather than in 3B capacity per se — an honest
   nuance to carry into the paper, not a reason to try a sixth retrain without
   a new mechanism behind it.
3. **n.** 46 cases is thin for a rate. Lead with the n=200 variance result,
   which is the strongest number in the project, not with the benchmark.

Venue: MSR, as `ROADMAP.md` already says — negative and methodological results
publish there.

# Committed this session (25 Aug)

    e4680b7  fix(evaluate): let plain identifiers ground a finding, with a threshold
    0391035  docs: correct the basic-bench record and hand off
    f5e3e69  fix(bench): stop scoring correct paraphrases as hallucinations
    e181184  fix(serve): use bfloat16 when there is no CUDA device
    f5ac501  fix(dashboard): stop the variance probe matching its own command line
    f1e62f5  docs: hand off with the retrain in flight and the benchmark at 44 cases
    49a3f09  docs: record the 44-case benchmark, verified in all 9 languages
    ff6bd71  feat(bench): expand basic-algorithm benchmark to 44 cases, 9 languages
    85c00bf  fix(bench): make identified() hyphen-insensitive, and score the base model

**These hashes move.** The history was rewritten at least twice during the
session — every hash above changed once already, and one rewrite silently
reverted uncommitted work in `evaluate.py` while leaving the rest of the file
alone. If a fix described in this handoff is not in the code, check the reflog
before redoing it. Regenerate the list with
`git log --oneline ae65e2e..HEAD`.

Uncommitted at handoff: `docs/RESULTS.md` and this file.

New this session: `bench/basic/` grew from 12 to 46 case directories;
`data/basic_bench_base44.jsonl`, `data/basic_bench_oracle44.jsonl` and
`data/basic_bench_ml8.jsonl` (44 rows each, the three-way run);
`data/basic_bench_base.jsonl` and `data/basic_bench_oracle.jsonl` (12 rows
each, the superseded set — keep them, `--score` still re-grades them).
`artifacts/base-3b` on the box is a symlink into the HF cache pointing at
`models--Qwen--Qwen2.5-Coder-3B-Instruct/snapshots/488639f1ff…`.

Still on the box, not synced locally: `artifacts/sft-ml8-grounded` (the
regression — keep it, step 3 compares against it), `artifacts/dpo-adapter-v2`,
`artifacts/oracle-merged-v2` (6.2 GB, the DPO null),
`artifacts/gate_noleak.joblib`. Throwaway launchers worth deleting:
`run_dpo2.sh`, `cmp3.sh`, `cmp_greedy.sh`, `ctx2.py`, `ctx_test.sh`.

# Operational notes

- **Training runs on `oracle-gpu`, never locally.** The local venv has no
  `trl`/`peft`/`datasets`/`accelerate`/`bitsandbytes`, and this laptop's GPU is
  an AMD Radeon 680M with no ROCm stack. Installing training deps locally drags
  in a CPU torch that replaces the CUDA wheel; restore with
  `pip install --force-reinstall torch==2.13.0 --index-url https://download.pytorch.org/whl/cu130`
  and re-pin `fsspec<=2026.6.0`.
- **The remote shell on `oracle-gpu` is fish**, and it bit twice this session.
  `VAR=val cmd` prefixes, `$!`, and any `\"...$...\"` nesting fail there with
  exit 127 or `fish: $" is not a valid variable in fish`. The shape that always
  works is a heredoc:

      ssh oracle-gpu bash -s <<'EOF'
      ...bash here...
      EOF

  `ssh oracle-gpu 'bash -lc "..."'` works only while the inner string contains
  no `$`.
- **Check the step count against the corpus size before trusting a run.**
  `steps == records * epochs / (batch_size * grad_accum)` must hold. When it
  does not, TRL truncated records past `MAX_SEQ_LENGTH` (1024, `keep_start`),
  their assistant turn was cut off, and TRL dropped them as fully masked — 49%
  of `sft_mechanism_v1` and 52% of `sft_ml8_grounded` went that way. Build
  corpora with `dataset_builder/build_mechanism_corpus.py --tokenizer`, which
  shrinks each diff until the answer survives; it reports
  "N fit as written, M had the diff shrunk, K dropped".
- **`include_schema` does not default the way the corpora were built.**
  `client.py:170` gives the `ollama` backend `include_schema=True`, so every
  benchmark run sends the full JSON Schema while the corpora are short-hint.
  Pin it: `ORACLE_INCLUDE_SCHEMA=false` for a tuned checkpoint, and say which
  setting a number was taken under. `basic_bench.py` does not set it at all.
- **Every setting is read as `ORACLE_<NAME>`.** `config.py:18` is
  `os.getenv(f"ORACLE_{name}")`, so a bare `INFERENCE_SAMPLES=1` sets nothing
  and the run silently uses the default of 3. `_env()` now prints a warning to
  stderr when the bare name is set and the prefixed one is not — **if you see
  that line, the run you just started is not configured the way you think.**
  Pin comparisons with `ORACLE_INFERENCE_SAMPLES=1`.
- **`serve.py` ignores the request's temperature**, so through the served
  backend every sample is greedy and the samples are byte-identical. That makes
  `INFERENCE_SAMPLES=3` deterministic but 3x the cost, and it makes
  `_analyze_consensus` a no-op — see step 2 in "Next steps". Results are still
  not identical to a 1-sample run: `client.py:473` keeps only the first finding
  per category, so consensus can drop a second finding of the same category.
- **Four status checks in this repo report intent, not observed state**:
  `dashboard.sh` called a *completed* variance run "STUCK" (its stall check
  reads mtime); `serve.sh stop` printed `tunnel closed` while leaving the
  forwarder listening; `serve.sh start` printed "server started" on the launch
  command returning, not on the server answering; and `serve.sh`'s `ssh -f -N -L`
  tunnel does not survive being launched from a detached context. Open the
  tunnel by hand:

      setsid ssh -f -N -L 8111:localhost:8111 -o ExitOnForwardFailure=yes \
          -o ServerAliveInterval=30 -o ServerAliveCountMax=1000 oracle-gpu

  `ssh -O exit oracle-gpu` does **not** close it — that only drops the control
  master. Find the forwarder with `ss -tlnp | grep 8111` and kill the pid.
- **The `pkill`/`pgrep` self-match trap is real** and `serve.sh:29` warns about
  it. It fired twice this session: `pkill -f "8111:localhost:8111"` killed its
  own shell (exit 144), and `pgrep -f llm_explainer.serve` reported two live
  pids for a server that was already dead — both were the pgrep pipeline
  itself. **Confirm a server is down with `nvidia-smi`, not with `pgrep`.**
- **`main.py analyze --commit` is broken on the box.** `main.py:99` imports
  `git_diff` from `ui.tui_app`, which imports `textual`, which is not installed
  there. Work around it by calling `llm_explainer.context.gather` directly, the
  way `evaluate.py:119` does.
- Long GPU jobs: launch with `setsid nohup ... < /dev/null &` so they survive
  the local machine disconnecting.
- The `ssh ... "cd ~/oracle && cmd &"` shape puts only the backgrounded half in
  `~/oracle`; anything after the `&` runs in the login directory.
- Editing a script while it runs on the GPU box: write a temp file and `mv` it
  into place, never `sed -i` — a running bash re-reads its script by byte
  offset.
- Local venv `.venv/bin/python`, always. Keys: `~/.zshrc` exports
  `GROQ_API_KEY1..6` and `DEEPSEEK_API_KEY`. Labelling is done.
- Run `count_control.py` beside every detection number.
- `data/go_race_case.diff` is the cheapest end-to-end check: the model should
  report `concurrency`, and `go run -race` proves the bug (4 warnings; ~4% of
  runs lose a record). Every checkpoint so far reports it clean.
- Benchmark runtimes now installed on the laptop: `ruby` 3.4.10 and `php` 8.5.9
  (`sudo pacman -S ruby php`). `java` 21, `deno` 2.9, `rustc`, `go`, `node` and
  `gcc` were already there. `--verify` names the missing binary if one goes
  away.

# Known-stale comments worth fixing

In `fine_tuning/train_dpo.py`:

- The `padding_free=True` comment (~line 167) claims it saves about a quarter
  of the activation memory. **Confirmed dead** — TRL 1.9.2 prints
  `padding_free=True is temporarily unavailable after a refactor and is
  currently disabled` on every run.
- The comment below it says prompts run 751–1132 tokens, median 751. The
  measured DPO set is 414 median, 476 p90, 795 max. `config.py` is correct.
- `truncation_mode="keep_end"` warns it is deprecated and removed in TRL v2.0.0.

In `evaluate.py`: **fixed 25 Aug**, `identifiers()` now admits plain names and
`grounded()` applies a threshold. Left here because the *method* matters more
than the fix: the obvious version of this fix was worse than the bug, and only
a control caught it. Scoring each finding against a randomly paired commit
showed that admitting plain names freely grounds 18–36% of findings against an
unrelated diff. **Any future change to a matching rule in this repo should be
measured that way before it ships** — a rule that cannot tell a real pairing
from a random one is not measuring what it claims to.

# Decisions made (do not relitigate)

- **The immediate goal is the basic-algorithm slice at 8/10 with no
  hallucination**, measured by `bench/basic_bench.py`, not detection F1 on
  Apache Java.
- **No CPU inference.** Ruled out by the user 25 Aug; wait for the GPU.
- **Small goal before frameworks.** Framework idiom (next.js / react) is a
  LATER phase; the rules already exist in `llm_explainer/context.py`
  (`detect_framework`, `FRAMEWORK_RULES`).
- DPO ran on checkpoint-204, not checkpoint-136. Done, and now closed as a null.
- Do NOT switch the teacher to deepseek — the user vetoed it.
- The user's professor rejects "previous ML methods" (no XGBoost family). The
  narrative: the LightGBM head is infrastructure, the method is the gate→LLM
  cascade plus the eval framework. Contingency if pushed: the contrastive
  encoder (`ml_model/contrastive.py`, 27,798 pairs in
  `data/contrastive_pairs.jsonl`, tokenizer at `artifacts/code_bpe.json`) —
  started, then killed per the user's pivot. Offer it, do not assume it.
- Keep the ApacheJIT gate AUC 0.8293 as the gate's own-split number, but never
  quote a gate number measured on `labelled_heldout.jsonl` — those are leaked.
- Labelling is DONE. No more Groq budget needed.
