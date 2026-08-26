Continue ORACLE at ~/Documents/oracle. Read `docs/RESULTS.md` first (every
measurement plus the command that reproduces it), then `docs/ROADMAP.md`.

**First action this session:** nothing is running and the GPU box is free.
Read "Where this landed" — the retrain finished and is a regression, so the
obvious next move (ship it) is the wrong one.

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

# In progress, uncommitted (night of 25 Aug)

Started after the pivot-recommendation commit. The training run described
above has since consumed these. Two pieces:

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
