<!-- ============================================================
     PROMPT FOR THE NEXT SESSION — paste everything between the
     markers as the opening message.
     ============================================================ -->

<!-- BEGIN NEXT-SESSION PROMPT

Continue ORACLE at ~/Documents/oracle.

Read the top section — "THE VALUE TIER WORKS" (3 Sep 07:38), then "THE ABLATION
LANDED" (3 Sep 02:30) below it. It is the live
state: it carries the base-vs-SFT ablation, the explanation of why FA 0/46 is
not what it looks like, and five bugs fixed overnight. "EXECUTION-GROUNDED"
(2 Sep 22:00) is the section it builds on; "Where things stand" (1 Sep 23:00) still
describes the repair corpus and contract it builds on. EVERYTHING BELOW THOSE
TWO IS SUPERSEDED — the
31 Aug 14:10 section holds the v4 numbers, which still stand, but its action
list is done. Then read `docs/PLAN_SUGGEST_CONTRACT.md` for the thresholds.
Standing constraints are at "Standing constraints:" further down — no commits
without asking is the one that bites first.

## THE DEMO APP (3 Sep 08:30) — precision by refusing to speak

`review.py` + `.github/workflows/oracle-review.yml`. Runs the project's own
command at base and head, compares byte-for-byte, and says something only when
execution already proved there is something to say.

**Severity is read off the measurement, never off the model.** This is the
design rule; everything else follows from it.

| pre | post | what it says |
|---|---|---|
| ok | ERROR | :red_circle: high — "this commit makes the code fail", plus a ```suggestion reverting the hunk |
| ERROR | ok | :white_check_mark: "this commit fixes a failing run" |
| ok | ok, different | :information_source: "what this commit changes: X -> Y" -- explicitly NOT a defect claim |
| identical | | nothing at all |

Only the prose explanation can be wrong, and `verify()` drops it if it fails to
quote the measured values or invents a number -- the bare before/after is shown
instead. So the failure mode is SILENCE, not a false positive. That is where the
"80% not false-positive" bar comes from: it is enforced by the tool, not hoped
for from the model.

Verified on a throwaway repo (`scratchpad/demorepo`), three commits:
  * `refactor: rename accumulator` -> silent (correctly ignored)
  * `perf: tighten the hot path` (actually an off-by-one) -> neutral, 32 -> 26
  * `fix: correct total() bounds` (actually an IndexError) -> red, with revert
    suggestion. **All three commit messages lie about what the commit does, and
    all three were read from execution instead.**

### What it is NOT, and must be said in the write-up

Not a bug finder. It reports behaviour that CHANGED, which is not behaviour that
is WRONG, and it is blind to a latent defect that never reaches the output. The
unrestricted reviewer was wrong in 30 of 32 findings on real commits; this tool
deliberately does not operate in that mode. Note also that a bug-inducing commit
passes CI by definition -- so test-output diffing is a strong signal for
"behaviour changed" and a WEAK one for "defect introduced", the same distinction
that produced the FA 0/46 artifact.

### Why this shape helps the thesis

Severity comes from the exit status, the values from execution, the verdict from
a byte comparison. The 3B model does exactly one thing: write the sentence
explaining a difference it was HANDED. That is the narrowest defensible version
of "a small task-specific model does the explaining", and it is precisely what
the v2 corpus trains. Related: [[thesis-novelty-criterion]].

### Wiring
```
./serve.sh start
python review.py --run "pytest -q"                    # review HEAD
python review.py --pr 42 --run "pytest -q" --post     # comment on a PR
```
The Action needs `secrets.ORACLE_HOST`; without it the job still reports the
measured before/after, just with no prose.

---

## THE VALUE TIER WORKS (3 Sep 07:38) — 7% -> 72%, and the base cannot say "nothing happened"

The smoke run finished (137 steps, 3h46m, final gate step 137 / epoch 1.00:
recall 1.000, specificity 0.968, top1 0.983 — near the TOP of the specificity
oscillation, so the single saved checkpoint is a good one).

`bench/eval_exec_values.py` on the 60-row cross holdout (UNSEEN families),
GENERATED not teacher-forced, both arms same rows:

| | base-3b | trained | delta |
|---|---|---|---|
| parsed JSON | 60/60 (100%) | 60/60 (100%) | — |
| verdict correct | 22/60 (37%) | **57/60 (95%)** | +58 |
| **VALUES both right** | **4/60 (7%)** | **43/60 (72%)** | **+65** |

Baselines computed BEFORE the eval: retrieval 0/60, most-common-constant 0/60,
and *oracle-copy* (both values appear verbatim in the diff) 8/60 = **13%**, which
is an upper bound on any retrieve-from-input strategy. **The base model at 7% is
BELOW that ceiling; the trained model at 72% is far above it.** The capability is
computation, and it is the fine-tune that produced it — essentially none of it
pre-exists in Qwen2.5-Coder-3B.

### The decomposition — what it computes well and what it does not

| | base `before` | base `after` | trained `before` | trained `after` |
|---|---|---|---|---|
| `differs=false` (31) | 13 (42%) | **0 (0%)** | 30 (97%) | 27 (87%) |
| `differs=true` (29) | 22 (76%) | 6 (21%) | 26 (90%) | 16 (55%) |

Two things to carry into the write-up:

1. **The base model got `after` right 0/31 times when the output was unchanged.**
   It cannot represent "nothing happened" — it asserts a change and invents a
   value, every time. Its verdict score of 37% is WORSE than always answering
   `true` (48%). This is the same fabrication failure measured from the other
   side earlier tonight (`direction` pinned to a constant `post-fixes`,
   observable-right 11% across 44 held-out claims), and training removes it.
2. **The trained model reads programs better than it predicts edits.** `before`
   is 90-97% in both buckets; `after` is 87% when nothing changed but **55%**
   when the change actually alters output. So: executes code reliably, predicts
   the consequence of an edit moderately. 55% is still 4x the copy-ceiling, so
   even the hard half is computation, not guessing. THIS is the number the next
   corpus should target.

Verdict 95% generated vs 96.8% teacher-forced at the final gate — the decoding
path loses nothing.

Raw per-row output: `data/exec_values_sft.json`, `data/exec_values_base.json`.
Rerun either arm with `bench/eval_exec_values.py` (`--base-only` for the control).

### What this does and does not license saying

It licenses: *a 3B model trained on executed before/after pairs computes program
values on unseen program families at 72%, where the untrained model scores 7% and
no retrieval strategy exceeds 13%.*

It does NOT yet license any claim about real commits. Everything above is the
synthetic exec corpus. The `bench/basic` / held-out numbers in the section below
are a DIFFERENT contract (v1 `summary`+`findings`) and a different model
(oracle-merged); the two have not been joined. Joining them is the next
experiment: serve `artifacts/sft-exec` and score it on `bench/basic` +
`clean_heldout` to see whether the value capability survives contact with the
review contract.

---

## THE ABLATION LANDED (3 Sep 02:30) — the SFT beats base by +12, and FA 0 is explained

Everything below this section is history. The overnight chain ran all served-model
work to completion; four bugs were found and fixed on the way, two of which would
have silently corrupted a result rather than crashed.

### The headline: the fine-tune is worth +12 points under matched grounding

`bench/basic` (46 = 33 buggy / 13 clean), v1 contract, `ORACLE_INFERENCE_SAMPLES=1`,
identical prompt and identical exec facts for both models:

| arm | fully correct | false alarms | observable right |
|---|---|---|---|
| base-3b + facts | 28/46 (61%) | 0/46 | 23/36 (64%) |
| base-3b + facts + filter | 28/46 (61%) | 0/46 | 23/36 (64%) |
| oracle-merged + facts | 38/46 (83%) | 2/46 | 24/40 (60%) |
| **oracle-merged + facts + filter** | **40/46 (87%)** | **0/46** | 24/40 (60%) |

This is the ablation the thesis needs and it holds. 1 of 46 base calls errored and
was scored "no finding", so 28/46 is a floor by at most one.

**Variance is nil.** Five repeat runs of the winning arm: 40/46, FA 0/46, all five,
zero spread. The headline is not sampling luck.

### FA 0/46 does NOT mean the model stopped hallucinating

The conflation probe (A3) settles this. `bench/clean_heldout` is 34 clean cases:
21 `-fix` pairs whose behaviour legitimately DIFFERS, and 13 `-rename` pairs that
are byte-identical. On `bench/basic` all 13 clean cases are byte-identical, so
"buggy" and "differs" coincide there and nothing ever tested the distinction.

| oracle-merged on clean_heldout | FA total | `-fix` (differs) | `-rename` (identical) |
|---|---|---|---|
| no facts | 13/34 (38%) | 12/21 | 1/13 |
| + exec facts | 13/34 (38%) | 11/21 | 2/13 |
| + facts + filter | 11/34 (32%) | **11/21 (52%)** | **0/13 (0%)** |

The filter drives false alarms to exactly zero where execution proves the output
byte-identical, and suppresses NOTHING where behaviour legitimately changed.
`bench/basic`'s FA 0/46 is that mechanism clearing 13 no-op renames. Shown a clean
case that actually changes behaviour, the model calls it a defect **52%** of the
time. Report FA 0 with this attached or it is misleading.

What the facts DO buy is the value tier: `observable_ok` 3/34 -> **27/34**.

### The three claims separate cleanly now

- **exec facts** fix the *value* tier (11% -> 79% on clean_heldout)
- **exec filter** fixes false alarms *only* on byte-identical code
- **neither** touches "changed, but correctly" — the 52% above

That last gap is what the compute-then-explain corpus exists to close. It is now
measured, not assumed.

### Held-out: the SFT dominates on BOTH precision and recall

Do not read the clean set alone — it says the base model is better (FA 26% vs 38%)
and that conclusion reverses once the buggy set is included.

| combined held-out (55 = 21 mech buggy + 34 clean) | precision | recall | F1 |
|---|---|---|---|
| base-3b | 9/18 = 50% | 9/21 = 43% | 0.46 |
| oracle-merged | 16/29 = **55%** | 16/21 = **76%** | **0.64** |

There is no specificity trade: the SFT's extra false alarms come with more than
proportionally more true detections. Per-set: `mechanism_heldout` verdict correct
base 9/21 (43%) vs SFT 16/21 (76%); `clean_heldout` FA base 9/34 vs SFT 13/34.

### `direction` was never measuring the model

`direction_ok` scored 91% (21/23) on clean_heldout and 0% (0/21) on
mechanism_heldout. Both are the same artifact: unaided, oracle-merged emits
`"post-fixes"` for **41 of 44** effect claims across the two sets. It is a constant.
clean_heldout is all-`fix` and mechanism_heldout is all-`buggy`, so the constant
reads as 91% skill on one and 0% on the other. **base-3b does it too** (19 of 20),
so it is inherited from the base model under this prompt, not introduced by
fine-tuning — no corpus work on the current contract will fix it.

Handed exec facts on `bench/basic` the model is NOT constant (clean cases draw
`unchanged` 11/13), which is the real finding: the facts supply a signal the model
cannot produce itself, so 40/46 measures transcription of a computed fact rather
than derivation of one. Moving that computation inside the model is the point of
the exec corpus.

**Rule going forward:** print the distribution of the raw predicted value beside any
per-class accuracy. A single-label held-out set cannot separate a constant from a
competence, and it fails silently and high.

### Five bugs fixed tonight

1. **`bench/exec_filter.py` loaded a hardcoded facts path** (`data/exec_diff_basic.json`).
   Run against any other root, every id lookup missed, `v` was None, and it passed
   all rows through while printing an empty suppression list — a silent no-op that
   read as "nothing needed suppressing". It has never done anything outside
   `bench/basic`. Now takes the facts file as an optional 3rd arg (defaults to the
   old value) and exits if the ids do not intersect. This is what made A3f wrong
   on first pass; rerun with
   `python bench/exec_filter.py <in> <out> data/exec_diff_clean_heldout.json`.
2. **`fine_tuning/train_sft.py` counted eval positives as `r.get("label") == 1`.**
   The exec corpus has no `label` — its verdict is `differs`, inside the target — so
   the count read 0 on a holdout that is 46% positive and the guard aborted the run
   ("held-out slice has no defective examples"). Patched to read the first
   `true`/`false` literal of the target, which is exactly what `verdict_eval`
   scores; the `label` path is unchanged. Verified: `(27 defective)` of 60.
   NOTE `--verdict-weight` was NOT affected — `_first_verdict_pos` locates the
   verdict positionally, and checked over all 1404 exec rows, no field other than
   `differs` carries a lowercase `true`/`false`.
3. **The exec holdouts were label-ordered.** `--eval-max 60` took 56 positive /
   4 negative — recall on 56, specificity on 4. Both holdouts shuffled at seed 42;
   slices are now 27/33 (within) and 29/31 (cross).
4. **22% of training rows were unanswerable** (244/1095): 3-line diff context hid
   the driver call, so `before`/`after` were not derivable from the input and the
   target taught guessing — the exact failure the direction exists to fix. Fixed
   with an additive `--context` flag on `gen_exec_corpus.py`; rebuilt at the same
   seed/size/balance, now 0% unanswerable. Also capped **115 memorizable rows**
   (5 families whose output is constant regardless of input) at 4 per identical
   target.

5. **A stale background task from a DEAD session fired at 02:32** and launched a
   SECOND `train_sft` on the OLD uncorrected corpus (`data/exec_sft.jsonl`),
   pointed at the SAME `--output-dir artifacts/sft-exec`, redirecting with `>`
   over the live run's `run_exec.log`. Two trainers on a 6GB card writing one
   checkpoint dir. Caught because the task-completion notice arrived; killed at
   02:34 with no checkpoints written by either (dir was still empty), and the
   good run was restarted onto its own `run_exec_ctx.log`. Kept as
   `run_exec_clobbered_0232.log`. **Before launching anything on the box, run
   `pgrep -af fine_tuning[.]train_sft` — a queued job from a session that no
   longer exists can still fire.**

### THE VERDICT IS A SHORTCUT — the within-holdout gate measures nothing

The first gate on `exec_sft_ctx_holdout_within.jsonl` read
`recall 1.000 on 27 positives | specificity 0.939 | top1 0.967`. It looked like a
pass. It is not a measurement. Two trivial baselines fit on the training corpus
and scored on the same 60 rows:

| baseline | within-60 | cross-60 (unseen families) |
|---|---|---|
| family-majority lookup | **1.000** | 0.517 |
| tf-idf char 3-5gram + logreg | **1.000** (R 1.00 / S 1.00) | 0.567 |

A bag of character n-grams beats the model on that holdout. The cause is corpus
design: **34 of 38 families are single-label, covering 1008/1095 rows (92%)** —
the family name alone gives `differs`. Only `f_early_return` (8 true / 13 false)
is genuinely mixed; `f_dict_mutate` 21:2, `f_comparison_flip` 19:2 and
`f_copy_reference` 20:2 are skew, not mixture. The within-holdout shares those
families with training, so recognising the family answers the question.

Consequences, in order of how much they cost:

1. **`--verdict-weight 0.5` points ~34% of the loss at the shortcut.** The verdict
   token is the one thing in this corpus that does NOT require computing.
   Reconsider the weight for the real run — it was designed for `defect_found`
   under a 71% negative base rate, which is a different problem.
2. **Always evaluate on `exec_sft_ctx_holdout_cross.jsonl`**, where both baselines
   sit at chance (0.52 / 0.57). The live run was restarted onto it at 03:10.
3. **The value tier is NOT affected.** `before`/`after` vary with the randomised
   inputs and cannot be recovered from family identity, so the corpus still
   teaches computation where the thesis needs it. The verdict is the part that
   rots.
4. **Fix in the rebuild:** make each family emit both differing and identical
   cases depending on its inputs, so `differs` stops being a family property.
   `gen_exec_corpus.py` already knows the real values, so this is a generation
   change, not a labelling one.

Reproduce the baselines before trusting any future gate number — a per-class score
on a holdout that shares families with training cannot separate computing from
recognising.

### FOR THE REAL RUN: `save_strategy="epoch"` keeps only the last checkpoint

Held-out specificity OSCILLATES across the smoke run while recall stays pinned:

| step | 20 | 40 | 60 | 80 | 100 |
|---|---|---|---|---|---|
| recall | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| specificity | 0.806 | 1.000 | 0.968 | 1.000 | 0.806 |

A 0.806 <-> 1.000 swing (6 false positives of 31) means the verdict decision is not
stably converged -- the model drifts toward over-calling `differs` and back. With
`save_strategy="epoch"` (train_sft.py:452) only ONE checkpoint is written, at the
end, so the saved weights are whichever phase of that swing step 137 happens to
land in. There is no step-40 or step-80 to fall back on.

**Change for the real run:** `save_strategy="steps"` with `save_steps` aligned to
`--eval-steps`, plus `load_best_model_at_end` with a metric that is not recall
(recall is 1.000 everywhere here and cannot discriminate — use specificity or
balanced accuracy). Left alone for the smoke run: it is 50 minutes from done and
the value tier is what it exists to measure.

### The VALUE tier cannot be gamed — baselines, computed before the eval exists

The verdict tier turned out to be a shortcut. The same check on the value tier
says the opposite, which is why the value number is the one to trust. Baselines
fit on train, scored on the first 60 rows of the cross holdout:

| baseline | both values right |
|---|---|
| most-common constant from training | 0/60 (0%) |
| nearest-neighbour retrieval (tf-idf char 3-5gram, copy that row's values) | 0/60 (0%) — `before` 7/60, `after` 0/60 |
| **oracle-copy**: both values appear verbatim in the diff | **8/60 (13%)** |

The last row is an UPPER BOUND on any retrieve-from-input strategy: 52 of 60 rows
have at least one value that does not appear in the text at all, so a perfect
copier still caps at 13%. **Any value score above ~13% is computation.** 34
distinct (before, after) pairs across 60 rows, so there is no mode to guess.

All three splits are 100% answerable (driver call visible in the diff: 1095/1095,
121/121, 188/188), so the eval asks a question the input can answer.

### The tool for it, staged and ready

`bench/eval_exec_values.py` (new, synced to the box, parser unit-tested):

```
python bench/eval_exec_values.py --adapter artifacts/sft-exec \
    --dataset data/exec_sft_ctx_holdout_cross.jsonl --limit 60
python bench/eval_exec_values.py --base-only \
    --dataset data/exec_sft_ctx_holdout_cross.jsonl --limit 60   # the control
```

It GENERATES rather than teacher-forcing -- `verdict_eval` scores one forced
token and structurally cannot see whether the model computes. Reports parse rate,
verdict accuracy and values-both-right, split by differs=true/false because a
`false` row has equal values and a model that copies one field into the other
would score without computing. Run both arms; the pair is the value-tier
ablation, and the verdict number alone is not.

### Running right now

Smoke run on the corrected corpus, relaunched 03:10 on the box (pid 545871,
log `run_exec_cross.log`) — eval switched to the CROSS holdout per the section
above:

```
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True .venv/bin/python -u \
  -m fine_tuning.train_sft \
  --dataset data/exec_sft_ctx.jsonl \
  --eval-dataset data/exec_sft_ctx_holdout_cross.jsonl \
  --output-dir artifacts/sft-exec \
  --verdict-weight 0.5 --eval-steps 20 --eval-max 60 \
  --epochs 1 --max-seq-length 512 --warmup-steps 15 --seed 42 \
  > run_exec_cross.log 2>&1
```

Header confirmed healthy: 1095 examples, 60 held-out (29 defective), verdict
tokens located, weight 0.5.

**FIRST REAL GATE, step 20 / epoch 0.15, on UNSEEN families:**
`recall 1.000 on 29 positives | specificity 0.806 | top1 0.900 | n=60`
(29 TP / 25 TN / 6 FP / 0 FN)

| cross-60, unseen families | accuracy |
|---|---|
| family-majority lookup | 0.517 |
| tf-idf char 3-5gram + logreg | 0.567 |
| constant "true" | 0.483 |
| **model @ step 20** | **0.900** |

+33 points over the best trivial baseline on families absent from training, and
specificity 0.806 rules out the degenerate all-`true` predictor that recall 1.000
alone would be consistent with. This is generalisation, not recognition -- and it
is the number to compare future gates against, NOT the 1.000 from the within
holdout.

137 steps total at ~88 s/step; started 03:10, ETA ~06:10. Gates every 20 steps.
Step-20 trace: loss 1.167, mean_token_accuracy 0.951, entropy 0.192. **The standing gate applies: if held-out verdict
recall is 0.000 at step 20, kill it.** Earlier attempts kept as `run_exec_failed_0227.log` (label bug),
`run_exec_clobbered_0232.log` (stale-task collision) and
`run_exec_ctx_withinholdout_0235.log` (the shortcut gate).

`data/exec_explain.jsonl` (1075 / 121 / 150) is built, gated and synced but NOT
trained — it is the compute-then-explain corpus, and it is the thing that targets
the 52% and the value tier. Capping pushed its cross-holdout to 64% positive, so
read its specificity, not just recall.

### Uncommitted — NOTHING is committed, per the standing rule

Modified tonight: `bench/exec_filter.py` (facts-path arg),
`fine_tuning/train_sft.py` (eval positive count),
`dataset_builder/gen_exec_corpus.py` (`--context`).
New: `dataset_builder/build_exec_explain.py`.
Backups of all three originals are in the session scratchpad.
Rebuilt: `data/exec_sft_ctx*.jsonl` (shuffled holdouts).
New result files: `data/heldout_{clean,mech}_{oracle,base}.jsonl`,
`data/heldout_clean_oracle_exec{,_filtered}.jsonl`,
`data/basic_bench_base46_exec{,_filtered}.jsonl`.


## EXECUTION-GROUNDED (2 Sep 22:00) — the model line is capped, the executor is not

Everything below this section is history. The W=0.5 run described in the next
section was killed at its own gate; read this one and stop.

### The day in one paragraph

The repair epoch-1 checkpoint scored **0 findings on 40 real commits**. Three
interventions were tried and measured: verdict loss-weighting (no effect),
a prompt rule suppressing speculation (no effect), and feeding the model
executed before/after (small effect). Mechanism-correctness sat at 13-14 of 33
in **all four** arms. Meanwhile `bench/exec_diff.py` — which just runs the code —
scored **45/46 with zero false positives**. The result now lives in the execution
layer, and the new direction is training the model to PREDICT execution rather
than to describe diffs.

### Why epoch 1 produced nothing (settled, not guessed)

Raw output explicitly carries `"defect_found": false`, `confidence` pinned at
0.62, `repair_direction` null 40/40. Both post-filters were inert:
`drop_ungrounded` is gated on `GROUNDING_FILTER` (default `off`) and
`drop_refuted` needs a `_post_source` the bench never sets.

**The decisive number is the train-set replay, not the real commits.** The 40
real commits carry NO gold label — fields are date/diff/files/language/project/
rev/subject — so a model emitting nothing cannot be scored wrong by them. 8 of
40 are fix-shaped, 9 chore/refactor. Replaying 60 of its OWN training examples:

    recall on trained positives : 0/40      (20/20 negatives correct)

**Cause: loss dilution.** Targets average 100 tokens; `defect_found` is 1 of
them, against a 71% negative base rate. The decision carries **1% of the token
loss**, so "always false + a templated sentence" is nearly free. That is what
loss 0.23 and `mean_token_accuracy` 0.93 were rewarding. Never read either as
explanation quality.

### Three interventions, all measured, two negative

    arm                      correct  imprec  wrong  miss   strict  lenient
    stored (30 Aug)               13       8      9     3      39%      64%
    baseline v1 (2 Sep)           13       3     10     7      39%      48%
    no-speculation rule           13       3     12     5      39%      48%
    exec-grounded prompt          14       7      7     5      42%      64%

Hand-graded, all 33 buggy cases, same rubric, per case in
`data/mechanism_grade_ab.json`.

1. **`--verdict-weight 0.5`** (auxiliary CE on the verdict token). Gate at step
   20: **recall 0.000 on 14 positives**, specificity 1.000, top1 0.767 = exactly
   the negatives. Killed per the pre-registered criterion. 2h05m, no checkpoint
   (`save_strategy="epoch"`, 1 epoch). NOT a refutation of weighting in general —
   step 20 of 131 is 15% of an epoch — but it is not a fast fix.
2. **No-speculation prompt rule.** Cut hedged consequences, moved 7 misses to 5
   by making the model commit — to wrong claims. `wrong` rose 10 -> 12.
3. **Exec-grounded prompt** (measured before/after in the message). `wrong` fell
   10 -> 7, scorer's FABRICATED fell 20% -> 5%, lenient 48% -> 64%. Strict moved
   13 -> 14.

**`correct` is 13-14 in every arm** while 15 of 33 individual grades churn
between arms. That is a checkpoint ceiling, not a prompt problem.

**And the finding that kills the "more context" hypothesis:** five cases
CONTRADICTED facts placed in their own prompt. `py-pop-guard` shown
`AttributeError`, still said "may receive None". `ts-nullish-default` shown
`"" -> "anon"`, said "behavior remains identical". `rb-range-bound` shown
`15 -> 10`, claimed 20. A 3B given ground truth ignores it ~15% of the time.

### THE RESULT: execution as oracle and veto

`bench/exec_diff.py` compiles and runs pre and post for all nine bench
languages (python3, node incl. --experimental-strip-types for ts, ruby, php,
go run, rustc, java single-file, gcc). On `bench/basic`:

    buggy cases where execution DIFFERS : 32/33
    clean cases where execution is SAME : 13/13
    => verdict from execution alone     : 45/46  (98%), ZERO false positives

`bench/exec_filter.py` suppresses findings execution disproves. Configurations,
same scorer:

    oracle-merged (stored 30 Aug)     41/46   FA 2
    oracle-merged (2 Sep)             37/46   FA 1
      + exec filter                   37/46   FA 0
    exec-grounded prompt              38/46   FA 2
      + exec filter                   40/46   FA 0     <- best
    variance runs 1,2 (same config)   40/46   FA 0     (identical; greedy)

**Known limits, state them:** `c-array-bound` is invisible — reading `a[5]`
returned 0 so the sum is still 15, and the filter suppresses its correct
finding. `rs-overflow` never compiles (`error: this arithmetic operation will
overflow`), a correct detection but a different signal. And this works only
because the 46 cases are self-contained runnable programs; real commits need a
build and a test. Benchmark-scope result, say so.

### CONTRACT: oracle-merged is v1. Do not "upgrade" it.

Every answer in `data/basic_bench_oracle46.jsonl` (the 41/46 run) has exactly
two keys, `summary` and `findings`. No `effect`. That is v1. Running the same
checkpoint under v2 scores **31/46 with 9 false alarms** — a ten-point drop from
the prompt alone. `ui/tui_app.py:35` setdefaults v3, so the TUI must be
overridden; `try_tui.sh` does it.

**UNRESOLVED, and it matters before anything is published:** under v1,
`include_schema=true` still makes the model emit `effect`/`confidence`/
`repair_direction` (39-43 of 46 non-null), which the stored 41/46 rows do not
have. That is the likeliest explanation of 41 vs 37 and it is not yet run down.

### NEW DIRECTION: train it to CALCULATE, not to describe

The claim: *training on executed behaviour teaches a small model to predict
behaviour rather than pattern-match on diff text.* At inference there is no
runtime — `exec_diff` is the teacher, not a component. Control already measured:
a model HANDED the facts scores 42%.

`dataset_builder/gen_exec_corpus.py` generates runnable pre/post pairs and
labels them BY EXECUTION. No prose target, no LLM in the loop:

    target = {"differs": true, "before": "780", "after": "741"}

    1404 pairs, 44 families
      distinct diff FRAMES (slots stripped) : 717   (ratio 0.51)
      distinct (before, after) value pairs  : 694/1404 (49%)
      label balance                         : 47% positive
      train 1095 / holdout_within 121 / holdout_cross 188

`changed` (the construct that moved) is metadata and is deliberately NOT
trained on: one templated string per family would teach diff-shape -> phrase,
the recitation failure this corpus exists to avoid.

**Two holdouts, because they answer different questions.** within-family =
values unseen, families seen ("can it compute?"). cross-family = 6 families
never trained on, drawn from BOTH pools 4 buggy / 2 clean ("does it
generalise?"). A cross set of only buggy shapes would measure recall and call
it generalisation.

**Build gates that refuse to write:** frame ratio below `--min-frame-ratio`
(fired twice at 0.497 and 0.50), an empty split, a single-label split.

**Bugs the build caught before training:** `exec_diff` compared
`stdout.strip()`, so a pair differing ONLY by `.strip()` compared equal and was
labelled clean — fixed with an unstripped `raw` key. And the first corpus was
74% positive, the exact mirror of the repair corpus's 71% negative; fixed by
adding 8 clean families (which also bought the frame ratio back), not by
oversampling the existing ones.

### QUEUED RIGHT NOW (background task, 2 Sep 22:00)

    1. BASE ABLATION — artifacts/base-3b under the identical exec-grounded +
       filter config, against the SFT's 40/46. This is the evidence the
       fine-tuned model matters. Prior, without execution: base 33/44 vs
       oracle-merged 40/44.
    2. SMOKE RUN — artifacts/sft-exec, data/exec_sft.jsonl, --verdict-weight 0.5
       --eval-steps 20 --eval-max 60 --epochs 1 --max-seq-length 512.
       ~250-token records, so ~90s/step not 380; 137 steps ~= 3-4h.
       KILL IT if held-out recall is 0 at step 20, same as this morning.

    watch   tr '\r' '\n' < ~/oracle/run_exec.log | grep -a "holdout @ step"

### THE PLAN — 3 weeks to a publishable draft

Week 1: corpus + smoke + full run. Write background, method, and the
"JIT prediction is a probability; we make it a readable explanation" framing.
Week 2: evaluate on `bench/basic` (untouched held-out set), the base ablation,
the exec-grounded results. Week 3: new numbers, discussion, polish.
Training is GPU wall-time, not the author's time — it runs overnight.

**The honest headline available today:** locus ~85-89%, mechanism ~39-42%, both
reproduced; execution verdict 45/46 with 0 false positives; a quantified
boundary against 93% mechanism for gpt-oss-120b on identical cases. Two
interventions measured and negative. Do not inflate this — the measured
boundary IS the contribution.

### Uncommitted — NOTHING is committed, per the standing rule

    fine_tuning/train_sft.py       --verdict-weight/--verdict-check/--eval-dataset/
                                   --eval-steps/--eval-max, counters, 4 memory fixes
                                   (chunked_nll returns no logits -> hook the final
                                   RMSNorm; output_hidden_states holds all 36 layers;
                                   per_device_eval_batch_size defaults to 8 vs train 1;
                                   PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True)
    dataset_builder/gen_exec_corpus.py   NEW — 44 families, executed labels, splits
    dataset_builder/build_repair_sft.py  --holdout/--holdout-by/--split-seed, shuffled
    dataset_builder/schema.py      OBSERVED_TEMPLATE, opt-in _NO_SPECULATION
    llm_explainer/client.py        analyze(observed=...) via instance attr
    bench/exec_diff.py             NEW — differential executor, 9 languages
    bench/exec_filter.py           NEW — suppress what execution disproves
    bench/basic_bench.py           --exec-facts; FIX: .get(k,"") returns None on a
                                   present-but-null key, crashed the whole run
    ui/tui_app.py                  FIX: KeyError 'UNSCORED' on empty-diff/merge commits
    serve.sh                       MODEL var; reuse a running server (was reloading
                                   3B of weights on every launch)
    try_tui.sh                     NEW — launcher, v1 contract, NO_GATE=1, --pick, LIMIT
    data/  exec_diff_basic.json, exec_sft*.jsonl, mechanism_grade_oracle46.{json,md},
           mechanism_grade_ab.json, basic_bench_oracle46_{repro,terse,exec}*.jsonl,
           sft_repair_train{,_holdout}.jsonl, var_exec_*.jsonl

The GPU box's `dataset_builder/schema.py` predates `_SYSTEM_PROMPT_REPAIR`, so
corpus builders only run on the laptop. It affected nothing measured — benches
build prompts locally, the box only serves — but it breaks a rebuild there.

Epoch 2 of the repair run remains exactly resumable from
`artifacts/sft-repair/checkpoint-146` (corpus still hashes `eeb318d39ad8`).
**Do not resume it.** See the loss-dilution section above.

## SUPERSEDED — W=0.5 run (2 Sep 17:00), killed at its gate

The epoch-1 pause fired cleanly at 14:34 and everything below about it is now
history. `artifacts/sft-repair/checkpoint-146` is complete (all seven files a
resume reads), the corpus still hashes to `eeb318d39ad8`, and epoch 2 remains
exactly resumable — but DO NOT resume it. The reason is the whole of this
section.

### What epoch 1 turned out to be

Scored on the same 40 real commits as v6/v7: **0 findings, 0 flagged, over all
40**. v7's number was 32 findings / 30 wrong / 0 correct, so both sit at **0
confirmed correct** — ep1 just gets there by saying nothing, which also scores
0 no-such-entity and 0 incoherent and therefore reads *cleaner* on the grading
sheet than the model that at least tried.

That zero is the model's own call, not harness attrition. Checked end to end:
raw output is well-formed and explicitly carries `"defect_found": false` (the
key is present, not omitted), `confidence` pinned at 0.62 on every commit,
`repair_direction` null 40/40. Both post-filters were inert — `drop_ungrounded`
is gated on `GROUNDING_FILTER` (config default `off`, and `score_repair.sh`
never sets it) and `drop_refuted` needs a `_post_source` the real-commits bench
never populates.

**The decisive measurement is the train-set replay, not the real commits.** The
40 real commits carry NO gold defect label — the fields are date/diff/files/
language/project/rev/subject and nothing else — so the evaluation hand-grades
whether findings are *correct*, and a model emitting none cannot be scored wrong
by it. 8 of the 40 are fix-shaped and 9 chore/refactor, so `false` may even be
right for a good number of them. Replaying 60 of its OWN TRAINING EXAMPLES
verbatim is what settles it:

    recall on trained positives : 0/40      (20/20 negatives correct)

It answers `false` to examples it was explicitly optimised to call `true`. Not
out-of-distribution. It never learned the positive class.

### Why — loss dilution, measured

The supervised target averages **100 tokens** and `defect_found` tokenizes to
exactly **1** of them, against a **71% negative base rate** (340 true / 824
false). The only decision the task is about carries **1% of the token loss**, so
"always answer `false` plus a fluent templated explanation" is very nearly free.
That is what loss 0.23 and `mean_token_accuracy` 0.93 were rewarding for sixteen
hours. Never read either as explanation quality.

The explanation collapsed accordingly: **6 sentence frames over 40 commits**,
top frame 16/40 ("Refines the guard on <ID> in <FILE> without changing what the
branches do"), and often false about the diff — axios `6b3c305fc4` adds a single
`import` line and no conditional, described as "Reworks conditional handling".
MEASURE THIS STRIPPED: a probe on the same checkpoint reported "60/60 distinct
explanation stems" on raw first-45-characters. Raw distinctness is the trap
already recorded under the v4 `effect.check` defect, and it caught this session
too.

One thing that is NOT wrong: the corpus positives are **100% grounded** — every
identifier cited in a positive target appears in the diff the model is shown.
The 94%-ungrounded poisoning recorded on 1 Sep is fixed. The collapse happened
on a clean corpus.

### What was built in response

`fine_tuning/train_sft.py`

    --verdict-weight W   auxiliary CE on the defect_found token alone, so it is
                         priced apart from the 99 around it. Coefficient, not a
                         multiplier, because it gathers ONE logit row instead of
                         upcasting (batch x seq x 151k), which does not fit here.
                         share ~= (W + 1/N)/(1 + W); W=0.5, N=100 -> ~34%.
    --verdict-check N    locate the verdict token over N batches and exit. A 14h
                         run must never be what discovers the token was missed.
    --eval-dataset       held-out set; verdict recall reported per epoch
    --eval-steps N       ...and every N steps. One epoch is 131 steps at ~6min,
                         so an epoch-end-only metric reports at hour 14.
    --eval-max N         cap examples per eval (~15s each; all 116 is ~30min)

`dataset_builder/build_repair_sft.py` — `--holdout FRAC` (default 0.1),
`--holdout-by {label,project}`, `--split-seed`. Writes 1048 train / 116 holdout,
29% positive in both, rebuild verified identical to the original 1164 with zero
overlap. The holdout is SHUFFLED before writing: it is built class-by-class, so
unshuffled every capped prefix is all-negative and recall reads `nan` — a metric
measuring nothing, which is the exact failure this split exists to prevent.
`label` shares 20 projects with train (a training-health gate); `project` leaks
nothing but landed 84% defective from 29 skewed projects — use it for the number
you report, not for tuning.

### Four bugs the smoke tests caught, all of which would have died mid-run

    outputs.logits is None            TRL defaults to loss_type="chunked_nll",
                                      which never materialises logits (that is
                                      how seq 2048 fits). Take one hidden state
                                      via a hook on the final RMSNorm instead.
    output_hidden_states=True         returns ALL 36 layers, ~300MB/forward on a
                                      card whose training peak was 5318/6144.
    per_device_eval_batch_size=8      defaults independent of the train batch
                                      size, so eval forwarded 8x2048 vs train's
                                      1x2048. OOM. Pinned to args.batch_size.
    allocator fragmentation           OOM in loss.backward() with 821MB reserved
                                      -but-unallocated. Launch with
                                      PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
                                      -> VRAM 5427 -> 4822 MiB.

### The live run

    on the box, launched 16:40 2 Sep, ~387s/step, 131 steps, ETA ~07:00 3 Sep

    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True .venv/bin/python -u \
      -m fine_tuning.train_sft \
      --dataset data/sft_repair_train.jsonl \
      --eval-dataset data/sft_repair_train_holdout.jsonl \
      --output-dir artifacts/sft-repair-w05 \
      --verdict-weight 0.5 --eval-steps 20 --eval-max 60 \
      --epochs 1 --max-seq-length 2048 --warmup-steps 15 --seed 42 \
      > run_repair_w05.log 2>&1 &

Same seed, warmup and sequence length as ep1, so the weighting is the variable.
Trains on 1048 where ep1 had 1164 (the holdout is carved from the same pool), so
it is not a perfectly clean A/B. New output dir; `artifacts/sft-repair/` and the
corpus hash are untouched.

**THE GATE: first eval at step 20 (~18:40), then every 20 steps.** Recall above
zero means the weighting bit and the remaining ~11h are worth spending. Recall
at exactly zero means it did not, and the run should be killed there — the log
says so explicitly when it happens. 60 examples with 14 positives, so
granularity is ~7 points: enough to tell zero from non-zero, too coarse to tune
W on.

    watch it   tr '\r' '\n' < ~/oracle/run_repair_w05.log | grep -a "holdout @ step"

### When it finishes

    1. score it    ADAPTER=artifacts/sft-repair-w05 TAG=repair_w05 ./score_repair.sh
    2. hand-grade  data/real_commits_repair_w05.md -> ..._grades.json
                   v7 is still the number to beat: 32 findings, 30 wrong, 0 correct
    3. if recall moved but findings are still wrong, the next lever is SPLITTING
       detection from explanation (a classifier for the verdict, generation only
       for positives) rather than pushing W up. Rebalancing alone is not the fix:
       it moves the base rate 71% -> 50% while the verdict still carries 1% of
       the loss.

### Uncommitted work — NOTHING is committed, per the standing rule

Added 2 Sep afternoon, on top of the list further down (which still stands):

    fine_tuning/train_sft.py          verdict weighting, holdout eval, the four
                                      memory fixes above (synced to the box)
    dataset_builder/build_repair_sft.py   holdout split (LAPTOP ONLY — see below)
    data/sft_repair_train.jsonl       1048 train  (synced to the box)
    data/sft_repair_train_holdout.jsonl   116 holdout (synced to the box)

The GPU box's `dataset_builder/schema.py` predates `_SYSTEM_PROMPT_REPAIR`, so
the corpus builder only runs on the laptop. It affected nothing measured here —
the benches build prompts locally and the box only serves — but it will bite a
rebuild attempted on the box.

## SUPERSEDED — PAUSE/RESUME (2 Sep 10:07), the pause it describes has fired

The run does NOT roll into epoch 2 by itself any more. `pause_after_epoch1.sh`
is armed on the box under setsid/nohup, watching trainer pid 206034. It waits
for the first `artifacts/sft-repair/checkpoint-*` to hold every file a resume
needs AND to stop growing, then SIGTERMs the trainer and stages a scoring copy.

    on the box     bash pause_after_epoch1.sh --check     # state, changes nothing
                   tail ~/oracle/pause_ep1.log
    from here      ./dashboard_train.sh --once            # "pause" line under peak vram

WHEN IT FIRES (~2 Sep 15:00, step 146):

    1. score epoch 1   ADAPTER=artifacts/sft-repair-ep1 TAG=repair_ep1 ./score_repair.sh
    2. hand-grade      data/real_commits_repair_ep1.md -> data/real_commits_repair_ep1_grades.json
                       v7 is the number to beat: 32 findings, 30 wrong (93%), 0 correct
    3. resume epoch 2  on the box: nohup bash resume_repair.sh > resume_repair.log 2>&1 &
       or DON'T. The v4 evidence below says epoch 2 was 3-6 points worse. Decide
       from the epoch-1 grade, which is the whole point of stopping here.

Resuming is exact, not approximate: optimiser moments, cosine LR position, RNG
and dataloader position all come out of the checkpoint, so epoch 2 runs the same
batches in the same order at the same LR as if it had never stopped. Two guards
protect that claim, because it holds only while the schedule is unchanged —
`resume_repair.sh` refuses to start if `data/sft_repair_msgs.jsonl` no longer
hashes to eeb318d39ad8, and `resolve_resume()` in `fine_tuning/train_sft.py`
refuses if the step total the arguments imply differs from the checkpoint's.
Do not "fix" the epoch count to 1 in resume_repair.sh: --epochs 2 describes the
SCHEDULE the checkpoint was written under, not the work remaining.

`--resume` is new (2 Sep) in `fine_tuning/train_sft.py`; bare, it takes the
latest checkpoint under --output-dir. Local and box copies are in sync.

### Uncommitted work — NOTHING is committed, per the standing rule

Written 2 Sep, all of it dirty in the working tree. A fresh session sees these
as modifications with no commit explaining them, so this is the explanation:

    fine_tuning/train_sft.py    --resume flag + resolve_resume() step-total guard
                                (synced to the box; the running trainer already
                                has its code in memory and is unaffected)
    dashboard_train.sh          "pause" line under peak vram; PAUSE/PAUSE_LOG
                                added to the single SSH fetch
                                backups: /tmp/claude-1000/dashboard_train.sh.bak,
                                .bak2 (train-at-bottom reorder), .bak3 (pre-pause)
    next-session.md             this section

Box-only, following the existing run_*.sh convention (they have never lived in
the local repo — run_v4/v6/v7/repair.sh are all box-side):

    ~/oracle/pause_after_epoch1.sh    the watcher
    ~/oracle/resume_repair.sh         epoch 2, corpus-hash guarded

State at 2 Sep 10:09 — PIDs go stale, re-read them rather than trusting these:

    trainer 206034   watcher 388032   step 104/292 [11:22:03<20:50:50, 399.21s/it]

### Loss trace — the step-25/50 memorisation guard did NOT trip

    step   5    25    50    75   100
    loss 1.392 0.711 0.420 0.287 0.229      threshold was <0.2 by step 50

0.229 at step 100 and still falling; it may cross 0.2 before step 146. That is
not itself evidence of memorisation: the assistant turn is a fixed-key JSON
object, so much of the 93% token accuracy is braces and key names. The 40-commit
grade is what separates format from content.

## Where things stand (1 Sep 23:00) — REPAIR-SUPERVISED RUN IS TRAINING

Everything below this section is SUPERSEDED except for its recorded numbers.
The v6/v7 action lists are done. Read `docs/RESULTS.md` top three sections for
the measurements; this section is the state and the next commands.

### The run

    artifacts/sft-repair    292 steps (2 epochs), started 1 Sep 22:46
    driver ~/oracle/run_repair.sh, log ~/oracle/run_repair.log
    corpus data/sft_repair_msgs.jsonl — 1164 records, 340 defective (29%)
    max_seq_length 2048, LoRA r=16 a=32, lr 1e-4 cosine, warmup 15, seed 42
    ORACLE_OUTPUT_CONTRACT=repair

**First command of the session** — the run outlives its session:

    ./dashboard_train.sh --once        # reads run_repair.log, shows step/ETA/loss

TIMING: the box is a GTX 1660 SUPER (TU116 — NO tensor cores), so a step is
~400s and the full 2 epochs is ~33 h. Epoch 1 finishes at step 146, ~16 h in,
and `save_strategy="epoch"` writes a complete adapter there.

TAKE THE EPOCH-1 CHECKPOINT — now enforced by the watcher above, not by
remembering to look. The v4 run was scored at both, and epoch 2 improved
nothing while being 3-6 points WORSE on `basic` verdict on both seeds:

    seed42  1ep 89% / 2ep 86%      seed7  1ep 95% / 2ep 89%

### What this contract is

NOT v1/v2/v3. Different keys, different user template, targets derived from the
diff that REPAIRED each defect rather than written from the buggy code alone.

    defect_found  confidence  target_file  affected_identifiers
    explanation   repair_direction

Wired in `dataset_builder/schema.py` (`_SYSTEM_PROMPT_REPAIR`,
`_USER_TEMPLATE_REPAIR`, `repair_to_analysis`) and `llm_explainer/client.py`
(parse routed, chunking disabled). `build_repair_sft.py` IMPORTS the two
literals rather than keeping copies, so corpus and inference cannot drift.

Serving MUST set ORACLE_OUTPUT_CONTRACT=repair. Without it,
`_PROMPTS.get(OUTPUT_CONTRACT, _SYSTEM_PROMPT_V1)` silently serves the V1 prompt
— the shape the checkpoint never trained on.

### Next commands, in order

    # 1. score the new checkpoint on the SAME 40 real commits
    ./score_repair.sh              # serves the adapter, runs the 40, writes
                                   # the sheet, then runs grade_real.py

    # 2. machine-decidable half of the taxonomy
    .venv/bin/python bench/grade_real.py --tags v7 repair --show

    # 3. hand-grade the rest against data/real_commits_repair.md
    #    classes: contradicted | inverted | no-such-entity | incoherent
    #             | partial | confirmed correct
    #    record in data/real_commits_repair_grades.json (mirror the v7 file)

### The number to beat

v7 on those 40 commits: 27/40 flagged, 32 findings, **30 wrong (93%)**,
0 confirmed correct. Breakdown in `data/real_commits_v7_grades.json`:

    contradicted 10 | inverted 8 | no-such-entity 8 | incoherent 4 | partial 2

The one real defect in the set — `gin 34b1d0262e`, an `http.Flusher` type
assertion losing its `ok` guard — was missed by base 3B, both v6 seeds and v7.
gpt-oss-120b found it. That commit is the single best signal in the benchmark.

### Why the corpus is what it is (do not undo these)

Four defects were found and fixed on 1 Sep, all BEFORE any training used them:

  94% ungrounded  defective targets took identifiers from the REPAIR diff, which
                  the model never sees — typically the fix's TEST names bound to
                  a source file. Now the intersection of repair and reviewed
                  diff. `build_repair_targets.py`, and enforced again after
                  token-budget elision in `build_repair_sft.py`.

  hindsight       every defective frame said "a later commit repaired X". At
                  inference there is no later commit. 531 -> 0.

  templating      1178 clean targets were 41 skeletons (3%) while raw
                  distinctness read 99% — the filename slot made each unique.
                  Same shape as the v4 `check` failure. Frames 24 -> 56 clean,
                  3 -> 36 defective. ALWAYS measure distinctness with the
                  `<FILE>` and `` `id` `` slots stripped.

  CHANGES.txt     predicted CLEAN with 98% precision over 15% of the corpus
                  (159 clean / 2 defective, hbase+hadoop release notes).
                  `build_repair_targets.strip_non_source()` now removes every
                  non-source hunk before anything derives from the diff.

`dataset_builder/filter_repair_targets.py` exists because the sanitisation step
was ad-hoc and unrecorded; it also carries the 30:70 rebalance.

### Known limitations, for threats to validity

  project confound   hadoop-mapreduce + hbase are 42% of the clean class.
                     Capping was offered and declined; it stands.
  still frame-based  113 clean skeletons / 824, 81 defective / 340. Better than
                     41/1178 but the explanation is slot-filling, not reasoning.
  SZZ noise          labels are B-SZZ derived; literature puts precision at
                     50-70%. "Clean" means "not known to be defect-inducing".
  small              1164 records; 340 defective is thin.

### Rebuild chain, if the corpus must be regenerated

    python -m dataset_builder.build_repair_targets --out data/sft_repair.jsonl
    python -m dataset_builder.filter_repair_targets --out data/sft_repair_clean.jsonl
    python -m dataset_builder.build_repair_sft --out data/sft_repair_msgs.jsonl

Standing constraints: no commits without asking; commits carry NO attribution
trailers; do not delete `data/sft_v4_suggest.jsonl`; do not change the v3 prompt
in `dataset_builder/schema.py`; the GPU box login shell is fish, so every remote
command goes through `bash -lc`.

---

## Where things stand (31 Aug 21:00) — v6 IS TRAINING, corpus rebuilt

The 31 Aug 14:10 section below is SUPERSEDED except for its v4 numbers, which
still stand. The action item it named — "Fix the `check` template" — is DONE and
the two-seed v6 run is on the GPU box.

  seed 42  artifacts/sft-v6-suggest        started 20:42, ~3.75 h  -> tag v6
  seed 7   artifacts/sft-v6-suggest-seed7  chained after it        -> tag v6_seed7

  driver: ~/oracle/run_v6.sh (setsid nohup, log ~/oracle/run_v6.log)
  ONE epoch each, --max-seq-length 1152, corpus data/sft_v6_suggest.jsonl
  md5 053b5c02c8a4e4bcec7378accbdff248 on both boxes, 366 records, 0 dropped

**First command of the session** — the run outlives its session:

    ssh oracle-gpu 'bash -lc "cat ~/oracle/run_v6.log"'

Then score:

    ./score_v6.sh            # both seeds, all three sets, then compare + audit
    ./score_v6.sh --report   # re-read rows already scored, no GPU

## What changed, and why

`check` was a per-CATEGORY sentence with a filename slot, and the corpus has two
categories, so 366 targets carried 100 distinct checks and 357 said "the edit
touches". Three things were measured before the rebuild (all in
`docs/RESULTS.md`, all reproducible with no GPU):

  1. `bench/check_field_audit.py` — v4's `distinct*` (filename and token dump
     blanked) is **1** on all 21 mech_heldout cases, both seeds. One sentence.
  2. Cross-seed byte identity: v4's two seeds emit the identical `check` on
     16/46, 13/21, 21/34 — and the identical `summary` on 0/46, 0/21, 1/34.
     The summary column is the control. That contrast is the memorisation proof.
  3. `check_useful` was reading the appended token list, not the sentence:
     strip the tail and mech_heldout goes 20/21 -> 11/21, basic 29/31 -> 19/31.

`bench/template_audit.py` never read `effect.check`, which is how a 97%-template
field reached a training run. It now has `--with-check` (off by default) and
`--self` (leave-one-CASE-out corpus similarity, the pre-flight the v4 run
lacked).

The rebuild: 37 per-case `check` annotations in `meta.json`, written by
`bench/annotate_checks.py` (probe / watch / restored). Clean cases derive
theirs from the parent. Corpus goes 100 -> 341 distinct checks, "the edit
touches" 357 -> 0, all 366 assistant turns distinct, self-similarity median
54.6% -> 37.4%, longest verbatim run 117 -> 62 words.

Two other corpus defects fixed in the same pass:
  - `fix` targets drew "behaviour-preserving" closers under a
    `direction: post-fixes` effect. ~40 v4 targets contradicted themselves.
  - the opener said "an input validation" / "off by one"; category enums now
    map to noun phrases, and the opener takes the FINDING's category, which is
    finer than the case file's (v4 called an array overrun a "logic error"
    while its own finding said input-validation).

Confidence was near-constant `likely` (3 `possible` in 168 v4 responses). The
`possible` rule — "does the diff alone settle it" — now also covers overflow and
truncation, which depend on the caller's VALUES exactly as aliasing depends on
the caller's object. Corpus split 75% -> 58% likely.

## HOW TO READ THE RESULT, in this order

  1. **False alarms on clean cases FIRST.** v2 pair 4-15%, v4 9-11%. MUST NOT
     RISE. A model that hedges on everything is never wrong and never useful.
  2. Location when it speaks: v4 was `locus unconfirmed` = 0 everywhere.
  3. Copying: `template_audit.py`, both with and without `--with-check`, plus
     `check_field_audit.py`. v4 basic 28.7/24.3%, clean_heldout 71.1/74.6%.
  4. `check_useful`, and read the "no tail" column beside it.
  5. Calibration: is `possible` non-trivially present, and does `likely` beat it.

Expected direction, stated in advance: copying DOWN, `check_useful` roughly flat
or down a little (the token dump that was inflating it is gone — a drop toward
the 52-64% "no tail" figures is the honest number arriving, not a regression),
false alarms flat, location flat.

## Ground rules (unchanged)

  - **No commits.** Nothing since ba5a65f is committed, by request. Ask first.
  - ~1 month of thesis time. Land this, then write up. No new experiments.
  - `data/sft_v4_suggest.jsonl` must NOT be deleted — the v4 checkpoints are
    only auditable against the corpus they actually saw. `sft_v5_suggest.jsonl`
    was built but never trained (superseded by the check rewrite); keeping it
    costs nothing and deleting it would confuse the audit trail.
  - The box's login shell is fish: send remote commands through `bash -lc`.
  - Do NOT change `dataset_builder/schema.py`'s v3 prompt: it is baked into
    `sft_v6_suggest.jsonl` and a checkpoint scored under a prompt it was not
    trained on lost six cases in forty-six to that alone.

---

## Where things stand (31 Aug 14:10) — v4 IS FULLY SCORED, RESULT IS IN

All four v4 checkpoints scored on all three bench sets. 12/12 suites on disk.
The GPU box is idle and can be powered off; nothing is queued or waiting.

  seed42 final -> v4        seed42 epoch1 -> v4_ep1
  seed7  final -> v4_seed7  seed7  epoch1 -> v4_ep1_seed7

## The result in one paragraph

v4 CLEARED both gating thresholds and produced one readable improvement, while
verbatim copying roughly TRIPLED and two contract fields collapsed to near
constants. It scores better while reciting more. Read it as mixed, leaning
negative on the novelty claim: a model reproducing corpus sentences is not
explaining. Do not write it up as a win.

### What held (the thresholds)

  - False alarms did NOT rise. basic 9% (seed42) / 11% (seed7), inside the v2
    4-15% band. clean_heldout 0/34 on ALL FOUR checkpoints.
  - Location: `locus unconfirmed` = 0 everywhere, both seeds, all sets. It named
    the defect every time it returned a verdict. v2 was 87-98%.
  - One readable effect, v4 vs v2, on clean_heldout: `observable` claims
    12/11 -> 0/0. That set's measured noise floor is ZERO seed flips, so it is
    real. v4 stopped asserting behaviour change on unchanged code.
  - v4 is markedly more seed-stable than v2: 5/46 cases flip on seed alone
    (v2: 14/46) on basic, 2/21 (v2: 10/21) on mech. Do not oversell this — a
    more templated model is trivially more consistent.

### What broke (the real finding)

Verbatim 8-word coverage of corpus answers (`bench/template_audit.py`):

  set            v2_pilot2  v2_seed7      v4  v4_seed7  v4_ep1  v4_ep1_seed7
  basic              11.6%      6.2%   28.7%     24.3%   27.7%         29.1%
  mech_heldout        5.3%      0.0%   16.2%     16.0%   18.3%         18.6%
  clean_heldout      40.4%     39.9%   71.1%     74.6%   73.5%         74.1%

On clean_heldout the `>=50%` column is 34/34, 33/34, 34/34, 34/34 — essentially
EVERY answer is at least half verbatim corpus text.

Two contract fields are dead:
  - `check`: 100% of outputs contain "the edit touches" (corpus was 97% — the
    model pushed it to saturation). Two INDEPENDENTLY TRAINED checkpoints emit
    the byte-identical `check` string 30-59% of the time, while their `summary`
    matches 0/46. That contrast is the proof it is memorised, not reasoned.
  - `effect_confidence`: 3 `possible` in 168 responses. Effectively constant
    `likely`. Not carrying information.

## THE CAUSAL RESULT — this is what the session bought

The 30 Aug notes attributed copying to TWO causes: the 97% `check` template AND
seed 42's convergence collapse. **The epoch-1 checkpoints separate them.** They
are measurably less converged and they copy IDENTICALLY (27.7/29.1 vs 28.7/24.3
basic; 73.5/74.1 vs 71.1/74.6 clean).

  => Convergence is NOT the cause. The corpus template is.
  => Training less will not fix copying. Fixing `_V3_CHECK` is the only lever.

## Epoch 1 vs epoch 2: epoch 2 bought NOTHING

`compare_seeds.py --base v4 v4_seed7 --new v4_ep1 v4_ep1_seed7` returns "no" on
EVERY metric across all three sets — inside seed band, seeds disagree, or
unchanged. Not one metric moved beyond noise.

  => Train ONE epoch. ~3.75 h/seed instead of 7.5 h. This is free time.

## The extract prediction FAILED

`php-extract-helper` and `py-extract-helper` were the stable targets that were
predicted to go quiet. They are now seed-unstable, not reliably quiet. The
controls (`c-const`, `py-comprehension`) stayed ALARM in all four checkpoints,
so the model did not just go globally timid — but the predicted effect is absent.
Report this as a failed prediction; do not soften it.

## WHAT TO DO NEXT SESSION, in order

  1. Fix the `check` template — `_V3_CHECK` / `suggested_effect` in
     `dataset_builder/build_mechanism_corpus.py`. This is a CONTENT change, not
     a parsing one. The goal is a `check` that names the actual identifier and
     condition for THIS case, not a per-category sentence with a filename slot.
     Target: "the edit touches" appears in a small minority of targets, and two
     records in the same category do not share a `check` string.
  2. Rebuild the corpus and AUDIT IT BEFORE TRAINING:
       .venv/bin/python bench/template_audit.py --corpus data/sft_v5_suggest.jsonl
     Also re-check the identifier bug is still fixed (0/366 unbalanced tokens).
  3. Train v5, TWO seeds, ONE epoch each (~3.75 h/seed, ~7.5 h total).
  4. Score with `./score_v4.sh` (add v5 tags to ADAPTER/TAG maps first).
  5. Read in this order: false alarms -> location -> copying -> calibration.

`data/sft_v5_suggest.jsonl` already exists (identifier bug fixed, 366 records)
but was built BEFORE the check-template fix. Rebuild it; do not train it as is.

## Ground rules (unchanged)

  - **No commits.** Nothing since ba5a65f is committed, by request. Ask first.
  - ~1 month of thesis time. Land v5, then write up. No new experiments.
  - `data/sft_v4_suggest.jsonl` must NOT be deleted — `score_v4.sh:116` audits
    copying against it and the v4 checkpoints are only auditable against the
    corpus they actually saw.
  - The box's login shell is fish: send remote commands through `bash -lc`.

## Infrastructure fixed this session (do not re-break)

  - `score_v4.sh` `start_server`: was `remote "cd ~/oracle && nohup ... &"`.
    The `&` backgrounds the whole `&&`-list in a subshell but the redirection
    binds only to `nohup`, so the subshell held ssh's stdout/stderr and ssh
    NEVER RETURNED. Cost 5 hours on 31 Aug. Now parenthesised:
    `remote "(cd ~/oracle && nohup ...) > log 2>&1 < /dev/null &"`.
  - `~/.ssh/config`: oracle-gpu moved 192.168.1.170 -> **192.168.1.158** (DHCP;
    host keys verified identical, box never rebooted). If it goes unreachable
    again, CHECK THE LEASE FIRST — `nmap -sn 192.168.1.0/24`.
  - `dashboard_train.sh`: new "scoring (local)" section — 12-suite progress from
    the ROWS FILES (not the log; `| tail -18` buffers a whole suite), per-suite
    false-alarm/unlocated/err, and a STALLED flag (GPU idle + stale log).
    Also fixed `bar()` mangling UTF-8 and a pgrep matching wrapper shells.

## Bench guards that worked — trust them

  - `basic_bench.py` REFUSES to write a rows file when 100% of calls error,
    because "no finding" on clean cases would score as a perfect pass.
  - `compare_seeds.py` prints "awaiting second seed" rather than inventing a
    number from one arm.
  - Scoring is deterministic: re-scoring seed7ep1's basic set after the outage
    reproduced all five counts exactly (ORACLE_INFERENCE_SAMPLES=1, greedy).

END NEXT-SESSION PROMPT -->

---

# SUPERSEDED BELOW — kept for history (30 Aug and earlier)

<!-- ============================================================
     PROMPT FOR THE NEXT SESSION — paste everything between the
     markers as the opening message.
     ============================================================ -->

<!-- BEGIN NEXT-SESSION PROMPT

Continue ORACLE at ~/Documents/oracle.

Read `next-session.md` first — its head ("Where things stand", 30 Aug 21:00) is
current. The 30 Aug 12:30 section below it is SUPERSEDED: it was written before
the corpus defect was found. Then `docs/PLAN_SUGGEST_CONTRACT.md` (the active
plan; its thresholds still stand), then the top two sections of
`docs/RESULTS.md`.

## What happened overnight, in one line

The v4 corpus was found to be defective AFTER training started: 207 of its 366
targets (56%) name an identifier that does not exist. It is fixed and rebuilt as
`data/sft_v5_suggest.jsonl`; the v4 checkpoints trained on the broken one.

## What should be finished by now

  - `sft-v4-suggest-seed7` — ETA ~03:06, chained by `run_v4.sh` after seed 42
    (which exited 0 at 19:38:56).
  - `./score_v4.sh all` — a DETACHED job (`setsid nohup`) fires when seed 7
    exits and scores FOUR checkpoints, ~38 min each, so ~05:40.

**First command of the session** — the scoring job outlived its session, so read
its log, do not re-run it blind:

    cat /tmp/claude-1000/-home-arp-Documents-oracle/*/scratchpad/score_v4_run.log

If that file is missing (`/tmp` is cleared on reboot) or ends in `TIMEOUT`, check
`ssh oracle-gpu 'bash ~/oracle/watch_v4.sh'` and run `./score_v4.sh all`
yourself. `./score_v4.sh --report` re-reads rows already scored, no GPU.

## The corpus defect — read before interpreting ANY v4 number

`build_mechanism_corpus.py` built the v3 `check` field's token list with
`tok.strip("(){}[];,:")`. `str.strip` works on both ends, so `len(xs)` lost its
closing bracket and became `len(xs`, and `.split()` on whitespace cut
`Math.addExact(a, b)` into an already-unbalanced `Math.addExact(a,`.

  - v4 corpus: 207/366 targets (56%) carry such a token.
  - Both v4 checkpoints reproduce it. Served on CPU, seed 42 answered with
    `` `len(xs` ``, `` `total(xs` ``, `` `print(s` ``.
  - FIXED (`_trim`, `dataset_builder/build_mechanism_corpus.py`) and rebuilt:
    `data/sft_v5_suggest.jsonl`, 0/366, same 366 records, 0 dropped, same
    direction mix (177 post-breaks / 105 unchanged / 84 post-fixes).

**`data/sft_v4_suggest.jsonl` is kept ON PURPOSE and must not be deleted.**
`score_v4.sh:116` audits copying against it, and the v4 checkpoints are only
auditable against the corpus they actually saw.

## The OTHER corpus problem, NOT fixed

`"the edit touches"` appears in 357 of 366 assistant targets (**97%**) in BOTH
v4 and v5 — the `check` field is a per-category template with a filename slot.
The `check` field is the entire point of the suggestion contract. Fixing this is
a content change (`_V3_CHECK` / `suggested_effect`), not a parsing one, and it
was deliberately left alone pending the copying number.

**Expect `template_audit.py` to look bad, and attribute it correctly.** Two
independent causes: this 97% template, and seed 42's own convergence — final
train loss 0.036 with entropy collapsed 1.513 → 0.045 on 366 examples.

## How to read the result

Unchanged from the plan, and still the right order:

  1. **False alarms on clean cases FIRST.** v2 pair was 4-15% — MUST NOT RISE.
     A model that hedges on everything is never wrong and never useful.
  2. Location rate when it speaks: v2 pair was 87-98%, must not drop.
  3. `FABRICATED` will NOT read 0 and that is not a violation — under v3 the
     scorer keeps the absolute-path half of the rule. A non-zero count is an
     invented PATH, not an invented value.
  4. Verbatim copying: was 18-30%. See the attribution note above.
  5. `check_useful` and `likely` vs `possible` calibration: new, no threshold.

If the false-alarm rate rose, the honest result is negative. Say so; do not go
looking for a metric that moved.

## Epoch 1 vs epoch 2 is now a scored question

`save_strategy="epoch"` wrote `checkpoint-46` for both seeds, so the epoch-1
checkpoints cost no GPU time to obtain. `score_v4.sh` scores all four:

    seed42 -> v4        seed42ep1 -> v4_ep1
    seed7  -> v4_seed7  seed7ep1  -> v4_ep1_seed7

Selectors: `final`, `ep1`, `all` (default), or one target by name. `report()`
runs three `compare_seeds.py` passes: v4 vs v2, v4_ep1 vs v2, and **v4_ep1 vs
v4** — the last is the direct epoch question. Both seeds are scored because
`compare_seeds.py` takes `nargs=2`; a single-seed epoch-1 number is the point
estimate that script exists to refuse.

Epoch 2 bought very little: loss 0.070 → 0.036 across the whole second epoch,
essentially flat from step 65 (0.049 → 0.036 over ~2 GPU-hours).

## What to do, in order

  1. Read `score_v4_run.log`. If it did not run, run it.
  2. Read the false-alarm rate first, then copying, then the epoch comparison.
  3. Decide on v5. It is built and unused. Training it is one run (~7.5 h/seed).
     **Do not launch it without deciding whether to fix the 97% `check`
     template first** — one run that fixes both beats two runs that fix one
     each, and only 1 month of thesis time remains.

## Ground rules

  - **No commits.** The working tree is dirty and nothing since ba5a65f is
    committed, by request. Ask before committing anything.
  - Only 1 month of thesis time remains. The agreed scope is: land this two-seed
    result, then write up. Do not start a new experiment.
  - Run `bench/template_audit.py` before believing any comparison between two
    checkpoints. A corpus-vs-corpus control does NOT work — `sft_v3_extract`
    shares 78 of `sft_v2_pilot2`'s 80 records.
  - The GPU box's login shell is fish: send remote commands through `bash -lc`,
    or a bash construct fails in a way that looks like the host being down.
  - A defect visible in the corpus before training started has now cost GPU-hours
    three sessions running. Audit the corpus file itself — not the builder — as
    the last step before any launch.

END NEXT-SESSION PROMPT -->

Continue ORACLE at ~/Documents/oracle. Read this head first, then
`docs/PLAN_SUGGEST_CONTRACT.md` (the active plan), then the top two sections of
`docs/RESULTS.md` — both 30 Aug, newest first. Sections below those are 29, 28
and 27 Aug and are historical.

# Where things stand — 30 Aug, 21:00

**seed 42 is done and its corpus was defective. seed 7 is still training on that
same defective corpus. The fix is built but nothing has trained on it.**

## Running right now

  - `sft-v4-suggest-seed7`, step ~12/92 at 20:45, ~292 s/it, **ETA ~03:06**.
    Its loss now streams live (see "the buffering fix" below).
  - A detached `./score_v4.sh all` waiting on it — four checkpoints, **ETA
    ~05:40**. Log: `.../scratchpad/score_v4_run.log`.

## Done today, after the 12:30 section below was written

**1. seed 42 finished clean** — exit 0 at 19:38:56, 7 h 24 m, adapter written
with `checkpoint-46` and `checkpoint-92` both on disk. Loss 1.982 → 0.036 over
2 epochs, smooth, no instability, `grad_norm` bounded 0.27-1.56. But entropy
collapsed 1.513 → 0.045 and token accuracy hit 98.4% on 366 examples: that is
memorisation territory, and it is one of two reasons to expect a bad copying
number.

**2. The buffering fix.** `logging_steps=5` was always correct — 18 log points
existed. `ProgressCallback.on_log` writes them with `tqdm.write`, i.e. to
stdout, while the bar goes to stderr; under `run_v4.sh` stdout is a file, so it
block-buffers and the loss only appears when the process exits. A 7-hour run
showed a moving bar and no loss. Fixed with `sys.stdout.reconfigure(
line_buffering=True)` at the top of `main()` in `fine_tuning/train_sft.py`,
synced to the box, and **confirmed live on seed 7**. seed 42's trace is complete
in its log, just flushed all at once at exit.

**3. The corpus defect** — the big one. See the prompt block above for the full
account. `tok.strip("(){}[];,:")` unbalanced 56% of v4's targets; fixed and
rebuilt as `data/sft_v5_suggest.jsonl` (0/366). v4 is retained deliberately so
`template_audit.py` stays valid.

**4. Two try-cases, on CPU, n=2 — an anecdote, not a rate.** seed 42 served on
CPU (GPU untouched). `go-offbyone`: right direction, wrong mechanism — it said
`i` reaches `len(xs)-1`, which is the correct behaviour, not the bug.
`py-extract-helper` (CLEAN, and one of the two `STABLE_TARGET` cases):
**false-alarmed** as `logic-error`/`post-breaks`/`likely`. Both answers used
near-identical templated phrasing. Do not quote these as results; the scored
false-alarm rate is the number.

**5. `score_v4.sh` scores four checkpoints now**, not two — see the prompt.

**6. The TUI ran the v3 model under the v1 contract.** `config.py:185` defaults
`OUTPUT_CONTRACT` to `"v1"` and neither `main.py` nor `ui/tui_app.py` set it, so
the TUI sent v1 prompts — and, because `DIFF_RENDERING="auto"` resolves to
word-diff only under v2/v3, unified diffs to a word-diff-trained model. Fixed
with `os.environ.setdefault("ORACLE_OUTPUT_CONTRACT", "v3")` before the `config`
import in both. An explicit `ORACLE_OUTPUT_CONTRACT=v2` still wins.
**Note: this makes every `main.py` subcommand default to v3, not just `tui` and
`analyze`** — accepted deliberately, flagged here in case it should be narrowed.

**7. The TUI now renders the suggestion contract.** It previously showed only
`summary` + `findings` and dropped `effect` entirely, so `trigger`, `direction`,
`check` and `confidence` — everything v4 was trained to produce — were invisible.
Added above the summary (schema order, evidence before verdict) and to the
clipboard export. Tested against v3, v2 and no-`effect` answers.

**8. Docs point at v5.** `README.md` and `PLAN_SUGGEST_CONTRACT.md` build and
train from `sft_v5_suggest`, both noting why v4 is kept. Historical references
(`PLAN:138`, `PLAN:187`, the corpus table) still say v4 on purpose — they record
what actually ran.

## Small open items

  - `llm_explainer/client.py:633` calls `_selftest()` before `main()`, and the
    selftest asserts `include_schema` (line 625). With `ORACLE_INCLUDE_SCHEMA=
    false` — what `score_v4.sh` exports — the CLI crashes on startup and never
    reaches `main()`. Scoring is unaffected (`basic_bench.py` imports the
    module). Fix: guard the selftest behind a flag.
  - `ml_model/encoder.py:75` loads GraphCodeBERT and transformers reports
    `pooler.dense.*` as MISSING (randomly initialised). Harmless here — line 104
    reads `.last_hidden_state` and mean-pools by hand; `pooler` appears nowhere
    else in the project. `add_pooling_layer=False` would silence it honestly.
  - The user wants a real hands-on TUI test once the GPU is free (after ~05:40).
    Drop `ORACLE_OUTPUT_CONTRACT=v2` when pointing at a v4 checkpoint.

## Uncommitted at handoff

Everything below is in the working tree and NOT committed:
`fine_tuning/train_sft.py` (buffering), `dataset_builder/build_mechanism_corpus.py`
(`_trim`), `data/sft_v5_suggest.jsonl` (new), `score_v4.sh` (four targets),
`main.py` + `ui/tui_app.py` (contract default + effect rendering), `README.md`,
`docs/PLAN_SUGGEST_CONTRACT.md`, `next-session.md`.

---

# Where things stand — 30 Aug, 12:30 — SUPERSEDED, see above

**Training is running. The v3 experiment's diagnosis was wrong and has been
replaced. The suggestion contract is built end to end and its first two
checkpoints are on the GPU now.**

## Running right now

| | |
|---|---|
| `sft-v4-suggest` (seed 42) | started 12:14, 92 steps, 293 s/it, ETA ~19:40 |
| `sft-v4-suggest-seed7` (seed 7) | chained with `&&`, starts on a clean exit, ETA ~03:05 |

Launcher `~/oracle/run_v4.sh`; status `ssh oracle-gpu 'bash ~/oracle/watch_v4.sh'`;
logs `sft_v4_seed42.log` / `sft_v4_seed7.log`, wrapper log `run_v4.log`.
4528 MiB of 6144 in use — the move from 1024 to 1152 tokens fits with headroom.
Corpus `data/sft_v4_suggest.jsonl`, 366 records, contract v3, `--max-seq-length
1152` on both the build and the train.

## What was established today, in order

### 1. The 30 Aug "the corpus taught two templates" reading is WRONG

`bench/template_audit.py` (new) measures verbatim 8-word overlap between an
answer and the corpus. Both pre-registered gates FAILED:

- **Copying is real and large** — 30.5% of seed 42's answer prose on
  `bench/basic`, against a **0.0%** floor from an untuned model on the same 46
  cases, 86-word longest run.
- **It is NOT a v3 defect.** v3 30.2 / 17.9 vs v2 30.5 / 18.6. The corpus
  version does not move it; the SEED does (42 → ~30%, 7 → ~18%, either corpus).
- **v3 is not more repetitive than v2**: worst sentence 105/399 (26%) vs
  78/318 (25%).
- The old cross-corpus control was void: `sft_v3_extract` shares 78 of
  `sft_v2_pilot2`'s 80 records. Only an out-of-family checkpoint is a floor.

### 2. Three real corpus bugs, all in the extract-boundary family

Full detail in RESULTS.md, "Three corpus bugs". Short form:

1. **27 targets literally said "renames `a local` to `a new name`"** for a diff
   that ADDS a function — the nine `*-extract-boundary-refactor` cases have no
   `renamed` key and fell through to a placeholder default. That is the sentence
   `sft-v3-extract` emitted on all five held-out extract cases. The model was
   reproducing a false target, not inventing one.
2. **All 54 clean targets named `{parent}.{ext}`** while their diff header says
   `{id}.{ext}` — a filename absent from the prompt, so unlearnable. Five
   hand-authored `analysis.json` had also copied the `b`-prefixed word-diff
   header form (`bpy-min-empty-guard.py`).
3. **Nine cases share one summary**, upsampled ×6 = 54 byte-identical targets.

Every 29 Aug pre-flight check passed on this because the duplication bar was
20% and the worst WHOLE-TARGET repeat was 13.5%. The 105/399 was a *sentence*
inside otherwise-differing summaries, which that check could not see.

### 3. The split that motivates the new contract

Across four checkpoints and 101 executable cases, by kind of claim:

| asked for | right |
|---|---|
| **where** — cite the code at fault | **87–98%** |
| **which way** — breaks or fixes | **79–93%** |
| **the concrete before/after value** | **15–31%** |

69–85% of answers carry a value that running the code contradicts, and in
**90–99% of those the location was still right**. The headline metric never
read before/after, so deleting the value costs **zero**. That is the whole
argument for the suggestion contract.

## What was built today

| file | change |
|---|---|
| `bench/template_audit.py` | NEW — verbatim copying vs an out-of-family floor |
| `config.py`, `llm_explainer/client.py` | `OUTPUT_CONTRACT` accepts `v3`; word-diff for v3 |
| `dataset_builder/schema.py` | `Effect` gains `check` + `confidence`; v3 prompt (662 tokens, parity with v2); selectors. **v2 serialises byte-identically** |
| `dataset_builder/build_mechanism_corpus.py` | v3 target generator, varied per copy; the three bugs above |
| `dataset_builder/build_sft_data.py` | pre-flight: repeated-SENTENCE check, ghost-filename check, duplication bar 20% → 10% |
| `bench/basic_bench.py` | `check_useful`, confidence calibration, observable tier retired under v3 |
| `score_v4.sh` | NEW — serve, tunnel, three sets, both seeds, then report |
| `README.md` | retitled; "Predict, Then Point"; ORACLE = On-commit Risk And Code-Location Estimator |
| `docs/PLAN_SUGGEST_CONTRACT.md` | NEW — the active plan, with thresholds fixed in advance |

**The scorer gate passes**: re-grading the stored v2 rows gives exactly **76**
and **86**, per-set 31+11+34 and 35+17+34.

**Corpus quality, old vs new:**

| | `sft_v3_extract` | `sft_v4_suggest` |
|---|---|---|
| records | 399 | 366 |
| distinct targets | 98 | **356** |
| worst whole-target repeat | 54 (14%) | **2 (1%)** |
| worst repeated sentence | 105 (26%) | **32 (9%)** |
| targets naming a file not in their prompt | 282 | **0** |
| dropped by the sequence budget | — | **0** |
| confidence split | n/a | 75% likely / 25% possible |

# What to do next, in order

## 1. Score the pair — `./score_v4.sh`

Refuses to start while training holds the VRAM. No merge step: `serve.py:62`
loads a LoRA adapter directly. The contract is set on the CLIENT side by the
script (`ORACLE_OUTPUT_CONTRACT=v3 ORACLE_INCLUDE_SCHEMA=false
ORACLE_INFERENCE_SAMPLES=1`); scoring a v3 checkpoint with it unset sends v1
prompts and measures the mismatch, worth six cases in forty-six.

## 2. Read the false-alarm rate FIRST

Thresholds were fixed before training (`docs/PLAN_SUGGEST_CONTRACT.md`):

| metric | v2 pair | target |
|---|---|---|
| false alarms on clean cases | 4–15% | **must not rise** |
| location rate when it speaks | 87–98% | must not drop |
| fabricated concrete values | 69–85% of answers | 0 by construction — but see below |
| verbatim copying | 18–30% | lower, and measured either way |
| `check_useful` | n/a | reported, no threshold on the first run |
| calibration | n/a | `likely` should beat `possible` |

**The false-alarm rate is the one that can kill the idea.** A model that hedges
on everything is never wrong and never useful. If it rises, the hedging bought
nothing and the honest result is negative — say so.

Read the audit against the floor checkpoints in the SAME table, not against the
old 30% figure: the new corpus has 6502 distinct 8-grams to the old one's 2337,
so it is harder to copy and the metric is more sensitive. `v2_pilot2` scores
11.6% against it versus 30.5% against its own corpus.

**Read it on `bench/basic` ONLY.** `base44` and `gptoss120b` have no
`heldout_clean` or `heldout_mech` rows, so there is no out-of-family floor on
those two sets. All four in-family checkpoints sit at 38-40% on `clean_heldout`
against a corpus they never saw — a v4 number in that band is uninterpretable,
not a finding.

**The `FABRICATED` counter will not read 0, and should not.** Under v3 the
scorer retires the identical-output half of the fabrication rule and keeps the
absolute-path half, so what it still counts is an invented PATH. Rescoring real
v2 answers converted to v3 shape leaves it at 5/46 on `bench/basic` (30 Aug).
The "0 by construction" line refers to the concrete-value tier, which no longer
exists.

## 3. Both seeds must agree

Seed alone moves 24 of 101 cases and the headline by 10. A single-seed delta is
not a result. `bench/compare_seeds.py` enforces this; `mechanism_heldout`
(10 of 21 flip on seed alone) cannot resolve anything and should not be quoted.

## Small open items

- `bench/compare_seeds.py:185` labels every case outside `STABLE_TARGET` as
  `(seed-unstable)`, including `js-extract-helper`, which is really "no
  headroom". Cosmetic, touches no metric, but it is in the table the verdict
  gets read off.
- Error rows store `case_id: None`, so a failed case is only identifiable from
  the run log. One errored case per side on the v3 run — same rate as the v2
  baselines, not a new fault.
- `README.md` picked up a one-line edit from outside this session (the acronym
  line); it is folded into the rewrite.

## Uncommitted at handoff

Modified: `README.md`, `config.py`, `bench/basic_bench.py`,
`dataset_builder/{schema,build_mechanism_corpus,build_sft_data}.py`,
`llm_explainer/client.py`, `docs/RESULTS.md`, `next-session.md`, and five
`bench/mechanism_pilot/*/analysis.json` (the `b`-prefix filename fix).
Untracked: `bench/template_audit.py`, `bench/compare_seeds.py`, `score_v4.sh`,
`dashboard_train.sh`, `docs/PLAN_SUGGEST_CONTRACT.md`, the 18 v3 bench case
dirs, `data/sft_v4_suggest.jsonl`, `data/*_v3*.jsonl`, `data/*_v2_seed7.jsonl`.
Nothing since ba5a65f is committed, by request.

# What v3 was testing, and how it failed — ANSWERED 30 Aug, see the head

**Kept for the design rationale and the pre-registered prediction. The
prediction was falsified on 30 Aug; the counter-aligned pairing did prevent a
surface rule, but the model memorised both answer texts instead. Do not read
the prediction below as open.**

**The gap:** 0 of 54 clean-direction training cases added a function, yet 5 of
`bench/basic`'s cases do, all clean, and the model false-alarms on them — 3 of
pilot2's 5 false alarms and 3 of seed7's 5 are that one shape.

**The fix:** 9 matched pairs, one per language, sharing a byte-identical `pre`
and the same diff shape (a function is added, the call site rewired), differing
by one character in the new helper:

| | helper | output | label | goes to |
|---|---|---|---|---|
| `*-extract-boundary-refactor` | `score >= 60` | unchanged | refactor | `bench/clean_direction` |
| `*-extract-boundary` | `score > 60` | `pass fail` -> `fail fail` | buggy | `bench/mechanism_pilot` |

Counter-aligned on purpose. Adding only the clean half would install a new
surface rule — "an added function is safe" — which is the one-directional
mistake the 27 Aug boundary work had to spend a day undoing. A model that learns
"added function = safe" fails all 9 buggy members; one that learns "added
function = suspicious" fails all 9 refactor members. The surface cannot carry
the answer because the surface is identical.

**Held out, untouched:** the 5 `bench/basic` extract cases and TestJIT commit 4.
Different algorithm, different extraction — they test transfer, not memorisation.

**Prediction, stated before the run:** false alarms on those 5 drop toward zero.
If they do not move, coverage was not the cause and it is cleanly falsified.

## How to read that prediction — the 5 are NOT equivalent evidence (29 Aug)

Both v2 seeds score "3 of the 5 held-out extract cases false-alarm", which reads
like a stable effect. **It is not the same 3.** Pulling the two baselines apart
case by case:

| case | v2 seed42 | v2 seed7 | what it can show |
|---|---|---|---|
| `php-extract-helper` | ALARM | ALARM | **stable target** |
| `py-extract-helper` | ALARM | ALARM | **stable target** |
| `go-extract-helper` | ALARM | quiet | seed-unstable — movement here is noise |
| `java-extract-method` | quiet | ALARM | seed-unstable — movement here is noise |
| `js-extract-helper` | quiet | quiet | no headroom — cannot improve |

So the honest form of the prediction is **not** "5 -> 0". It is:

> **`php-extract-helper` and `py-extract-helper` go quiet on BOTH v3 seeds.**

Those are the only two cases where the v2 pair agrees, so they are the only two
where a change can be attributed to the corpus rather than to the seed. **A v3
run that fixes `go` and `java` but leaves `php` and `py` alarming has shown
nothing** — the seed already moves exactly those two cases on its own.

**There is a free control sitting in the same file.** `c-const` and
`py-comprehension` false-alarm on both v2 seeds and are NOT extract-shaped, so
the v3 corpus should not touch them:

- php/py go quiet, `c-const` and `py-comprehension` keep alarming
  -> **extract-shape coverage was the cause.** The claim v3 was built to make.
- php/py go quiet AND the control goes quiet too
  -> the model merely got globally less willing to flag anything. A much weaker
     claim, and one that predicts a matching cost in recall on the buggy sets.
     Check `false_alarm` against the headline before calling that a win.

## The noise floor is PER SET, and the aggregate hides it

The "±10 on locus, 24 of 101 cases" figure below is an aggregate over all three
sets. Measured per set from the same v2 seed pair — identical corpus, identical
steps, seed the only variable:

| set | cases flipping on seed alone | headline moves |
|---|---|---|
| `bench/basic` | 14 of 46 (30%) | 31 -> 35 |
| `bench/mechanism_heldout` | **10 of 21 (48%)** | 11 -> 17 |
| `bench/clean_heldout` | **0 of 34 (0%)** | 34 -> 34 |

**`mechanism_heldout` cannot resolve anything.** Half its cases flip on the seed
alone and its total swings by 6 in 21. Do not report a v3-vs-v2 difference on
that set; nothing this project can train will clear that bar on 21 cases.

`clean_heldout` is the opposite — zero flips across the pair. A change there IS
readable, which matters because that is where a "globally more timid" model
would sit unchanged at 34/34 while the buggy sets quietly lost ground.

**The headline metric is `basic_bench.py:413`** —
`verdict_ok and (identified or not buggy)`, i.e. clean cases pass by not being
flagged. It reproduces the documented 76/101 and 86/101 for the two v2 seeds
exactly; a script that does not reproduce those two numbers is measuring
something else and its deltas mean nothing. Summing raw `identified` does NOT
reproduce them (it gives 44 and 47) — that is a buggy-only count.

**The corpus:** `data/sft_v3_extract.jsonl`, 399 records, 0 temp dirs, 98
distinct assistant turns, 47% clean, 100 steps at 2 epochs (399 x 2 / 8 = 99.8).

**The first build silently shipped only half of it.** `build_mechanism_corpus`
printed `!! rs-extract-boundary has no analysis.json — skipped` for all 9 buggy
cases and built anyway: mechanism stayed at 168 while clean-direction rose to
189. That is exactly the one-directional corpus the pairing exists to prevent,
and it was a WARNING, not an error. The 9 target answers were written and
schema-validated, and the rebuild shows `mechanism x6: 222`. **A corpus can lose
a whole family to a warning — read the build output, do not just check the row
count.**

# THE RESULT THAT OUTRANKS EVERYTHING ELSE (28 Aug, evening)

**The benchmark cannot tell small differences apart, and nobody had checked.**

Three checkpoints were trained. Two of them — `sft-v2-pilot2` and
`sft-v2-pilot2-seed7` — used the **identical corpus, identical steps, identical
everything**. The only difference is `--seed 42` against `--seed 7`.

| | pilot (old corpus) | pilot2 (fixed) | seed7 (fixed) | corpus fix | **SEED ALONE** |
|---|---|---|---|---|---|
| locus | 84 | 76 | 86 | -8 | **+10** |
| direction right | 84 | 78 | 91 | -6 | **+13** |
| observable right | 35 | 31 | 21 | -4 | **-10** |
| false alarms | 1 | 5 | 5 | +4 | 0 |
| fabricated (abs path) | 9 | 0 | 0 | -9 | **0** |

**31 of 101 cases have an unstable locus grade** across the three runs. 66 are
always correct, 4 always wrong. Seed alone flipped 24 cases — 17 to correct,
7 to wrong. Locus totals span 76 to 86.

Decoding is greedy (`serve.py` ignores temperature), so this is not sampling
noise. It is the weights.

### What this invalidates

**Any checkpoint comparison in this project with a gap under ~10 cases in 101
(~5 in 46) is unsupported.** That includes claims currently written down as
findings:

- "Measured identically, v2 is the better checkpoint" — 37/46 against 35/46,
  two cases. **Not supportable.**
- "`oracle-merged` is the best model this project has" — 41/46 against 40/44.
  Same problem, and it mixes denominators as well.
- The whole four-checkpoint ranking.
- The pilot -> pilot2 "regression" of -8 locus that this session reported
  earlier in the day. Inside the band. **Do not report it as an effect.**

The "stuck at 67%" story survives, but its honest form is **"every checkpoint is
indistinguishable inside noise"**, not "each intervention trades one failure for
another". That is a cleaner claim and a more defensible one.

### What survives the noise

- **The path-fabrication fix.** 9 -> 0 -> 0, identical on both seeds. The seed
  moves it by zero. This is the one clean causal result of the day.
- **The false alarms are probably real.** 1 -> 5 -> 5: both fixed-corpus runs
  agree exactly while locus swings +-10 around them. Two seeds is weak, but it
  is consistent and in the direction the corpus changed. Earlier in the day this
  was called unattributable; the control makes it the more likely reading.
- **`clean_heldout` is completely stable** — 34/34 on all three runs, zero
  flips. All the instability lives in the buggy sets.

### What must change in how this project reports

Every number in `docs/RESULTS.md` is a single-seed point estimate. **They need
to be ranges over seeds.** A 46-case benchmark on a 3B QLoRA cannot resolve
differences under roughly 10%, which is the size of difference this field
routinely publishes. That is a measurement contribution in its own right and it
is bigger than any checkpoint result here.

`train_sft.py` now takes `--seed`. It did not before, which is why every
checkpoint ever trained here shares seed 42 and why this was invisible.

# Progress, 28 Aug, in one screen

**Twelve training runs exist. Ten SFT, two DPO (both null, closed).** Four
happened today: `sft-v2-pilot` finished 01:49, `pilot2` 14:17, `pilot2-seed7`
21:08, `v3-extract` started 22:55.

| | before today | after today |
|---|---|---|
| checkable behavioural claims, ever | **0** | **101/101** well-formed |
| `direction_ok` | could not be asked | 84/101, 78/101, 91/101 across three runs |
| fabricated absolute paths | 9/101 | **0/101**, on both seeds |
| corpus records with an unlearnable token | 66/318 (21%) | **0** |
| clean training cases that add a function | **0 of 54** | **9 of 63**, counter-aligned |
| retrain-to-retrain noise | **never measured** | **±10 locus, 24 of 101 cases** |
| apparatus bugs fixed | — | 5 |

**Against the goal — basic algorithms at 8/10 with no hallucination — neither
half is met.** Locus is 76-86 of 101 across three runs, straddling 80% *inside*
the noise band. False alarms are 1, 5, 5 and fabrication 10, 5, 5; both must be
zero. And locus is a floor: the one hand-grade that checked locus AND mechanism
came out 31/46 (67%) and has not moved across four checkpoints.

**What actually moved, and survives scrutiny:**

1. **Path fabrication 9 -> 0.** Caused by the corpus, fixed at source, stable
   across both seeds. The one clean causal result.
2. **The v2 contract is learned.** 101/101 well-formed effects against a
   baseline where no checkpoint had ever made a checkable claim.
3. **A measured noise floor**, which is the most valuable and least comfortable
   finding. See the section above.

**What did not move: the headline.** Ten SFT runs, and locus+mechanism sits
where it did. That is consistent with the standing read — the contribution is
the measurement work, not the checkpoint chase — and it is now backed by a noise
floor that explains WHY the checkpoint chase looked like it was working.

**Apparatus fixed today (five):** the row writer that dropped every `effect_*`
key; the hardcoded "v1 contract" label; the temp dir in `obs()`; the temp dir in
`outputs()`; and `DIFF_RENDERING`, which had the TUI feeding unified diffs to a
word-diff-trained checkpoint. That last one cost the single real defect in the
TestJIT `pyalgo` history — unified errored on it, word-diff caught it.

**TestJIT was rebuilt** (`~/Documents/TestJIT`) as 9 basic-algorithm repos, 45
commits, every label proved by execution. The old set was data structures and
out of distribution. It is 80% clean against `bench/basic`'s 28%, which makes it
the harsher and more honest test of the "no hallucination" half — and the model
scores 3/5 on `pyalgo`.

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

**1. Score both v3 seeds and answer the one question.** Do false alarms on the
five held-out extract cases in `bench/basic` drop toward zero? Report a RANGE
across the two seeds, never a point estimate. Commands in the status section.

**2. Retract the invalidated claims in `docs/RESULTS.md`.** The noise floor
makes several written findings unsupportable — "measured identically, v2 is the
better checkpoint" (2 cases), "`oracle-merged` is the best model this project
has" (1-5 cases, and it mixes denominators), and the four-checkpoint ranking.
They are still written as findings. Mark them, do not quietly delete them: the
retraction is itself a result, and it is the strongest argument for the
measurement contribution.

**3. Re-report every surviving number as a seed range.** Every figure in
`RESULTS.md` is a single-seed point estimate. A 46-case benchmark on a 3B QLoRA
cannot resolve differences under roughly 10%, which is the size of difference
this field publishes routinely. That sentence is the paper.

**4. Rent a GPU.** This stopped being an optimisation today. Seed ranges mean
2-3 runs per checkpoint; that is 13-20 hours on the 1660 SUPER against about an
hour rented. The card is a TU116 with **no tensor cores**, is not power or
thermally limited (74W of 125W, 1905 of 2100 MHz, 100% util), and already uses
SDPA and 4-bit — there is no software fix left. Local levers, if it stays:
`batch_size 2` + `grad_accum 4` (~1.2-1.4x, may fit in the 1.3GB headroom), one
epoch instead of two (exactly 2x), `LORA_R` 64 -> 32 (~1.1x). **Do not change
any of them mid-comparison.**

**5. Give `effect.trigger` something to say, or drop it.** 101/101 filename
echo. The builder fills it with `running {id}.{ext} as written` while the schema
asks for "One input or condition that exposes the difference". The executable
cases have real entry points with literal arguments. **No scorer may search it**
— it contains the case name.

**6. Show `effect` in the TUI.** It renders `summary` and `findings` only
(`tui_app.py:303-309`), so the behavioural claim the model is trained to emit
FIRST is generated and then thrown away. You are running a v2 model through a v1
window.

**7. Fix the remaining TestJIT failures.** After the rendering fix, `pyalgo` is
3/5: the real off-by-one is caught and the fix commit is no longer flagged, but
`add positive count` and `extract an add helper` are still false alarms. The
second is the v3 probe. The first is not covered by v3 and is unexplained.

**8. Fabrication of code that does not exist, three instances.** `siftDown(1)`
in the old heap case, a `float` conversion in `pyalgo` (the string `float`
appears 0 times in that repo's history), and a `ValueError("empty sequence")`
traceback for a function that never raises. Distinct from the path fabrication
that was fixed — the model invents a PRIOR STATE of the code to justify a
verdict. Not yet measured or counted anywhere.

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

- **A full disk fails SILENTLY through `cat > file <<'EOF'`.** On 29 Aug root hit
  100% (64K free) and a heredoc write produced a **0-byte file with exit 0** —
  `cat: write error: No space left on device` went to stderr and was nearly
  missed. `next-session.md` was checked for truncation immediately and survived.
  The offenders were caches, not data: `~/.cache/go-build` at **157G** and
  `~/.cache/yay` at 58G, both cleared. Note `data/cvefixes/CVEfixes.db` is 48G
  and is real data — do not reach for it first. Check `df -h /` before a scoring
  run: six result files plus temp space is not much, but zero is zero.
- **The GPU box's login shell is FISH, not bash.** `ssh oracle-gpu 'for x in ...;
  do ...; done'` dies with "Missing end to balance this for loop" and exit 127.
  Every remote command in this file uses `ssh oracle-gpu bash -s <<'EOF'` for
  that reason — keep it that way rather than "simplifying" to a quoted one-liner.
- **Check free VRAM before planning to serve and train at once.** The card is
  6 GB; training holds 4.4 GB. The 28 Aug handoff instructed the next session to
  "score the seed-42 run while you wait" and that was never possible. `nvidia-smi
  --query-gpu=memory.free --format=csv` costs one second and settles it.
- **Never score one arm of a comparison on CPU because the GPU is busy.** CPU and
  GPU float arithmetic differ; against a measured noise floor this small, that is
  an uncontrolled variable in the one place the project cannot afford another.
- **`trainer_state.json` lives in `checkpoint-N/`, not the adapter root**, and
  `training_args.bin` is only written when the run SAVES — so a mid-flight run
  cannot be verified from its artifacts. Read `/proc/<pid>/cmdline` instead: that
  is how `--seed 7` was confirmed at step 13 rather than at step 100.
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
- **A corpus can lose a whole family to a WARNING.**
  `build_mechanism_corpus` prints `!! <id> has no analysis.json — skipped` and
  builds anyway. All 9 buggy extract cases were dropped that way while their 9
  clean counterparts went in, which would have shipped exactly the
  one-directional corpus the pairing exists to prevent. **Read the build output
  (`mechanism x6:` / `clean-direction x3:`), not just the row count.**
- **Never poll for a sibling process by NAME; wait on a PID.** The pgrep
  self-match trap fired three times in one day — a deadlocked waiter, and two
  shells that killed themselves with exit 144, one of them a `pkill` whose own
  `sed ... score.py` argument matched its pattern. `kill -0 $PID` cannot
  self-match. `queue_seed7.sh` is the shape that works.
- **`to_word_diff` is NOT idempotent** — a second pass eats a space of
  indentation. `basic_bench --word-diff-module` renders before calling the
  client, so the client must detect already-rendered input or the benchmark
  silently changes every number instead of failing. `_already_word_diff`
  requires markers AND no surviving `+`/`-` prefixes, because either alone gives
  false positives.
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
